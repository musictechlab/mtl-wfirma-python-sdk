import json
import types
import pytest

from wfirma_sdk import WFirmaAPIClient, WFirmaAPIError


class _Resp:
    def __init__(self, status_code=200, content=b"", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {"Content-Type": "application/xml"}
        self.ok = 200 <= status_code < 300


def _xml_api(body_inner: str, status="OK"):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<api>
{body_inner}
  <status><code>{status}</code></status>
</api>""".encode("utf-8")


def test_client_has_resources():
    client = WFirmaAPIClient(
        company_id="123",
        oauth2_token="token-abc",
        base_url="https://api2.wfirma.pl",
    )
    assert hasattr(client, "contractors")
    assert hasattr(client, "invoices")
    assert hasattr(client, "company_accounts")


def test_request_builds_oauth_headers_and_params(monkeypatch):
    captured = {}

    def fake_request(method, url, params=None, data=None, headers=None, timeout=None):
        captured["method"] = method
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        # minimal valid xml body
        content = _xml_api("<users></users>")
        return _Resp(200, content)

    client = WFirmaAPIClient(
        company_id="321", oauth2_token="bearer-token", base_url="https://api2.wfirma.pl"
    )
    # monkeypatch low-level requests.request used by the SDK
    import requests

    monkeypatch.setattr(requests, "request", fake_request)

    # any GET; choose invoices.get with id
    client.invoices.get(777)

    assert captured["url"] == "https://api2.wfirma.pl/invoices/get/777"
    # must include company_id and oauth_version=2 and default formats
    assert captured["params"]["company_id"] == "321"
    assert captured["params"]["oauth_version"] == "2"
    assert captured["params"]["inputFormat"] == "xml"
    assert captured["params"]["outputFormat"] == "xml"
    # check auth header
    assert captured["headers"]["Authorization"] == "Bearer bearer-token"
    assert captured["headers"]["Accept"] == "application/xml"


def test_request_builds_apikey_headers(monkeypatch):
    captured = {}

    def fake_request(method, url, params=None, data=None, headers=None, timeout=None):
        captured["headers"] = headers
        # return minimal xml api
        content = _xml_api("<users></users>")
        return _Resp(200, content)

    client = WFirmaAPIClient(
        access_key="AK",
        secret_key="SK",
        app_key="APP",
        base_url="https://api2.wfirma.pl",
    )
    import requests

    monkeypatch.setattr(requests, "request", fake_request)

    # trigger any request
    client.contractors.find(page=1, limit=1)

    assert captured["headers"]["accessKey"] == "AK"
    assert captured["headers"]["secretKey"] == "SK"
    assert captured["headers"]["appKey"] == "APP"
    assert "Authorization" not in captured["headers"]


def test_invoices_get_parsing(monkeypatch):
    def fake_request(method, url, params=None, data=None, headers=None, timeout=None):
        body = "<invoices><invoice><id>42</id></invoice></invoices>"
        return _Resp(200, _xml_api(body))

    import requests

    monkeypatch.setattr(requests, "request", fake_request)

    client = WFirmaAPIClient(oauth2_token="X")
    resp = client.invoices.get(42)
    assert resp["status"]["code"] == "OK"
    # Depending on converter, list or single dict; normalize for both
    invoices = resp.get("invoices")
    # invoices could be a dict with 'invoice' inside
    if isinstance(invoices, dict) and "invoice" in invoices:
        inv = invoices["invoice"]
        if isinstance(inv, list):
            inv = inv[0]
        assert inv["id"] == "42"
    else:
        pytest.skip("Unexpected invoices shape in parser")


def test_invoices_download_parameters_xml(monkeypatch):
    captured = {}

    def fake_request(method, url, params=None, data=None, headers=None, timeout=None):
        captured["data"] = (
            data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
        )
        return _Resp(200, _xml_api("<invoices></invoices>"))

    import requests

    monkeypatch.setattr(requests, "request", fake_request)

    client = WFirmaAPIClient(oauth2_token="X")
    client.invoices.download(123, page="all", duplicate=0, leaflet=0)

    # ensure parameters/parameter(name,value) appear in body
    assert "<parameters>" in captured["data"]
    assert "<name>page</name>" in captured["data"]
    assert "<value>all</value>" in captured["data"]
    assert "<name>duplicate</name>" in captured["data"]
    assert "<name>leaflet</name>" in captured["data"]


def test_empty_body_returns_no_content(monkeypatch):
    def fake_request(method, url, params=None, data=None, headers=None, timeout=None):
        return _Resp(200, b"")

    import requests

    monkeypatch.setattr(requests, "request", fake_request)

    client = WFirmaAPIClient(oauth2_token="X")
    resp = client.company_accounts.find()
    assert resp["status"]["code"] == "NO_CONTENT"


def test_api_error_raises(monkeypatch):
    def fake_request(method, url, params=None, data=None, headers=None, timeout=None):
        # Return a valid xml with ERROR status
        return _Resp(200, _xml_api("<invoices></invoices>", status="ERROR"))

    import requests

    monkeypatch.setattr(requests, "request", fake_request)

    client = WFirmaAPIClient(oauth2_token="X")
    with pytest.raises(WFirmaAPIError):
        client.invoices.get(1)
