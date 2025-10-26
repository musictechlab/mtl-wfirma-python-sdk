# FastAPI example for wFirma invoices

## Features

- **Web Interface**: Beautiful HTML interface for viewing invoices and summaries
- **API Endpoints**: RESTful API for programmatic access
- **Filtering**: Filter invoices by year, month, and day
- **Summary Dashboard**: Overview of invoice statistics and payment status

## Requirements

```text
fastapi
uvicorn
python-dotenv
jinja2
wfirma-sdk-python  # lokalnie lub z repo
```

## Run locally

```bash
cd examples/fastapi_app
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# auth config (pick one)
export WFIRMA_OAUTH_TOKEN="your_token"
# or
export WFIRMA_ACCESS_KEY="..."
export WFIRMA_SECRET_KEY="..."
export WFIRMA_APP_KEY="..."
export WFIRMA_COMPANY_ID="123456"

uvicorn main:app --reload
```

Then open your browser to:
- **Web Interface**: http://localhost:8000/
- **API Documentation**: http://localhost:8000/docs

## Web Interface

### Main Pages
- **`/`** - Invoices list with filtering and table view
- **`/summary`** - Dashboard with invoice statistics and payment status

### Features
- Responsive design with modern UI
- Real-time filtering by date range
- Invoice status indicators (paid, overdue, pending)
- Payment due date tracking
- Summary cards with key metrics

## API Endpoints

### `GET /api/invoices`
- Parameters: `year`, `month`, `day`
- Returns full list of invoices for selected period.

Examples:
- `/api/invoices?year=2024`
- `/api/invoices?year=2025&month=10`
- `/api/invoices?year=2025&month=10&day=26`

### `GET /api/invoices/summary`
Aggregated statistics for invoices in the given range:
- total count
- sum netto / brutto / VAT
- overdue invoices and their total
- invoices due within 3 days

### Example response (summary)
```json
{
  "status": "OK",
  "filters": {"from": "2025-01-01", "to": "2025-10-26"},
  "generated_at": "2025-10-26T12:00:00Z",
  "summary": {
    "total_count": 32,
    "sum_netto": "15500.50",
    "sum_brutto": "19065.61",
    "sum_tax": "3565.11",
    "sum_paid": "18000.00",
    "overdue": {"count": 3, "sum_brutto": "2400.00"},
    "upcoming_due_in_3_days": {"count": 2}
  }
}
```