"""SenseCLLM multi-agent harness."""

from pathlib import Path

from dotenv import load_dotenv

# A local, ignored `.env` is the single configuration entry point. Existing
# process variables win so CI, Docker, and one-off overrides remain possible.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)

__version__ = "0.1.0"
