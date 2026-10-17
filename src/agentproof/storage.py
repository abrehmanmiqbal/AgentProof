"""Local SQLite persistence for cases and runs (stdlib only, offline, no accounts).

Design notes:
- All SQL is parameterized; stored content is data and is never executed.
- Schema changes are explicit, ordered migrations tracked via ``PRAGMA user_version``.
  A database newer than this code is refused rather than silently misread.
- Each run records the SHA-256 of the exact case JSON it ran against, so a result can
  always be tied to the precise case definition (case edits do not rewrite history).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .models import RegressionCase, RegressionResult

MAX_JSON_BYTES = 1_000_000  # per stored case or result
MAX_LABEL_LENGTH = 64

# Ordered migrations. Index i upgrades schema version i -> i+1. Never edit shipped entries;
# append new ones.
MIGRATIONS: list[str] = [
    """
    CREATE TABLE cases (
        case_id     TEXT PRIMARY KEY,
        case_json   TEXT NOT NULL,
        case_hash   TEXT NOT NULL,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    );
    CREATE TABLE runs (
        run_id      INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id     TEXT NOT NULL REFERENCES cases(case_id) ON DELETE CASCADE,
        case_hash   TEXT NOT NULL,
        label       TEXT NOT NULL,
        runner_name TEXT NOT NULL,
        passed      INTEGER NOT NULL CHECK (passed IN (0, 1)),
        result_json TEXT NOT NULL,
        created_at  TEXT NOT NULL
    );
    CREATE INDEX idx_runs_case ON runs(case_id, run_id);
    """,
]
SCHEMA_VERSION = len(MIGRATIONS)


class StorageError(Exception):
    """Base class for predictable persistence errors."""


class CaseExistsError(StorageError):
    pass


class NotFoundError(StorageError):
    pass


class SchemaTooNewError(StorageError):
    pass


class PayloadTooLargeError(StorageError):
    pass


class StoredRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: int
    case_id: str
    case_hash: str
    label: str
    runner_name: str
    created_at: str
    result: RegressionResult


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _canonical_json(model: BaseModel) -> str:
    return json.dumps(
        model.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def case_hash(case: RegressionCase) -> str:
    return hashlib.sha256(_canonical_json(case).encode("utf-8")).hexdigest()


def _check_size(text: str, what: str) -> None:
    if len(text.encode("utf-8")) > MAX_JSON_BYTES:
        raise PayloadTooLargeError(f"{what} exceeds {MAX_JSON_BYTES} bytes")


class Repository:
    def __init__(self, path: str | Path = ":memory:") -> None:
        try:
            self._conn = sqlite3.connect(str(path))
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._migrate()
        except sqlite3.Error as exc:
            conn = getattr(self, "_conn", None)
            if conn is not None:
                conn.close()
            raise StorageError(f"Cannot open database '{path}': {exc}") from exc

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Repository:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def schema_version(self) -> int:
        return int(self._conn.execute("PRAGMA user_version").fetchone()[0])

    def _migrate(self) -> None:
        version = self.schema_version
        if version > SCHEMA_VERSION:
            raise SchemaTooNewError(
                f"Database schema v{version} is newer than supported v{SCHEMA_VERSION}"
            )
        for target in range(version, SCHEMA_VERSION):
            try:
                self._conn.executescript("BEGIN;" + MIGRATIONS[target] + "COMMIT;")
                # user_version cannot be parameterized; target is an int we control.
                self._conn.execute(f"PRAGMA user_version = {target + 1}")
            except sqlite3.Error:
                self._conn.rollback()
                raise

    # ---- cases -------------------------------------------------------------------
    def save_case(self, case: RegressionCase, *, overwrite: bool = False) -> str:
        """Store a case; returns its content hash. Refuses to replace unless overwrite."""
        payload = _canonical_json(case)
        _check_size(payload, "case")
        digest = case_hash(case)
        now = _now()
        exists = self._conn.execute(
            "SELECT 1 FROM cases WHERE case_id = ?", (case.case_id,)
        ).fetchone()
        if exists and not overwrite:
            raise CaseExistsError(f"Case '{case.case_id}' already exists")
        if exists:
            self._conn.execute(
                "UPDATE cases SET case_json=?, case_hash=?, updated_at=? WHERE case_id=?",
                (payload, digest, now, case.case_id),
            )
        else:
            self._conn.execute(
                "INSERT INTO cases(case_id, case_json, case_hash, created_at, updated_at)"
                " VALUES (?,?,?,?,?)",
                (case.case_id, payload, digest, now, now),
            )
        self._conn.commit()
        return digest

    def get_case(self, case_id: str) -> RegressionCase:
        row = self._conn.execute(
            "SELECT case_json FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Case '{case_id}' not found")
        return RegressionCase.model_validate_json(row[0])

    def list_case_ids(self) -> list[str]:
        rows = self._conn.execute("SELECT case_id FROM cases ORDER BY case_id").fetchall()
        return [r[0] for r in rows]

    def delete_case(self, case_id: str) -> None:
        cur = self._conn.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))
        self._conn.commit()
        if cur.rowcount == 0:
            raise NotFoundError(f"Case '{case_id}' not found")

    # ---- runs --------------------------------------------------------------------
    def record_run(
        self, case: RegressionCase, result: RegressionResult, *, label: str, runner_name: str
    ) -> int:
        """Persist a run of ``case``. The case must already be saved."""
        if not label or len(label) > MAX_LABEL_LENGTH:
            raise StorageError(f"label must be 1-{MAX_LABEL_LENGTH} characters")
        if result.case_id != case.case_id:
            raise StorageError("result.case_id does not match case.case_id")
        payload = _canonical_json(result)
        _check_size(payload, "result")
        if not self._conn.execute(
            "SELECT 1 FROM cases WHERE case_id = ?", (case.case_id,)
        ).fetchone():
            raise NotFoundError(f"Case '{case.case_id}' must be saved before recording runs")
        cur = self._conn.execute(
            "INSERT INTO runs(case_id, case_hash, label, runner_name, passed, result_json,"
            " created_at) VALUES (?,?,?,?,?,?,?)",
            (case.case_id, case_hash(case), label, runner_name, int(result.passed), payload, _now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    @staticmethod
    def _row_to_run(row: tuple) -> StoredRun:
        return StoredRun(
            run_id=row[0],
            case_id=row[1],
            case_hash=row[2],
            label=row[3],
            runner_name=row[4],
            created_at=row[5],
            result=RegressionResult.model_validate_json(row[6]),
        )

    _RUN_COLS = "run_id, case_id, case_hash, label, runner_name, created_at, result_json"

    def get_run(self, run_id: int) -> StoredRun:
        row = self._conn.execute(
            f"SELECT {self._RUN_COLS} FROM runs WHERE run_id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Run {run_id} not found")
        return self._row_to_run(row)

    def list_runs(self, case_id: str) -> list[StoredRun]:
        rows = self._conn.execute(
            f"SELECT {self._RUN_COLS} FROM runs WHERE case_id = ? ORDER BY run_id", (case_id,)
        ).fetchall()
        return [self._row_to_run(r) for r in rows]
