from __future__ import annotations

from dataclasses import dataclass
from base64 import b64encode
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen
import json
import os
import re
import ssl


class ServiceNowConfigurationError(ValueError):
    pass


class ServiceNowAPIError(RuntimeError):
    pass


class ServiceNowConflictError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServiceNowCredentials:
    instance: str
    username: str | None = None
    password: str | None = None
    token: str | None = None

    @classmethod
    def from_env(cls) -> "ServiceNowCredentials":
        instance = os.getenv("SN_INSTANCE", "").strip().rstrip("/")
        username = os.getenv("SN_USERNAME", "").strip() or None
        password = os.getenv("SN_PASSWORD", "") or None
        token = os.getenv("SN_TOKEN", "").strip() or None
        if not instance:
            raise ServiceNowConfigurationError("SN_INSTANCE is required.")
        if not instance.startswith("https://"):
            raise ServiceNowConfigurationError("SN_INSTANCE must use HTTPS.")
        if not token and not (username and password):
            raise ServiceNowConfigurationError(
                "Set SN_TOKEN or both SN_USERNAME and SN_PASSWORD."
            )
        return cls(instance, username, password, token)


class ServiceNowTableClient:
    """Small standard-library client for the ServiceNow Table API."""

    SAFE_QUERY_VALUE = re.compile(r"^[A-Za-z0-9_.:@/ -]+$")

    def __init__(
        self,
        credentials: ServiceNowCredentials,
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.credentials = credentials
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.credentials.token:
            headers["Authorization"] = f"Bearer {self.credentials.token}"
        else:
            raw = f"{self.credentials.username}:{self.credentials.password}".encode()
            headers["Authorization"] = "Basic " + b64encode(raw).decode()
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.credentials.instance}{path}"
        if query:
            url += "?" + urlencode(query)
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(url, data=body, headers=self._headers(), method=method)
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                text = response.read().decode("utf-8")
                return json.loads(text) if text else {}
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise ServiceNowAPIError(
                f"ServiceNow returned HTTP {exc.code} for {method} {path}: {detail}"
            ) from exc
        except URLError as exc:
            raise ServiceNowAPIError(
                f"Could not reach ServiceNow for {method} {path}: {exc.reason}"
            ) from exc

    @staticmethod
    def _table_path(table: str, sys_id: str | None = None) -> str:
        safe_table = quote(table, safe="_")
        path = f"/api/now/table/{safe_table}"
        if sys_id:
            path += "/" + quote(sys_id, safe="")
        return path

    def get_records(
        self,
        table: str,
        *,
        encoded_query: str = "",
        fields: list[str] | None = None,
        limit: int = 100,
        display_value: str = "false",
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {
            "sysparm_limit": max(1, min(limit, 10000)),
            "sysparm_display_value": display_value,
            "sysparm_exclude_reference_link": "true",
        }
        if encoded_query:
            query["sysparm_query"] = encoded_query
        if fields:
            query["sysparm_fields"] = ",".join(fields)
        response = self._request("GET", self._table_path(table), query=query)
        result = response.get("result", [])
        if not isinstance(result, list):
            raise ServiceNowAPIError("Expected a list result from Table API GET.")
        return result

    def create_record(self, table: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._request("POST", self._table_path(table), payload=payload)
        result = response.get("result")
        if not isinstance(result, dict):
            raise ServiceNowAPIError("Expected an object result from Table API POST.")
        return result

    def update_record(
        self,
        table: str,
        sys_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        response = self._request(
            "PATCH", self._table_path(table, sys_id), payload=payload
        )
        result = response.get("result")
        if not isinstance(result, dict):
            raise ServiceNowAPIError("Expected an object result from Table API PATCH.")
        return result

    def upsert_by_field(
        self,
        table: str,
        *,
        key_field: str,
        key_value: str,
        payload: dict[str, Any],
    ) -> tuple[str, dict[str, Any]]:
        if not self.SAFE_QUERY_VALUE.fullmatch(key_value):
            raise ValueError("Correlation value contains unsupported query characters.")
        matches = self.get_records(
            table,
            encoded_query=f"{key_field}={key_value}",
            fields=["sys_id", key_field],
            limit=2,
        )
        if len(matches) > 1:
            raise ServiceNowConflictError(
                f"Multiple {table} records use {key_field}={key_value}."
            )
        if matches:
            sys_id = str(matches[0]["sys_id"])
            return "UPDATED", self.update_record(table, sys_id, payload)
        return "CREATED", self.create_record(table, payload)

    def discover_dictionary_fields(self, table: str) -> list[dict[str, Any]]:
        return self.get_records(
            "sys_dictionary",
            encoded_query=f"name={table}^elementISNOTEMPTY^active=true",
            fields=[
                "element", "column_label", "internal_type", "max_length",
                "mandatory", "reference", "active", "name"
            ],
            limit=1000,
            display_value="true",
        )
