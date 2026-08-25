"""Legacy configuration compatibility layer.

The original pipeline imports these module-level names directly. Keep those
names stable, but source credentials and machine-local paths from environment
variables so secrets never need to live in Git.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASE_DIR = PROJECT_ROOT
load_dotenv(PROJECT_ROOT / ".env", override=False)


def _env_path(name: str, default: Path) -> Path:
    return Path(os.getenv(name, str(default))).expanduser().resolve()


def _bearer(header_name: str, key_name: str) -> str:
    explicit = os.getenv(header_name, "").strip()
    if explicit:
        return explicit
    key = os.getenv(key_name, "").strip()
    return f"Bearer {key}" if key else ""


# The Harness overwrites these values per run. Defaults keep direct legacy
# step invocation possible.
input_file = _env_path("SENSECLLM_INPUT_FILE", PROJECT_ROOT / "examples" / "sensor.md")
output_report = _env_path(
    "SENSECLLM_OUTPUT_REPORT", PROJECT_ROOT / "runs" / "default" / "report.md"
)
output_report_cn = _env_path(
    "SENSECLLM_OUTPUT_REPORT_CN", PROJECT_ROOT / "runs" / "default" / "report.zh.md"
)

# Only keys referenced by the retained legacy stages are exposed here.
dify_api_key = os.getenv("DIFY_API_KEY", "")
dify_2_analyze_onlyRAG_api_key = os.getenv("SENSOR_RAG_API_KEY", "sensor-rag-local")
dify_chat_api_key = os.getenv("DIFY_CHAT_API_KEY", "")
dify_verify_onlyRAG_api_key = os.getenv("SENSOR_RAG_API_KEY", "sensor-rag-local")

chatanywhere_auth_header = _bearer("CHATANYWHERE_AUTH_HEADER", "CHATANYWHERE_API_KEY")
