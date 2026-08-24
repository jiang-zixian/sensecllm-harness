from __future__ import annotations

import json
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .config import RAGConfig, benchmark_sensor_models
from .indexer import index_stats
from .pipeline import SensorRAG


class RAGApplication:
    def __init__(self, config: RAGConfig):
        self.config = config
        self._pipeline: SensorRAG | None = None
        self._lock = threading.Lock()

    @property
    def pipeline(self) -> SensorRAG:
        if self._pipeline is None:
            with self._lock:
                if self._pipeline is None:
                    self._pipeline = SensorRAG(self.config)
        return self._pipeline

    def process(self, body: dict[str, Any]) -> dict[str, Any]:
        inputs = body.get("inputs") if isinstance(body.get("inputs"), dict) else {}
        query = str(body.get("query") or "").strip()
        rag_input = inputs.get("RAGinput") or inputs.get("rag_input")
        if rag_input is not None and not isinstance(rag_input, str):
            rag_input = json.dumps(rag_input, ensure_ascii=False)
        if not query and not rag_input:
            raise ValueError("query or inputs.RAGinput is required")
        evidence_only = str(inputs.get("mode", "answer")).casefold() in {"evidence", "retrieve", "raw"}
        raw_exclude_terms = inputs.get("exclude_terms") or []
        if isinstance(raw_exclude_terms, str):
            exclude_terms = [term.strip() for term in raw_exclude_terms.split(",") if term.strip()]
        elif isinstance(raw_exclude_terms, list):
            exclude_terms = [str(term).strip() for term in raw_exclude_terms if str(term).strip()]
        else:
            raise ValueError("inputs.exclude_terms must be a list or comma-separated string")
        # This is a service-wide safety boundary, not merely a Step-4 caller
        # convention: every endpoint excludes all held-out benchmark models.
        exclude_terms = list(dict.fromkeys([*benchmark_sensor_models(), *exclude_terms]))
        return self.pipeline.answer(
            query or "retrieve",
            rag_input=rag_input,
            evidence_only=evidence_only,
            exclude_terms=exclude_terms,
        )


def make_handler(application: RAGApplication):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SenSecRAG/1.0"

        def log_message(self, fmt: str, *args: Any) -> None:
            print(f"[RAG] {self.address_string()} - {fmt % args}")

        def _json(self, status: int, payload: dict[str, Any]) -> None:
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 10 * 1024 * 1024:
                raise ValueError("invalid request body length")
            return json.loads(self.rfile.read(length).decode("utf-8"))

        def do_GET(self) -> None:  # noqa: N802
            if self.path.rstrip("/") == "/health":
                stats = index_stats(application.config)
                if not stats.get("rows", 0):
                    status = "index_missing"
                elif not stats.get("complete"):
                    status = "partial_index"
                else:
                    status = "ok"
                self._json(HTTPStatus.OK, {"status": status, **stats})
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path.rstrip("/") not in {"/v1/chat-messages", "/v1/retrieve"}:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return
            try:
                body = self._read_json()
                if self.path.rstrip("/") == "/v1/retrieve":
                    body.setdefault("inputs", {})["mode"] = "evidence"
                result = application.process(body)
                if self.path.rstrip("/") == "/v1/retrieve":
                    self._json(HTTPStatus.OK, result)
                    return
                self._send_dify_response(body, result)
            except (ValueError, json.JSONDecodeError) as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid_param", "message": str(exc)})
            except Exception as exc:
                self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    {"error": "rag_error", "message": f"{type(exc).__name__}: {exc}"},
                )

        def _send_dify_response(self, body: dict[str, Any], result: dict[str, Any]) -> None:
            conversation_id = str(body.get("conversation_id") or uuid.uuid4())
            message_id = str(uuid.uuid4())
            answer = str(result["answer"])
            metadata = {"sources": result.get("sources", []), "retrieval_query": result.get("retrieval_query")}
            if body.get("response_mode", "streaming") == "blocking":
                self._json(
                    HTTPStatus.OK,
                    {
                        "event": "message",
                        "message_id": message_id,
                        "conversation_id": conversation_id,
                        "answer": answer,
                        "metadata": metadata,
                    },
                )
                return

            events = [
                {
                    "event": "message",
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                    "answer": answer,
                },
                {
                    "event": "message_end",
                    "message_id": message_id,
                    "conversation_id": conversation_id,
                    "metadata": metadata,
                },
            ]
            encoded = b"".join(
                f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8") for event in events
            )
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return Handler


def serve(config: RAGConfig) -> None:
    application = RAGApplication(config)
    server = ThreadingHTTPServer((config.host, config.port), make_handler(application))
    print(f"SenSec RAG listening on http://{config.host}:{config.port}")
    print(f"Dify-compatible endpoint: http://{config.host}:{config.port}/v1/chat-messages")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
