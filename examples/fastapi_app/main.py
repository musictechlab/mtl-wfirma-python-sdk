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


# Register template functions
templates.env.globals["extract_invoice_financials"] = (
    extract_invoice_financials_template
)


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
    year: int, month: Optional[int] = None, day: Optional[int] = None
) -> Dict[str, Any]:
    """Fetch invoices from wFirma API for the given date range."""
    client = get_client()
    date_from, date_to = calculate_date_range(year, month, day)

    xml_body = f"""
    <api>
        <invoices>
            <parameters>
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

    # Fetch data from API endpoint
    params = {"year": year}
    if month:
        params["month"] = month
    if day:
        params["day"] = day

    api_data = await fetch_data_from_api_endpoint("/api/invoices", params)

    # Sort invoices if sort_by is specified
    invoices = api_data["invoices"]
    if sort_by:
        reverse_order = sort_order == "desc"

        if sort_by == "number":
            invoices = sorted(
                invoices, key=lambda x: x.get("fullnumber", ""), reverse=reverse_order
            )
        elif sort_by == "date":
            invoices = sorted(
                invoices, key=lambda x: x.get("date", ""), reverse=reverse_order
            )
        elif sort_by == "contractor":
            invoices = sorted(
                invoices,
                key=lambda x: x.get("contractor", {}).get("altname", ""),
                reverse=reverse_order,
            )
        elif sort_by == "netto":
            invoices = sorted(
                invoices,
                key=lambda x: extract_invoice_financials(x)[0],  # netto
                reverse=reverse_order,
            )
        elif sort_by == "tax":
            invoices = sorted(
                invoices,
                key=lambda x: extract_invoice_financials(x)[2],  # tax
                reverse=reverse_order,
            )
        elif sort_by == "brutto":
            invoices = sorted(
                invoices,
                key=lambda x: extract_invoice_financials(x)[1],  # brutto
                reverse=reverse_order,
            )
        elif sort_by == "paid":
            invoices = sorted(
                invoices,
                key=lambda x: float(x.get("alreadypaid") or 0)
                * float(x.get("price_currency_exchange") or 1.0),
                reverse=reverse_order,
            )
        elif sort_by == "paymentdate":
            invoices = sorted(
                invoices, key=lambda x: x.get("paymentdate", ""), reverse=reverse_order
            )
        elif sort_by == "status":
            invoices = sorted(
                invoices, key=lambda x: x.get("paymentstate", ""), reverse=reverse_order
            )

    return templates.TemplateResponse(
        "invoices.html",
        {
            "request": request,
            "invoices": invoices,
            "count": api_data["count"],
            "year": year,
            "month": month,
            "day": day,
            "sort_by": sort_by,
            "sort_order": sort_order,
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
            "current_year": datetime.now().year + 1,
            "monthly_data": api_data["monthly_data"],
        },
    )


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

        if payment_date:
            pay_dt = datetime.strptime(payment_date, "%Y-%m-%d")
            days_to_payment = (pay_dt - now).days
            inv["days_to_payment"] = days_to_payment

            type = inv.get("type")
            if type != "correction":
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

                # Sprawdź czy przeterminowane
                if payment_date:
                    pay_dt = datetime.strptime(payment_date, "%Y-%m-%d")
                    if pay_dt < now:
                        overdue_count += 1
                        overdue_sum += brutto

        monthly_data.append(
            {
                "month_num": month,
                "month_name": month_names[month - 1],
                "total_invoices": total_invoices,
                "total_netto": round(total_netto, 2),
                "total_brutto": round(total_brutto, 2),
                "unpaid_count": unpaid_count,
                "unpaid_sum": round(unpaid_sum, 2),
                "overdue_count": overdue_count,
                "overdue_sum": round(overdue_sum, 2),
            }
        )

    result = {"monthly_data": monthly_data}

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
