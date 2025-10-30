from fastapi import FastAPI, Query, Request
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
import os
from dotenv import load_dotenv
import httpx


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
