from __future__ import annotations
from typing import Any, Dict


class ContractorsResource:
    def __init__(self, client):
        self._client = client

    def add(self, contractor_fields: Dict[str, Any]) -> Dict[str, Any]:
        """POST /contractors/add (XML body).
        Wraps fields into:
        <api><contractors><contractor>...</contractor></contractors></api>
        """
        return self._client._post_module_record(
            "/contractors/add",
            module_plural="contractors",
            record_name="contractor",
            fields=contractor_fields,
        )

    def get(self, contractor_id: int | str) -> Dict[str, Any]:
        """GET /contractors/get/{id}"""
        return self._client._request("GET", f"/contractors/get/{contractor_id}")

    def edit(self, contractor_id: int | str, fields: Dict[str, Any]) -> Dict[str, Any]:
        """POST /contractors/edit/{id} (XML body)"""
        return self._client._post_module_record(
            f"/contractors/edit/{contractor_id}",
            module_plural="contractors",
            record_name="contractor",
            fields=fields,
        )

    def find(
        self,
        parameters_xml: bytes | str | None = None,
        *,
        page: int | None = None,
        limit: int | None = None,
        fields: list[str] | None = None,
    ) -> Dict[str, Any]:
        """POST /contractors/find with <parameters> in body. Provide full XML or basic paging via kwargs."""
        if parameters_xml is not None:
            return self._client._request(
                "POST", "/contractors/find", data=parameters_xml
            )
        # basic builder
        xml = self._client._build_parameters_xml(
            "contractors", page=page, limit=limit, fields=fields
        )
        return self._client._request("POST", "/contractors/find", data=xml)
