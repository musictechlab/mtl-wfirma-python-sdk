from fastapi import FastAPI, Query, Request
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
import os
from dotenv import load_dotenv
import httpx
import time

# Wykorzystujemy klienta SDK
from wfirma_sdk import WFirmaAPIClient

# Load environment variables
load_dotenv()

app = FastAPI(title="MTL wFirma Invoices API Demo")

# Setup templates
templates = Jinja2Templates(directory="templates")


# Add custom template functions
def extract_invoice_financials_template(
    invoice: Dict[str, Any],
) -> Tuple[float, float, float]:
    """Template version of extract_invoice_financials for use in Jinja2 templates."""
    return extract_invoice_financials(invoice)


def format_currency(amount):
    """Format currency with thousands separators."""
    if amount is None:
        return "0,00"
    try:
        # Convert to float if it's a string
        if isinstance(amount, str):
            amount = float(amount)

        # Format with 2 decimal places and thousands separator
        formatted = f"{amount:,.2f}"
        # Replace comma with space for thousands separator (Polish format)
        formatted = formatted.replace(",", " ")
        # Replace dot with comma for decimal separator (Polish format)
        formatted = formatted.replace(".", ",")
        return formatted
    except (ValueError, TypeError):
        return "0,00"


# Register template functions
def generate_invoice_filter_url(year: int, month: int, invoice_numbers: list) -> str:
    """Generate URL for filtering invoices by year, month and specific invoice numbers."""
    base_url = f"/?year={year}&month={month}"
    if invoice_numbers:
        # Add invoice numbers as comma-separated parameter
        invoice_numbers_str = ",".join(invoice_numbers)
        base_url += f"&invoice_numbers={invoice_numbers_str}"
    return base_url


# Register the function for use in templates
templates.env.globals["generate_invoice_filter_url"] = generate_invoice_filter_url
templates.env.globals["extract_invoice_financials"] = (
    extract_invoice_financials_template
)
templates.env.globals["format_currency"] = format_currency


class SimpleCache:
    """Simple in-memory cache with TTL support."""

    def __init__(self):
        self._cache = {}

    def get(self, key: str, ttl: int = 300) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < ttl:
                return value
            else:
                del self._cache[key]
        return None

    def set(self, key: str, value: Any) -> None:
        """Set value in cache with current timestamp."""
        self._cache[key] = (value, time.time())

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()


# Global cache instance
cache = SimpleCache()


def get_client():
    """Helper function to create WFirmaAPIClient with environment variables."""
    access_key = os.getenv("WFIRMA_ACCESS_KEY")
    secret_key = os.getenv("WFIRMA_SECRET_KEY")
    app_key = os.getenv("WFIRMA_APP_KEY")
    company_id = os.getenv("WFIRMA_COMPANY_ID")

    return WFirmaAPIClient(
        company_id=company_id,
        access_key=access_key,
        secret_key=secret_key,
        app_key=app_key,
    )


def extract_invoice_financials(invoice: Dict[str, Any]) -> Tuple[float, float, float]:
    """
    Extract netto, brutto, and tax values from invoice.
    First tries vat_contents.vat_content, falls back to direct invoice fields.
    """
    # Check if vat_contents exists and has vat_content
    vat_contents = invoice.get("vat_contents", {})
    vat_content = vat_contents.get("vat_content", {}) if vat_contents else {}

    if vat_content:
        # Use data from vat_contents.vat_content
        netto = float(vat_content.get("netto") or 0)
        brutto = float(vat_content.get("brutto") or 0)
        tax = float(vat_content.get("tax") or 0)
    else:
        # Fall back to direct invoice fields
        netto = float(invoice.get("netto") or 0)
        brutto = float(invoice.get("brutto") or 0)
        tax = float(invoice.get("tax") or 0)

    return netto, brutto, tax


def extract_invoice_financials_original_currency(
    invoice: Dict[str, Any],
) -> Tuple[float, float, float]:
    """
    Extract netto, brutto, and tax values from invoice in original currency.
    Uses invoicecontents or total field for original currency amounts.
    """
    # Try to get amounts from invoicecontents (original currency)
    invoicecontents = invoice.get("invoicecontents", {})
    invoicecontent = invoicecontents.get("invoicecontent", {})

    if invoicecontent:
        # If it's a list, sum all items
        if isinstance(invoicecontent, list):
            netto = sum(float(item.get("netto", 0)) for item in invoicecontent)
            brutto = sum(float(item.get("brutto", 0)) for item in invoicecontent)
            tax = sum(float(item.get("tax", 0)) for item in invoicecontent)
        else:
            # Single item
            netto = float(invoicecontent.get("netto", 0))
            brutto = float(invoicecontent.get("brutto", 0))
            tax = float(invoicecontent.get("tax", 0))
    else:
        # Fall back to total field (original currency)
        total = float(invoice.get("total", 0))
        brutto = total
        netto = total  # For non-VAT invoices, netto = brutto
        tax = 0

    # For PLN invoices, tax might be in vat_contents instead of invoicecontents
    if tax == 0 and invoice.get("vat_contents"):
        vat_contents = invoice.get("vat_contents", {})
        vat_content = vat_contents.get("vat_content", {})
        if vat_content:
            if isinstance(vat_content, list):
                tax = sum(float(item.get("tax", 0)) for item in vat_content)
            else:
                tax = float(vat_content.get("tax", 0))

    return netto, brutto, tax


def calculate_date_range(
    year: int, month: Optional[int] = None, day: Optional[int] = None
) -> Tuple[str, str]:
    """Calculate date range based on year, month, and day parameters."""
    date_from = datetime(year, month or 1, day or 1).strftime("%Y-%m-%d")

    if day:
        date_to = date_from
    elif month:
        # ostatni dzień miesiąca
        next_month = datetime(year + int(month == 12), (month % 12) + 1, 1)
        date_to = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        date_to = datetime(year, 12, 31).strftime("%Y-%m-%d")

    return date_from, date_to


def fetch_invoices_from_api(
    year: int,
    month: Optional[int] = None,
    day: Optional[int] = None,
) -> Dict[str, Any]:
    """Fetch invoices from wFirma API for the given date range."""
    client = get_client()
    date_from, date_to = calculate_date_range(year, month, day)
    xml_body = f"""
    <api>
        <invoices>
            <parameters>
                <limit>500</limit>
                <conditions>
                    <condition>
                        <field>date</field>
                        <operator>ge</operator>
                        <value>{date_from}</value>
                    </condition>
                    <condition>
                        <field>date</field>
                        <operator>le</operator>
                        <value>{date_to}</value>
                    </condition>
                </conditions>
            </parameters>
        </invoices>
    </api>
    """

    response = client._request(
        "POST",
        "/invoices/find",
        data=xml_body,
    )

    # Extract invoices from the parsed response
    invoices = response.get("invoices", {}).get("invoice", [])
    if not isinstance(invoices, list):
        invoices = [invoices] if invoices else []

    return {"count": len(invoices), "invoices": invoices}


async def fetch_data_from_api_endpoint(
    endpoint: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    """Fetch data from internal API endpoint."""
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://localhost:8000{endpoint}", params=params)
        return response.json()


@app.get("/")
async def invoices_web(
    request: Request,
    year: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    day: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query("asc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=200),
    invoice_numbers: Optional[str] = Query(None),
):
    """Web view for invoices list."""
    # Parse and validate parameters
    try:
        year = int(year) if year and year.strip() else datetime.now().year
        month = int(month) if month and month.strip() else None
        day = int(day) if day and day.strip() else None
    except ValueError:
        # If parsing fails, use defaults
        year = datetime.now().year
        month = None
        day = None

    # Fetch all invoices from wFirma API (no pagination on API side)
    all_invoices_data = fetch_invoices_from_api(year, month, day)
    all_invoices = all_invoices_data["invoices"]

    # Filter by invoice numbers if specified
    if invoice_numbers:
        invoice_numbers_list = [
            num.strip() for num in invoice_numbers.split(",") if num.strip()
        ]
        all_invoices = [
            inv
            for inv in all_invoices
            if inv.get("fullnumber", "") in invoice_numbers_list
        ]

    total_invoices = len(all_invoices)

    # Sort invoices if sort_by is specified
    if sort_by:
        reverse_order = sort_order == "desc"

        if sort_by == "number":
            all_invoices = sorted(
                all_invoices,
                key=lambda x: x.get("fullnumber", ""),
                reverse=reverse_order,
            )
        elif sort_by == "date":
            all_invoices = sorted(
                all_invoices, key=lambda x: x.get("date", ""), reverse=reverse_order
            )
        elif sort_by == "contractor":
            all_invoices = sorted(
                all_invoices,
                key=lambda x: x.get("contractor", {}).get("altname", ""),
                reverse=reverse_order,
            )
        elif sort_by == "netto":
            all_invoices = sorted(
                all_invoices,
                key=lambda x: extract_invoice_financials(x)[0],  # netto
                reverse=reverse_order,
            )
        elif sort_by == "tax":
            all_invoices = sorted(
                all_invoices,
                key=lambda x: extract_invoice_financials(x)[2],  # tax
                reverse=reverse_order,
            )
        elif sort_by == "brutto":
            all_invoices = sorted(
                all_invoices,
                key=lambda x: extract_invoice_financials(x)[1],  # brutto
                reverse=reverse_order,
            )
        elif sort_by == "paid":
            all_invoices = sorted(
                all_invoices,
                key=lambda x: float(x.get("alreadypaid") or 0)
                * float(x.get("price_currency_exchange") or 1.0),
                reverse=reverse_order,
            )
        elif sort_by == "paymentdate":
            all_invoices = sorted(
                all_invoices,
                key=lambda x: x.get("paymentdate", ""),
                reverse=reverse_order,
            )
        elif sort_by == "status":
            all_invoices = sorted(
                all_invoices,
                key=lambda x: x.get("paymentstate", ""),
                reverse=reverse_order,
            )

    # Apply pagination after sorting
    start_index = (page - 1) * per_page
    end_index = start_index + per_page
    invoices = all_invoices[start_index:end_index]

    # Calculate pagination info
    total_pages = (total_invoices + per_page - 1) // per_page
    display_start_index = start_index + 1
    display_end_index = min(end_index, total_invoices)

    return templates.TemplateResponse(
        "invoices.html",
        {
            "request": request,
            "invoices": invoices,
            "count": total_invoices,
            "year": year,
            "month": month,
            "day": day,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "start_index": display_start_index,
            "end_index": display_end_index,
            "invoice_numbers": invoice_numbers,
        },
    )


@app.get("/summary")
async def summary_web(
    request: Request,
    year: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    day: Optional[str] = Query(None),
):
    """Web view for invoices summary."""
    # Parse and validate parameters
    try:
        year = int(year) if year and year.strip() else datetime.now().year
        month = int(month) if month and month.strip() else None
        day = int(day) if day and day.strip() else None
    except ValueError:
        # If parsing fails, use defaults
        year = datetime.now().year
        month = None
        day = None

    # Fetch data from API endpoint
    params = {"year": year}
    if month:
        params["month"] = month
    if day:
        params["day"] = day

    api_data = await fetch_data_from_api_endpoint("/api/invoices/summary", params)

    return templates.TemplateResponse(
        "summary.html",
        {
            "request": request,
            "total_invoices": api_data["total_invoices"],
            "total_netto": api_data["total_netto"],
            "total_brutto": api_data["total_brutto"],
            "total_vat": api_data["total_vat"],
            "overdue_count": api_data["overdue_count"],
            "overdue_sum": api_data["overdue_sum"],
            "overdue": api_data["overdue"],
            "soon_due_count": api_data["soon_due_count"],
            "soon_due_invoices": api_data["soon_due_invoices"],
            "year": year,
            "month": month,
            "day": day,
        },
    )


@app.get("/api/invoices")
async def list_invoices_api(
    year: int = Query(datetime.now().year),
    month: Optional[int] = Query(None),
    day: Optional[int] = Query(None),
):
    """
    API endpoint - pobiera faktury z API wFirma dla wybranego roku/miesiąca/dnia.
    Przykłady:
    - /api/invoices?year=2024
    - /api/invoices?year=2024&month=5
    - /api/invoices?year=2024&month=5&day=10
    """
    return fetch_invoices_from_api(year, month, day)


@app.get("/overview")
async def overview_web(
    request: Request,
    year: Optional[str] = Query(None),
):
    """Web view for invoices overview table."""
    # Parse and validate parameters
    try:
        year = int(year) if year and year.strip() else datetime.now().year
    except ValueError:
        # If parsing fails, use current year
        year = datetime.now().year

    # Fetch data from API endpoint
    params = {"year": year}
    api_data = await fetch_data_from_api_endpoint("/api/invoices/overview", params)

    return templates.TemplateResponse(
        "overview.html",
        {
            "request": request,
            "year": year,
            "current_year": datetime.now().year,
            "monthly_data": api_data["monthly_data"],
            "totals": api_data["totals"],
        },
    )


@app.get("/clients")
async def clients_web(
    request: Request,
    year: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
):
    """Web view for clients overview table."""
    # Parse and validate parameters
    try:
        year = int(year) if year and year.strip() else datetime.now().year
    except ValueError:
        # If parsing fails, use current year
        year = datetime.now().year

    # Fetch data from API endpoint
    params = {"year": year}
    if sort_by:
        params["sort_by"] = sort_by
    if sort_order:
        params["sort_order"] = sort_order

    api_data = await fetch_data_from_api_endpoint("/api/invoices/clients", params)

    return templates.TemplateResponse(
        "clients.html",
        {
            "request": request,
            "year": year,
            "current_year": datetime.now().year,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "clients_data": api_data["clients_data"],
            "totals": api_data["totals"],
        },
    )


@app.get("/currencies")
async def currencies_web(
    request: Request,
    year: Optional[str] = Query(None),
    sort_by: Optional[str] = Query(None),
    sort_order: Optional[str] = Query(None),
):
    """Web view for currencies analysis."""
    # Parse and validate parameters
    try:
        year = int(year) if year and year.strip() else datetime.now().year
    except ValueError:
        # If parsing fails, use current year
        year = datetime.now().year

    # Fetch data from API endpoint
    params = {"year": year}
    if sort_by:
        params["sort_by"] = sort_by
    if sort_order:
        params["sort_order"] = sort_order

    api_data = await fetch_data_from_api_endpoint("/api/invoices/currencies", params)

    return templates.TemplateResponse(
        "currencies.html",
        {
            "request": request,
            "year": year,
            "current_year": datetime.now().year,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "currencies_data": api_data["currencies_data"],
            "totals": api_data["totals"],
        },
    )


@app.get("/transactions")
async def transactions_web(request: Request):
    """Web view for transactions analysis."""
    import json

    # Load transaction data from JSON file
    json_file_path = "data/combined_summary.json"

    try:
        with open(json_file_path, "r") as f:
            transaction_data = json.load(f)
    except FileNotFoundError:
        # Return empty data if file doesn't exist
        transaction_data = {
            "total_files_processed": 0,
            "individual_summaries": [],
            "combined_statistics": {},
        }
    except Exception as e:
        # Handle other errors
        transaction_data = {
            "total_files_processed": 0,
            "individual_summaries": [],
            "combined_statistics": {},
            "error": str(e),
        }

    return templates.TemplateResponse(
        "transactions.html",
        {
            "request": request,
            "individual_summaries": transaction_data.get("individual_summaries", []),
            "total_files_processed": transaction_data.get("total_files_processed", 0),
            "combined_statistics": transaction_data.get("combined_statistics", {}),
        },
    )


@app.get("/api/invoices/clients")
async def invoices_clients_api(
    year: int = Query(datetime.now().year),
    sort_by: Optional[str] = Query("total_brutto"),
    sort_order: Optional[str] = Query("desc"),
):
    """
    API endpoint - zwraca dane faktur pogrupowane po klientach:
    - liczba faktur per klient
    - suma netto, brutto, VAT per klient
    - zaległe faktury per klient
    - faktury przeterminowane per klient
    """
    # Get invoices data using the helper function
    invoices_data = fetch_invoices_from_api(year)
    invoices = invoices_data["invoices"]

    # Group invoices by client
    clients_data = {}
    now = datetime.now()

    for inv in invoices:
        contractor_name = inv.get("contractor", {}).get("altname", "Brak nazwy")

        if contractor_name not in clients_data:
            clients_data[contractor_name] = {
                "client_name": contractor_name,
                "total_invoices": 0,
                "total_netto": 0.0,
                "total_brutto": 0.0,
                "total_vat": 0.0,
                "unpaid_count": 0,
                "unpaid_sum": 0.0,
                "unpaid_invoices": [],
                "overdue_count": 0,
                "overdue_sum": 0.0,
                "overdue_invoices": [],
            }

        # Extract financial data
        netto, brutto, vat = extract_invoice_financials(inv)

        # Update totals
        clients_data[contractor_name]["total_invoices"] += 1
        clients_data[contractor_name]["total_netto"] += netto
        clients_data[contractor_name]["total_brutto"] += brutto
        clients_data[contractor_name]["total_vat"] += vat

        # Check payment status (skip corrections)
        payment_date = inv.get("paymentdate")
        paid_state = inv.get("paymentstate")
        invoice_type = inv.get("type", "")

        # Skip corrections in unpaid/overdue calculations
        if invoice_type != "correction" and paid_state != "paid":
            clients_data[contractor_name]["unpaid_count"] += 1
            clients_data[contractor_name]["unpaid_sum"] += brutto
            clients_data[contractor_name]["unpaid_invoices"].append(
                inv.get("fullnumber", "")
            )

            if payment_date:
                try:
                    pay_dt = datetime.strptime(payment_date, "%Y-%m-%d")
                    if pay_dt < now:
                        clients_data[contractor_name]["overdue_count"] += 1
                        clients_data[contractor_name]["overdue_sum"] += brutto
                        clients_data[contractor_name]["overdue_invoices"].append(
                            inv.get("fullnumber", "")
                        )
                except ValueError:
                    pass

    # Convert to list and sort
    clients_list = list(clients_data.values())

    # Define sorting keys
    sort_keys = {
        "client_name": lambda x: x["client_name"].lower(),
        "total_invoices": lambda x: x["total_invoices"],
        "total_netto": lambda x: x["total_netto"],
        "total_brutto": lambda x: x["total_brutto"],
        "total_vat": lambda x: x["total_vat"],
        "unpaid_count": lambda x: x["unpaid_count"],
        "overdue_count": lambda x: x["overdue_count"],
    }

    # Apply sorting
    if sort_by in sort_keys:
        reverse_order = sort_order == "desc"
        clients_list.sort(key=sort_keys[sort_by], reverse=reverse_order)
    else:
        # Default sort by total_brutto descending
        clients_list.sort(key=lambda x: x["total_brutto"], reverse=True)

    # Calculate totals
    total_invoices_sum = sum(client["total_invoices"] for client in clients_list)
    total_netto_sum = sum(client["total_netto"] for client in clients_list)
    total_brutto_sum = sum(client["total_brutto"] for client in clients_list)
    total_vat_sum = sum(client["total_vat"] for client in clients_list)
    total_unpaid_count = sum(client["unpaid_count"] for client in clients_list)
    total_unpaid_sum = sum(client["unpaid_sum"] for client in clients_list)
    total_overdue_count = sum(client["overdue_count"] for client in clients_list)
    total_overdue_sum = sum(client["overdue_sum"] for client in clients_list)

    # Find smallest client by brutto amount
    smallest_client = (
        min(clients_list, key=lambda x: x["total_brutto"]) if clients_list else None
    )

    result = {
        "clients_data": clients_list,
        "totals": {
            "total_invoices_sum": total_invoices_sum,
            "total_netto_sum": round(total_netto_sum, 2),
            "total_brutto_sum": round(total_brutto_sum, 2),
            "total_vat_sum": round(total_vat_sum, 2),
            "total_unpaid_count": total_unpaid_count,
            "total_unpaid_sum": round(total_unpaid_sum, 2),
            "total_overdue_count": total_overdue_count,
            "total_overdue_sum": round(total_overdue_sum, 2),
            "smallest_client": smallest_client,
        },
    }

    return result


@app.get("/api/invoices/currencies")
async def invoices_currencies_api(
    year: int = Query(datetime.now().year),
    include_all_years: bool = Query(False),
    sort_by: Optional[str] = Query("total_brutto_pln"),
    sort_order: Optional[str] = Query("desc"),
):
    """
    API endpoint - zwraca analizę walut:
    - ile jakich walut było użytych
    - jaki miały udział w przychodach
    """
    # Get invoices data using the helper function
    invoices_data = fetch_invoices_from_api(year)
    invoices = invoices_data["invoices"]

    # Group invoices by currency
    currencies_data = {}
    total_amount_all_currencies = 0.0

    for inv in invoices:
        # Get currency from invoice - try multiple possible fields
        currency = (
            inv.get("price_currency")
            or inv.get("currency")
            or inv.get("price_currency_code")
            or inv.get("vat_contents", {}).get("vat_content", {}).get("currency")
            or "PLN"
        )
        if not currency:
            currency = "PLN"

        # Extract financial data - use different functions based on currency
        if currency == "PLN":
            # For PLN, use the standard function that already returns PLN amounts
            netto, brutto, vat = extract_invoice_financials(inv)
            exchange_rate = 1.0  # No conversion needed for PLN
        else:
            # For other currencies, use original currency function
            netto, brutto, vat = extract_invoice_financials_original_currency(inv)
            exchange_rate = float(inv.get("currency_exchange", 1.0))

        # Convert to PLN
        netto_pln = netto * exchange_rate
        brutto_pln = brutto * exchange_rate
        vat_pln = vat * exchange_rate

        if currency not in currencies_data:
            currencies_data[currency] = {
                "currency": currency,
                "invoice_count": 0,
                "total_netto": 0.0,
                "total_brutto": 0.0,
                "total_vat": 0.0,
                "total_netto_pln": 0.0,
                "total_brutto_pln": 0.0,
                "total_vat_pln": 0.0,
            }

        currencies_data[currency]["invoice_count"] += 1
        currencies_data[currency]["total_netto"] += netto
        currencies_data[currency]["total_brutto"] += brutto
        currencies_data[currency]["total_vat"] += vat
        currencies_data[currency]["total_netto_pln"] += netto_pln
        currencies_data[currency]["total_brutto_pln"] += brutto_pln
        currencies_data[currency]["total_vat_pln"] += vat_pln

        total_amount_all_currencies += brutto_pln

    # Convert to list and sort by specified field
    currencies_list = list(currencies_data.values())

    sort_keys = {
        "currency": lambda x: x["currency"].lower(),
        "invoice_count": lambda x: x["invoice_count"],
        "total_netto": lambda x: x["total_netto"],
        "total_brutto": lambda x: x["total_brutto"],
        "total_netto_pln": lambda x: x["total_netto_pln"],
        "total_brutto_pln": lambda x: x["total_brutto_pln"],
        "total_vat": lambda x: x["total_vat"],
        "total_vat_pln": lambda x: x["total_vat_pln"],
        "percentage": lambda x: x["percentage"],
    }

    if sort_by in sort_keys:
        reverse_order = sort_order == "desc"
        currencies_list.sort(key=sort_keys[sort_by], reverse=reverse_order)
    else:
        currencies_list.sort(key=lambda x: x["total_brutto_pln"], reverse=True)

    # Calculate percentages
    for currency_data in currencies_list:
        if total_amount_all_currencies > 0:
            currency_data["percentage"] = round(
                (currency_data["total_brutto_pln"] / total_amount_all_currencies) * 100,
                2,
            )
        else:
            currency_data["percentage"] = 0.0

        # Round amounts
        currency_data["total_netto"] = round(currency_data["total_netto"], 2)
        currency_data["total_brutto"] = round(currency_data["total_brutto"], 2)
        currency_data["total_vat"] = round(currency_data["total_vat"], 2)
        currency_data["total_netto_pln"] = round(currency_data["total_netto_pln"], 2)
        currency_data["total_brutto_pln"] = round(currency_data["total_brutto_pln"], 2)
        currency_data["total_vat_pln"] = round(currency_data["total_vat_pln"], 2)

    # Calculate totals
    total_currencies = len(currencies_list)
    total_invoices = sum(currency["invoice_count"] for currency in currencies_list)
    total_netto_sum_pln = sum(
        currency["total_netto_pln"] for currency in currencies_list
    )
    total_brutto_sum_pln = sum(
        currency["total_brutto_pln"] for currency in currencies_list
    )
    total_vat_sum_pln = sum(currency["total_vat_pln"] for currency in currencies_list)

    result = {
        "currencies_data": currencies_list,
        "totals": {
            "total_currencies": total_currencies,
            "total_invoices": total_invoices,
            "total_netto_sum_pln": round(total_netto_sum_pln, 2),
            "total_brutto_sum_pln": round(total_brutto_sum_pln, 2),
            "total_vat_sum_pln": round(total_vat_sum_pln, 2),
        },
    }

    return result


@app.get("/api/debug/invoice-structure")
async def debug_invoice_structure(
    year: int = Query(datetime.now().year),
):
    """Debug endpoint to see invoice structure and available currency fields."""
    invoices_data = fetch_invoices_from_api(year)
    invoices = invoices_data["invoices"]

    if not invoices:
        return {"message": "No invoices found", "sample": None}

    # Check currencies in all invoices and find samples
    currencies_found = set()
    currency_samples = {}

    for invoice in invoices:
        currency = invoice.get("currency", "PLN")
        currencies_found.add(currency)

        # Store sample for each currency
        if currency not in currency_samples:
            currency_samples[currency] = {
                "sample_invoice": invoice,
                "currency_fields": {},
            }
            # Extract all currency-related fields
            for key, value in invoice.items():
                if "currency" in key.lower() or "waluta" in key.lower():
                    currency_samples[currency]["currency_fields"][key] = value

    return {
        "total_invoices": len(invoices),
        "currencies_found": list(currencies_found),
        "currency_samples": currency_samples,
    }


@app.get("/api/invoices/summary")
async def invoices_summary_api(
    year: int = Query(datetime.now().year),
    month: Optional[int] = Query(None),
    day: Optional[int] = Query(None),
):
    """
    API endpoint - zwraca agregaty dla faktur:
    - liczba faktur
    - suma netto, brutto, VAT
    - zaległe faktury
    - faktury zbliżające się do terminu płatności (3 dni)
    """
    # Get invoices data using the helper function
    invoices_data = fetch_invoices_from_api(year, month, day)
    invoices = invoices_data["invoices"]

    total_net = total_gross = total_vat = 0.0
    overdue = []
    soon_due = []
    now = datetime.now()

    for inv in invoices:
        netto, brutto, vat = extract_invoice_financials(inv)
        total_net += netto
        total_gross += brutto
        total_vat += vat

        payment_date = inv.get("paymentdate")
        paid_state = inv.get("paymentstate")
        invoice_type = inv.get("type")

        # Skip corrections in payment status calculations
        if invoice_type != "correction" and payment_date:
            pay_dt = datetime.strptime(payment_date, "%Y-%m-%d")
            days_to_payment = (pay_dt - now).days
            inv["days_to_payment"] = days_to_payment
            if inv.get("correction_type") != "correction":
                if paid_state != "paid":
                    if pay_dt < now:
                        overdue.append(inv)
                    elif days_to_payment <= 3:
                        soon_due.append(inv)

    return {
        "total_invoices": len(invoices),
        "total_netto": round(total_net, 2),
        "total_brutto": round(total_gross, 2),
        "total_vat": round(total_vat, 2),
        "overdue_count": len(overdue),
        "overdue_sum": round(sum(extract_invoice_financials(i)[1] for i in overdue), 2),
        "overdue": overdue,
        "soon_due_count": len(soon_due),
        "soon_due_invoices": soon_due,
    }


@app.get("/api/invoices/overview")
async def invoices_overview_api(
    year: int = Query(datetime.now().year),
):
    """
    API endpoint - zwraca dane dla tabeli overview:
    - dla każdego miesiąca: ilość faktur, kwota netto, kwota brutto, niezapłacone, przeterminowe
    """
    # Check cache first (5 minutes TTL)
    cache_key = f"overview_{year}"
    cached_result = cache.get(cache_key, ttl=300)
    if cached_result is not None:
        return cached_result

    monthly_data = []
    now = datetime.now()

    # Miesiące w języku polskim
    month_names = [
        "Styczeń",
        "Luty",
        "Marzec",
        "Kwiecień",
        "Maj",
        "Czerwiec",
        "Lipiec",
        "Sierpień",
        "Wrzesień",
        "Październik",
        "Listopad",
        "Grudzień",
    ]

    for month in range(1, 13):
        # Pobierz dane dla każdego miesiąca
        invoices_data = fetch_invoices_from_api(year, month)
        invoices = invoices_data["invoices"]
        total_invoices = len(invoices)
        total_netto = 0.0
        total_brutto = 0.0
        unpaid_count = 0
        unpaid_sum = 0.0
        overdue_count = 0
        overdue_sum = 0.0
        unpaid_invoices = []
        overdue_invoices = []

        for inv in invoices:
            netto, brutto, vat = extract_invoice_financials(inv)
            total_netto += netto
            total_brutto += brutto

            payment_date = inv.get("paymentdate")
            paid_state = inv.get("paymentstate")
            invoice_type = inv.get("type")

            # Licz niezapłacone faktury (nie korekty)
            if invoice_type != "correction" and paid_state != "paid":
                unpaid_count += 1
                unpaid_sum += brutto
                unpaid_invoices.append(inv.get("fullnumber", ""))

                # Sprawdź czy przeterminowane
                if payment_date:
                    pay_dt = datetime.strptime(payment_date, "%Y-%m-%d")
                    if pay_dt < now:
                        overdue_count += 1
                        overdue_sum += brutto
                        overdue_invoices.append(inv.get("fullnumber", ""))

        monthly_data.append(
            {
                "month_num": month,
                "month_name": month_names[month - 1],
                "total_invoices": total_invoices,
                "total_netto": round(total_netto, 2),
                "total_brutto": round(total_brutto, 2),
                "unpaid_count": unpaid_count,
                "unpaid_sum": round(unpaid_sum, 2),
                "unpaid_invoices": unpaid_invoices,
                "overdue_count": overdue_count,
                "overdue_sum": round(overdue_sum, 2),
                "overdue_invoices": overdue_invoices,
            }
        )

    # Calculate totals
    total_invoices_sum = sum(month["total_invoices"] for month in monthly_data)
    total_netto_sum = sum(month["total_netto"] for month in monthly_data)
    total_brutto_sum = sum(month["total_brutto"] for month in monthly_data)
    total_unpaid_count = sum(month["unpaid_count"] for month in monthly_data)
    total_unpaid_sum = sum(month["unpaid_sum"] for month in monthly_data)
    total_overdue_count = sum(month["overdue_count"] for month in monthly_data)
    total_overdue_sum = sum(month["overdue_sum"] for month in monthly_data)

    result = {
        "monthly_data": monthly_data,
        "totals": {
            "total_invoices_sum": total_invoices_sum,
            "total_netto_sum": round(total_netto_sum, 2),
            "total_brutto_sum": round(total_brutto_sum, 2),
            "total_unpaid_count": total_unpaid_count,
            "total_unpaid_sum": round(total_unpaid_sum, 2),
            "total_overdue_count": total_overdue_count,
            "total_overdue_sum": round(total_overdue_sum, 2),
        },
    }
    # Cache the result
    cache.set(cache_key, result)

    return result


@app.post("/api/cache/clear")
async def clear_cache():
    """Clear the cache. Useful for forcing data refresh."""
    cache.clear()
    return {"message": "Cache cleared successfully"}


@app.get("/api/cache/status")
async def cache_status():
    """Get cache status information."""
    return {"cache_size": len(cache._cache), "cached_keys": list(cache._cache.keys())}
