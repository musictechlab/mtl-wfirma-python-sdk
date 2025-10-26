from __future__ import annotations
from typing import Any, Dict


class InvoicesResource:
    def __init__(self, client):
        self._client = client

    def get(self, invoice_id: int | str) -> Dict[str, Any]:
        """GET /invoices/get/{id}"""
        return self._client._request("GET", f"/invoices/get/{invoice_id}")

    def add(
        self,
        *,
        invoice_xml_body: bytes | str | None = None,
        invoice_fields: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """POST /invoices/add. Pass full XML body or minimal dict (flat fields)."""
        if invoice_xml_body is not None:
            return self._client._request("POST", "/invoices/add", data=invoice_xml_body)
        if invoice_fields is None:
            raise ValueError("Provide either invoice_xml_body or invoice_fields")
        xml = self._client._wrap_module_body("invoices", "invoice", invoice_fields)
        return self._client._request("POST", "/invoices/add", data=xml)

    def download(self, invoice_id: int | str, **parameters) -> Dict[str, Any]:
        """POST /invoices/download/{id} with <parameters> body."""
        xml = self._client._wrap_parameters("invoices", parameters or {"page": "all"})
        return self._client._request(
            "POST", f"/invoices/download/{invoice_id}", data=xml
        )

    def send(self, invoice_id: int | str, **parameters) -> Dict[str, Any]:
        """POST /invoices/send/{id} with <parameters> body (email/subject/page/...)."""
        xml = self._client._wrap_parameters("invoices", parameters)
        return self._client._request("POST", f"/invoices/send/{invoice_id}", data=xml)

    def find(self, parameters_xml: bytes | str) -> Dict[str, Any]:
        """POST /invoices/find with given <parameters> XML"""
        return self._client._request("POST", "/invoices/find", data=parameters_xml)
