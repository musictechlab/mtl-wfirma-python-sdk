from pprint import pp
from fastapi import FastAPI, Query, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta
from typing import Optional
import os
from dotenv import load_dotenv

# Wykorzystujemy klienta SDK
from wfirma_sdk import WFirmaAPIClient

# Load environment variables
load_dotenv()

app = FastAPI(title="wFirma Invoices API Demo")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Mount static files (if needed)
# app.mount("/static", StaticFiles(directory="static"), name="static")


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


@app.get("/")
async def invoices_web(
    request: Request,
    year: Optional[str] = Query(None),
    month: Optional[str] = Query(None),
    day: Optional[str] = Query(None),
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

    client = get_client()
    date_from = datetime(year, month or 1, day or 1).strftime("%Y-%m-%d")

    if day:
        date_to = date_from
    elif month:
        # ostatni dzień miesiąca
        next_month = datetime(year + int(month == 12), (month % 12) + 1, 1)
        date_to = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        date_to = datetime(year, 12, 31).strftime("%Y-%m-%d")

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

    return templates.TemplateResponse(
        "invoices.html",
        {
            "request": request,
            "invoices": invoices,
            "count": len(invoices),
            "year": year,
            "month": month,
            "day": day,
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

    client = get_client()
    date_from = datetime(year, month or 1, day or 1).strftime("%Y-%m-%d")

    if day:
        date_to = date_from
    elif month:
        next_month = datetime(year + int(month == 12), (month % 12) + 1, 1)
        date_to = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        date_to = datetime(year, 12, 31).strftime("%Y-%m-%d")

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

    total_net = total_gross = total_vat = 0.0
    overdue = []
    soon_due = []
    now = datetime.now()

    for inv in invoices:
        netto = float(inv.get("netto") or 0)

        if inv.get("vat_contents"):
            brutto = float(
                inv.get("vat_contents").get("vat_content").get("brutto") or 0
            )
            vat = float(inv.get("vat_contents").get("vat_content").get("tax") or 0)
        else:
            brutto = float(inv.get("brutto") or 0)
            vat = float(inv.get("tax") or 0)

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

    return templates.TemplateResponse(
        "summary.html",
        {
            "request": request,
            "total_invoices": len(invoices),
            "total_netto": round(total_net, 2),
            "total_brutto": round(total_gross, 2),
            "total_vat": round(total_vat, 2),
            "overdue_count": len(overdue),
            "overdue_sum": round(sum(float(i.get("brutto") or 0) for i in overdue), 2),
            "overdue": overdue,
            "soon_due_count": len(soon_due),
            "soon_due_invoices": soon_due,
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
    client = get_client()
    date_from = datetime(year, month or 1, day or 1).strftime("%Y-%m-%d")

    if day:
        date_to = date_from
    elif month:
        # ostatni dzień miesiąca
        next_month = datetime(year + int(month == 12), (month % 12) + 1, 1)
        date_to = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        date_to = datetime(year, 12, 31).strftime("%Y-%m-%d")

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
    client = get_client()

    date_from = datetime(year, month or 1, day or 1).strftime("%Y-%m-%d")

    if day:
        date_to = date_from
    elif month:
        next_month = datetime(year + int(month == 12), (month % 12) + 1, 1)
        date_to = (next_month - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        date_to = datetime(year, 12, 31).strftime("%Y-%m-%d")

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

    total_net = total_gross = total_vat = 0.0
    overdue = []
    soon_due = []
    now = datetime.now()

    for inv in invoices:
        netto = float(inv.get("netto") or 0)
        brutto = float(inv.get("brutto") or 0)
        vat = float(inv.get("tax") or 0)
        total_net += netto
        total_gross += brutto
        total_vat += vat

        payment_date = inv.get("paymentdate")
        paid_state = inv.get("paymentstate")

        if payment_date:
            pay_dt = datetime.strptime(payment_date, "%Y-%m-%d")
            if paid_state != "paid":
                if pay_dt < now:
                    overdue.append(inv)
                elif (pay_dt - now).days <= 3:
                    soon_due.append(inv)

    return {
        "total_invoices": len(invoices),
        "total_netto": round(total_net, 2),
        "total_brutto": round(total_gross, 2),
        "total_vat": round(total_vat, 2),
        "overdue_count": len(overdue),
        "overdue_sum": round(sum(float(i.get("brutto") or 0) for i in overdue), 2),
        "overdue": overdue,
        "soon_due_count": len(soon_due),
        "soon_due_invoices": soon_due,
    }
