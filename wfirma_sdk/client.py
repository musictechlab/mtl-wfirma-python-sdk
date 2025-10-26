from __future__ import annotations

import os
from typing import Any, Dict, Optional

import httpx
import xml.etree.ElementTree as ET

from .exceptions import WFirmaAPIError, WFirmaAuthError
from .resources import ContractorsResource, InvoicesResource, CompanyAccountsResource


DEFAULT_BASE_URL = os.getenv("WFIRMA_API_BASE", "https://api2.wfirma.pl")


class _HeaderAuth(httpx.Auth):
    """Custom httpx.Auth that injects required headers (API Key or Bearer)."""

    def __init__(
        self,
        *,
        access_key: str | None = None,
        secret_key: str | None = None,
        app_key: str | None = None,
        bearer: str | None = None,
    ):
        self.access_key = access_key
        self.secret_key = secret_key
        self.app_key = app_key
        self.bearer = bearer

    def auth_flow(self, request: httpx.Request):
        if self.bearer:
            request.headers["Authorization"] = f"Bearer {self.bearer}"
        else:
            if self.access_key:
                request.headers["accessKey"] = self.access_key
            if self.secret_key:
                request.headers["secretKey"] = self.secret_key
            if self.app_key:
                request.headers["appKey"] = self.app_key
        yield request


class WFirmaAPIClient:
    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        company_id: Optional[str] = os.getenv("WFIRMA_COMPANY_ID"),
        # API Key headers:
        access_key: Optional[str] = os.getenv("WFIRMA_ACCESS_KEY"),
        secret_key: Optional[str] = os.getenv("WFIRMA_SECRET_KEY"),
        app_key: Optional[str] = os.getenv("WFIRMA_APP_KEY"),
        # OAuth2:
        oauth2_token: Optional[str] = os.getenv("WFIRMA_OAUTH_TOKEN"),
        timeout: Optional[float] = 30.0,
        transport: Optional[httpx.BaseTransport] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.company_id = company_id

        # Decide auth
        if oauth2_token:
            auth = _HeaderAuth(bearer=oauth2_token)
        elif access_key and secret_key and app_key:
            auth = _HeaderAuth(
                access_key=access_key, secret_key=secret_key, app_key=app_key
            )
        else:
            raise WFirmaAuthError(
                "Provide either OAuth2 token or API Key trio (accessKey/secretKey/appKey)."
            )

        self._client = httpx.Client(
            base_url=self.base_url,
            auth=auth,
            timeout=timeout,
            transport=transport,
            headers={
                "Accept": "application/xml",
                "Content-Type": "application/xml; charset=utf-8",
                **(headers or {}),
            },
        )

        # resources
        self.contractors = ContractorsResource(self)
        self.invoices = InvoicesResource(self)
        self.company_accounts = CompanyAccountsResource(self)

    # ---------- XML helpers ----------
    @staticmethod
    def _etree_to_dict(elem: ET.Element):
        children = list(elem)
        if not children:
            return (elem.text or "").strip()
        grouped: dict[str, list[ET.Element]] = {}
        for c in children:
            grouped.setdefault(c.tag, []).append(c)
        out: dict[str, Any] = {}
        for tag, nodes in grouped.items():
            if len(nodes) == 1:
                out[tag] = WFirmaAPIClient._etree_to_dict(nodes[0])
            else:
                out[tag] = [WFirmaAPIClient._etree_to_dict(n) for n in nodes]
        return out

    @staticmethod
    def _wrap_module_body(
        module_plural: str, record_name: str, fields: Dict[str, Any]
    ) -> bytes:
        api = ET.Element("api")
        mod = ET.SubElement(api, module_plural)
        rec = ET.SubElement(mod, record_name)
        for k, v in fields.items():
            node = ET.SubElement(rec, k)
            node.text = str(v)
        return ET.tostring(api, encoding="utf-8", xml_declaration=True)

    def _post_module_record(
        self, path: str, *, module_plural: str, record_name: str, fields: Dict[str, Any]
    ) -> Dict[str, Any]:
        xml = self._wrap_module_body(module_plural, record_name, fields)
        return self._request("POST", path, data=xml)

    @staticmethod
    def _wrap_parameters(module_plural: str, params: Dict[str, Any]) -> bytes:
        api = ET.Element("api")
        mod = ET.SubElement(api, module_plural)
        params_el = ET.SubElement(mod, "parameters")
        for name, value in params.items():
            p = ET.SubElement(params_el, "parameter")
            n = ET.SubElement(p, "name")
            n.text = str(name)
            v = ET.SubElement(p, "value")
            v.text = str(value)
        return ET.tostring(api, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _build_parameters_xml(
        module_plural: str,
        *,
        page: int | None = None,
        limit: int | None = None,
        fields: list[str] | None = None,
    ) -> bytes:
        api = ET.Element("api")
        mod = ET.SubElement(api, module_plural)
        params_el = ET.SubElement(mod, "parameters")
        if page is not None:
            p = ET.SubElement(params_el, "page")
            p.text = str(page)
        if limit is not None:
            l = ET.SubElement(params_el, "limit")
            l.text = str(limit)
        if fields:
            f = ET.SubElement(params_el, "fields")
            for fld in fields:
                fe = ET.SubElement(f, "field")
                fe.text = fld
        return ET.tostring(api, encoding="utf-8", xml_declaration=True)

    # ---------- HTTP core ----------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Dict[str, Any] | None = None,
        data: bytes | str | None = None,
    ) -> Dict[str, Any]:
        q = {"inputFormat": "xml", "outputFormat": "xml"}
        if self.company_id:
            q["company_id"] = self.company_id
        # OAuth2 requires oauth_version=2 param
        if "Authorization" in self._client.headers and self._client.headers[
            "Authorization"
        ].startswith("Bearer "):
            # header set via Auth flow at request time; here we pass query param
            q["oauth_version"] = "2"

        if params:
            q.update(params)

        resp = self._client.request(method, path, params=q, data=data)
        content = (resp.content or b"").strip()

        if not content:
            if not resp.is_success:
                raise WFirmaAPIError(resp.status_code, "HTTP error without body", None)
            return {"status": {"code": "NO_CONTENT"}}

        try:
            root = ET.fromstring(content)
        except Exception as e:
            raise WFirmaAPIError(resp.status_code, f"Failed to parse XML: {e}", content)

        # If wrapped in <api>, unwrap
        if root.tag == "api":
            data_dict: Dict[str, Any] = {}
            for child in root:
                data_dict.setdefault(child.tag, self._etree_to_dict(child))
        else:
            data_dict = self._etree_to_dict(root)

        # status check
        status_code = None
        st = data_dict.get("status")
        if isinstance(st, dict):
            status_code = st.get("code")
        if status_code and status_code not in ("OK", "NO_CONTENT"):
            raise WFirmaAPIError(
                resp.status_code, f"API status != OK: {status_code}", data_dict
            )

        return data_dict

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
