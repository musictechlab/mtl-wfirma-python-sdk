from __future__ import annotations
from typing import Dict, Any


class CompanyAccountsResource:
    def __init__(self, client):
        self._client = client

    def find(self) -> Dict[str, Any]:
        """GET /company_accounts/find"""
        return self._client._request("GET", "/company_accounts/find")

    def get(self, account_id: int | str) -> Dict[str, Any]:
        """GET /company_accounts/get/{id}"""
        return self._client._request("GET", f"/company_accounts/get/{account_id}")
