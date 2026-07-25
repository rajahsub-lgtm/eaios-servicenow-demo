from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class TableClientProtocol(Protocol):
    def get_records(self, table: str, *, encoded_query: str = "", fields=None, limit=100, display_value="false"): ...
    def create_record(self, table: str, payload: dict[str, Any]): ...
    def update_record(self, table: str, sys_id: str, payload: dict[str, Any]): ...
    def upsert_by_field(self, table: str, *, key_field: str, key_value: str, payload: dict[str, Any]): ...


@dataclass(frozen=True)
class SyncResult:
    action: str
    table: str
    correlation_field: str
    correlation_id: str
    sys_id: str
    record: dict[str, Any]


class ServiceNowAssessmentRepository:
    def __init__(self, client: TableClientProtocol, table: str, correlation_field: str) -> None:
        self.client = client
        self.table = table
        self.correlation_field = correlation_field

    def upsert(self, correlation_id: str, payload: dict[str, Any]) -> SyncResult:
        action, record = self.client.upsert_by_field(
            self.table,
            key_field=self.correlation_field,
            key_value=correlation_id,
            payload=payload,
        )
        return SyncResult(
            action=action,
            table=self.table,
            correlation_field=self.correlation_field,
            correlation_id=correlation_id,
            sys_id=str(record.get("sys_id", "")),
            record=record,
        )

    def get_by_correlation(self, correlation_id: str, fields: list[str]) -> dict[str, Any] | None:
        rows = self.client.get_records(
            self.table,
            encoded_query=f"{self.correlation_field}={correlation_id}",
            fields=fields,
            limit=2,
        )
        if len(rows) > 1:
            raise RuntimeError("Duplicate ServiceNow assessment correlation IDs detected.")
        return rows[0] if rows else None
