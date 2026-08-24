from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

from sensecllm.harness.state import RunState, utc_now


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _first(mapping: Any, keys: tuple[str, ...]) -> str:
    if not isinstance(mapping, dict):
        return ""
    for key in keys:
        value = mapping.get(key)
        if value not in (None, ""):
            return str(value)
    return ""


class EpisodicMemoryStore:
    """Lightweight historical case and verification-result memory.

    It is intentionally separate from literature RAG. A remembered case is a
    prior for future planning, never evidence about a new target device.
    """

    def __init__(self, database: Path) -> None:
        self.database = database.expanduser().resolve()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS cases (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL UNIQUE,
                    device_model TEXT NOT NULL DEFAULT '',
                    sensor_type TEXT NOT NULL DEFAULT '',
                    input_path TEXT NOT NULL,
                    report_path TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS findings (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL DEFAULT '',
                    mechanism TEXT NOT NULL DEFAULT '',
                    component TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    confidence TEXT NOT NULL DEFAULT '',
                    payload_json TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_cases_device ON cases(device_model, sensor_type);
                CREATE INDEX IF NOT EXISTS idx_findings_lookup
                    ON findings(kind, mechanism, status);

                CREATE TABLE IF NOT EXISTS verification_results (
                    id TEXT PRIMARY KEY,
                    case_id TEXT NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
                    vulnerability_name TEXT NOT NULL,
                    mechanism_name TEXT NOT NULL DEFAULT '',
                    outcome TEXT NOT NULL,
                    notes TEXT NOT NULL DEFAULT '',
                    evidence TEXT NOT NULL DEFAULT '',
                    recorded_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_verification_outcome
                    ON verification_results(outcome, mechanism_name);

                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    citations_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_conversation_run
                    ON conversation_messages(run_id, created_at);
                """
            )

    def remember_run(self, state: RunState) -> str:
        data_dir = state.data_dir
        step1 = _read_json(data_dir / "step1_output.json", {})
        graph = _read_json(data_dir / "step2_mechanism_paths.json", {})
        vulnerabilities = _read_json(data_dir / "step3_vulnerability_items.json", [])
        experiments = _read_json(data_dir / "step4_single_results.json", [])

        sensor_info = step1.get("sensor_info", {}) if isinstance(step1, dict) else {}
        device_model = _first(
            sensor_info,
            ("model", "sensor_model", "device_model", "product_model", "型号"),
        ) or _first(graph, ("sensor_model",))
        sensor_type = _first(
            sensor_info,
            ("sensor_type", "type", "category", "传感器类型", "类型"),
        ) or str(step1.get("rag_input", "") if isinstance(step1, dict) else "")

        accepted = graph.get("accepted_paths", []) if isinstance(graph, dict) else []
        summary = (
            f"accepted_paths={len(accepted)}; "
            f"vulnerabilities={len(vulnerabilities) if isinstance(vulnerabilities, list) else 0}; "
            f"experiments={len(experiments) if isinstance(experiments, list) else 0}"
        )
        now = utc_now()

        with self._connect() as connection:
            existing = connection.execute(
                "SELECT id, created_at FROM cases WHERE run_id = ?", (state.run_id,)
            ).fetchone()
            case_id = str(existing["id"]) if existing else str(uuid.uuid4())
            created_at = str(existing["created_at"]) if existing else now
            connection.execute(
                """
                INSERT INTO cases (
                    id, run_id, device_model, sensor_type, input_path,
                    report_path, summary, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    device_model=excluded.device_model,
                    sensor_type=excluded.sensor_type,
                    input_path=excluded.input_path,
                    report_path=excluded.report_path,
                    summary=excluded.summary,
                    updated_at=excluded.updated_at
                """,
                (
                    case_id,
                    state.run_id,
                    device_model,
                    sensor_type,
                    state.input_path,
                    state.report_path,
                    summary,
                    created_at,
                    now,
                ),
            )
            connection.execute("DELETE FROM findings WHERE case_id = ?", (case_id,))
            self._insert_path_findings(connection, case_id, accepted)
            self._insert_vulnerability_findings(connection, case_id, vulnerabilities)
            self._insert_experiment_findings(connection, case_id, experiments)
        return case_id

    def _insert_finding(
        self,
        connection: sqlite3.Connection,
        case_id: str,
        kind: str,
        payload: dict[str, Any],
        *,
        name: str = "",
        mechanism: str = "",
        component: str = "",
        status: str = "",
        confidence: str = "",
    ) -> None:
        connection.execute(
            """
            INSERT INTO findings (
                id, case_id, kind, name, mechanism, component,
                status, confidence, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                case_id,
                kind,
                name,
                mechanism,
                component,
                status,
                confidence,
                json.dumps(payload, ensure_ascii=False),
            ),
        )

    def _insert_path_findings(
        self, connection: sqlite3.Connection, case_id: str, paths: Any
    ) -> None:
        for path in paths if isinstance(paths, list) else []:
            if not isinstance(path, dict):
                continue
            mechanisms = path.get("mechanism_instances") or [{}]
            for mechanism in mechanisms:
                mechanism = mechanism if isinstance(mechanism, dict) else {}
                self._insert_finding(
                    connection,
                    case_id,
                    "mechanism_path",
                    path,
                    name=str(path.get("path_id") or ""),
                    mechanism=str(mechanism.get("mechanism_name") or ""),
                    component=str(mechanism.get("source_component") or ""),
                    status=str(path.get("status") or "accepted"),
                    confidence=str(path.get("path_score") or ""),
                )

    def _insert_vulnerability_findings(
        self, connection: sqlite3.Connection, case_id: str, items: Any
    ) -> None:
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            self._insert_finding(
                connection,
                case_id,
                "vulnerability",
                item,
                name=str(item.get("vulnerability_name") or item.get("name") or ""),
                mechanism=str(item.get("mechanism_name") or ""),
                component=str(item.get("source_component") or ""),
                status=str(item.get("status") or "proposed"),
                confidence=str(item.get("confidence") or ""),
            )

    def _insert_experiment_findings(
        self, connection: sqlite3.Connection, case_id: str, items: Any
    ) -> None:
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            plans = item.get("verification_plans") or item.get("plans") or [item]
            for plan in plans if isinstance(plans, list) else [item]:
                plan = plan if isinstance(plan, dict) else item
                self._insert_finding(
                    connection,
                    case_id,
                    "experiment_plan",
                    plan,
                    name=str(
                        item.get("vulnerability_name") or plan.get("vulnerability_name") or ""
                    ),
                    mechanism=str(item.get("mechanism_name") or plan.get("mechanism_name") or ""),
                    component=str(
                        item.get("source_component") or plan.get("source_component") or ""
                    ),
                    status="proposed",
                    confidence=str(plan.get("parameter_confidence") or ""),
                )

    def search_cases(
        self,
        query: str = "",
        *,
        sensor_type: str = "",
        mechanism: str = "",
        verification_outcome: str = "",
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        clauses = ["1 = 1"]
        parameters: list[Any] = []
        if query:
            term = f"%{query}%"
            clauses.append(
                "(c.device_model LIKE ? OR c.sensor_type LIKE ? OR c.summary LIKE ? "
                "OR EXISTS (SELECT 1 FROM findings fq WHERE fq.case_id=c.id "
                "AND (fq.name LIKE ? OR fq.mechanism LIKE ? OR fq.component LIKE ?)))"
            )
            parameters.extend([term] * 6)
        if sensor_type:
            clauses.append("c.sensor_type LIKE ?")
            parameters.append(f"%{sensor_type}%")
        if mechanism:
            clauses.append(
                "EXISTS (SELECT 1 FROM findings fm WHERE fm.case_id=c.id AND fm.mechanism LIKE ?)"
            )
            parameters.append(f"%{mechanism}%")
        if verification_outcome:
            clauses.append(
                "EXISTS (SELECT 1 FROM verification_results vr "
                "WHERE vr.case_id=c.id AND vr.outcome = ?)"
            )
            parameters.append(verification_outcome)
        parameters.append(max(1, min(limit, 100)))

        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT c.*,
                       (SELECT COUNT(*) FROM findings f WHERE f.case_id=c.id) AS finding_count,
                       (SELECT COUNT(*) FROM verification_results v WHERE v.case_id=c.id)
                           AS verification_count
                FROM cases c
                WHERE {" AND ".join(clauses)}
                ORDER BY c.updated_at DESC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        return [dict(row) for row in rows]

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            case = connection.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
            if case is None:
                return None
            findings = connection.execute(
                "SELECT * FROM findings WHERE case_id = ? ORDER BY kind, name", (case_id,)
            ).fetchall()
            verification = connection.execute(
                "SELECT * FROM verification_results WHERE case_id = ? ORDER BY recorded_at DESC",
                (case_id,),
            ).fetchall()
        result = dict(case)
        result["findings"] = [
            {**dict(row), "payload": json.loads(row["payload_json"])} for row in findings
        ]
        result["verification_results"] = [dict(row) for row in verification]
        return result

    def record_verification(
        self,
        case_id: str,
        vulnerability_name: str,
        outcome: str,
        *,
        mechanism_name: str = "",
        notes: str = "",
        evidence: str = "",
    ) -> str:
        allowed = {"confirmed", "rejected", "inconclusive", "not_tested"}
        if outcome not in allowed:
            raise ValueError(f"outcome must be one of: {', '.join(sorted(allowed))}")
        result_id = str(uuid.uuid4())
        with self._connect() as connection:
            exists = connection.execute("SELECT 1 FROM cases WHERE id = ?", (case_id,)).fetchone()
            if exists is None:
                raise KeyError(f"unknown case: {case_id}")
            connection.execute(
                """
                INSERT INTO verification_results (
                    id, case_id, vulnerability_name, mechanism_name,
                    outcome, notes, evidence, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result_id,
                    case_id,
                    vulnerability_name,
                    mechanism_name,
                    outcome,
                    notes,
                    evidence,
                    utc_now(),
                ),
            )
        return result_id

    def add_message(
        self,
        run_id: str,
        role: str,
        content: str,
        citations: list[dict[str, Any]] | None = None,
    ) -> str:
        if role not in {"user", "assistant", "system"}:
            raise ValueError("invalid conversation role")
        message_id = str(uuid.uuid4())
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO conversation_messages (
                    id, run_id, role, content, citations_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    run_id,
                    role,
                    content,
                    json.dumps(citations or [], ensure_ascii=False),
                    utc_now(),
                ),
            )
        return message_id

    def list_messages(self, run_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM conversation_messages
                WHERE run_id = ? ORDER BY created_at ASC LIMIT ?
                """,
                (run_id, max(1, min(limit, 200))),
            ).fetchall()
        return [
            {**dict(row), "citations": json.loads(row["citations_json"])} for row in rows
        ]
