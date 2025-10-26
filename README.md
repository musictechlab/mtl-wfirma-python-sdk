# wfirma-sdk-python

_Unofficial, minimal Python SDK for the wFirma.pl API (API Key & OAuth2)._  
**Status:** prototype for integrations. Before production, verify scopes, payloads and responses with official docs.

> This SDK focuses on a pragmatic subset: contractors, invoices (get/add/download/send), and company accounts. It exposes a low-level `call()` escape hatch for everything else.

---

## Install

```bash
pip install wfirma-sdk-python  # when published
poetry add wfirma-sdk-python
```

Python >= 3.9 recommended.

---

## Quickstart

```python
from wfirma_sdk import WFirmaAPIClient

client = WFirmaAPIClient(
    base_url="https://api2.wfirma.pl",
    company_id="YOUR_COMPANY_ID",   # optional but recommended

    # ---- Auth option A: API Key headers ----
    access_key="...",
    secret_key="...",
    app_key="...",

    # ---- OR Auth option B: OAuth2 ----
    # oauth2_token="eyJhbGciOi..."  # Bearer token
)

# Add contractor
resp = client.contractors.add({
    "name": "Nazwa kontrahenta",
    "zip": "12-345",
    "country": "PL",
    "tax_id_type": "custom",
    "nip": "1111111111",
})
print(resp)

# Get invoice
inv = client.invoices.get(12345678)
print(inv)

# Download invoice PDF link (valid for a short time on backend)
link = client.invoices.download(
    12345678,
    page="all",
    address=0,
    leaflet=0,
    duplicate=0,
    payment_cashbox_documents=0,
    warehouse_documents=0,
)
print(link["status"]["code"], link.get("response"))

# Send invoice by email
client.invoices.send(
    12345678,
    email="odbiorca@adres.pl",
    subject="Otrzymałeś fakturę",
    page="invoice",
    leaflet=0,
    duplicate=0,
    body="Przesyłam fakturę",
)
```

---

## Running Examples

To run the demo example:

```bash
# Clone the repository
git clone https://github.com/musictechlab/mtl-wfirma-python-sdk.git
cd mtl-wfirma-python-sdk

# Install dependencies with poetry
poetry install

# Set up your environment variables
cp .env.example .env  # if available, or create .env manually
# Edit .env with your credentials:
# WFIRMA_OAUTH_TOKEN=your_oauth_token
# WFIRMA_COMPANY_ID=your_company_id

# Run the demo
poetry run python examples/demo.py
```

The demo will fetch the 20 most recent invoices from your wFirma account.

---

## Authentication

### API Key (headers)

Place keys in headers (client does it for you):
- `accessKey`
- `secretKey`
- `appKey`

```python
client = WFirmaAPIClient(
    company_id="...",
    access_key="...",
    secret_key="...",
    app_key="...",
)
```

### OAuth2 (Bearer)
Use Authorization Code flow in your app to obtain an `access_token`. Pass it to the client:
```python
client = WFirmaAPIClient(
    company_id="...",
    oauth2_token="ACCESS_TOKEN_VALUE",  # adds Authorization: Bearer ... and ?oauth_version=2
)
```

> Tip: Regardless of auth method, remember `company_id` if your account has multiple companies.

---

## Modules covered

- `contractors` — `add`, `get`, `edit`, `find`
- `invoices` — `get`, `add`, `download`, `send`, `find` (custom XML)
- `company_accounts` — `find`, `get`
- `call(path, ...)` — low-level escape hatch

---

## Usage

### Contractors

```python
# add
client.contractors.add({
    "name": "ACME Sp. z o.o.",
    "zip": "00-000",
    "city": "Warszawa",
    "country": "PL",
    "tax_id_type": "nip",
    "nip": "1234567890",
})

# get
client.contractors.get(12345)

# edit
client.contractors.edit(12345, {"name": "ACME SA", "zip": "00-001"})

# find (basic paging/fields)
client.contractors.find(page=1, limit=50, fields=["Contractor.id", "Contractor.name"])
```

**Advanced `find`** — pass your own `<parameters>` as XML:
```python
parameters_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<api>
  <contractors>
    <parameters>
      <page>1</page>
      <limit>50</limit>
      <fields>
        <field>Contractor.id</field>
        <field>Contractor.name</field>
      </fields>
      <conditions>
        <condition>
          <field>name</field>
          <operator>like</operator>
          <value>ACME</value>
        </condition>
      </conditions>
      <order>
        <asc>name</asc>
      </order>
    </parameters>
  </contractors>
</api>"""
client.contractors.find(conditions_xml=parameters_xml)
```

### Invoices

```python
# get
client.invoices.get(12345678)
```

**add** — for complex nested structures use raw XML from wFirma docs:
```python
xml_body = b"""<api>
  <invoices>
    <invoice>
      <contractor>
        <name>Testowy kontrahent</name>
        <zip>10-100</zip>
        <city>Wrocław</city>
        <street>Prosta</street>
      </contractor>
      <type>correction</type>
      <parent_id>16679047</parent_id>
      <invoicecontents>
        <invoicecontent>
          <parent_id>19630727</parent_id>
          <name>produkt1</name>
          <count>1.0000</count>
          <price>11.00</price>
        </invoicecontent>
        <invoicecontent>
          <parent_id>19630791</parent_id>
          <name>produkt2</name>
          <count>1.0000</count>
          <price>11.00</price>
        </invoicecontent>
        <invoicecontent>
          <name>nowy - produkt3</name>
          <count>1.0000</count>
          <price>11.00</price>
        </invoicecontent>
      </invoicecontents>
    </invoice>
  </invoices>
</api>"""
client.invoices.add(invoice_xml_body=xml_body)
```

**download** — build `<parameters>` via helper:
```python
client.invoices.download(
    12345678,
    page="all", address=0, leaflet=0, duplicate=0,
    payment_cashbox_documents=0, warehouse_documents=0,
)
```

**send**
```python
client.invoices.send(
    12345678,
    email="odbiorca@adresmailowy123.pl",
    subject="Otrzymałeś fakturę",
    page="invoice",
    leaflet=0,
    duplicate=0,
    body="Przesyłam fakturę",
)
```

**find** — pass your own `<parameters>` XML for full control:
```python
invoices_find_xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<api>
  <invoices>
    <parameters>
      <page>1</page>
      <limit>20</limit>
      <fields>
        <field>Invoice.id</field>
        <field>Invoice.fullnumber</field>
        <field>Invoice.date</field>
        <field>InvoiceContent.name</field>
        <field>InvoiceContent.price</field>
      </fields>
      <conditions>
        <condition>
          <field>Invoice.remaining</field>
          <operator>gt</operator>
          <value>0</value>
        </condition>
      </conditions>
      <order>
        <desc>date</desc>
      </order>
    </parameters>
  </invoices>
</api>"""
client.invoices.find(parameters_xml=invoices_find_xml)
```

### Company accounts
```python
client.company_accounts.find()
client.company_accounts.get(999)
```

---

## Errors

- Network/HTTP/XML parsing errors ⇒ raises `WFirmaAPIError`.
- API-level status checking: if `<status><code>...</code></status>` is not `OK` (or `NO_CONTENT`), `WFirmaAPIError` is raised with the decoded response for inspection.

```python
from wfirma_sdk import WFirmaAPIError

try:
    client.invoices.get("bad-id")
except WFirmaAPIError as e:
    print(e, e.http_status, e.response)
```

---

## Tips & gotchas

- **Format:** SDK defaults to `inputFormat=xml&outputFormat=xml` and parses XML to Python dicts.
- **Multiple companies:** set `company_id` in the client to avoid accidental requests to the wrong company.
- **Temporary links:** `/invoices/download` returns a link that is valid only briefly (per backend rules).
- **Rate limits:** avoid bursts; consider backoff/retries on `TOTAL REQUESTS LIMIT EXCEEDED` or `TOTAL EXECUTION TIME LIMIT EXCEEDED`.
- **Escape hatch:** `client.call(path, method=..., params=..., body_xml=...)` to hit any endpoint not yet wrapped.

---

## Versioning

This SDK is intentionally small. Breaking changes may occur until 1.0. Pin versions in production.

---

## Contributing

Issues / PRs welcome. Keep the scope minimal and docs-linked.

---

## 🪪 License

MIT License — © 2025 **MusicTech Lab**  
Built with ❤️ by MusicTech Lab.
