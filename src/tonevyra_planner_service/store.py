"""Durable local idempotency store for the Planner Service."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
from threading import Lock
from typing import Any


class IdempotencyConflictError(Exception):
    pass


class IdempotencyStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def ready(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            probe = self.path.parent / ".ready"
            probe.write_text("ready", encoding="ascii")
            probe.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def execute(
        self,
        *,
        principal_hash: str,
        idempotency_key: str,
        input_digest: str,
        create_response,
    ) -> tuple[dict[str, Any], bool]:
        record_key = hashlib.sha256(f"{principal_hash}:{idempotency_key}".encode("utf-8")).hexdigest()
        with self._lock:
            records = self._load()
            existing = records.get(record_key)
            if existing is not None:
                if existing.get("input_digest") != input_digest:
                    raise IdempotencyConflictError(idempotency_key)
                response = deepcopy(existing["response"])
                response["replayed"] = True
                return response, True
            response = create_response()
            records[record_key] = {"input_digest": input_digest, "response": response}
            self._save(records)
            return deepcopy(response), False

    def _load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save(self, records: dict[str, Any]) -> None:
        temp = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(records, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.path)
