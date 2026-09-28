"""Shared test setup.

The suite must behave identically whether or not the developer running it has
credentials in `.env`. `llm_client` and `bob_client` both call `load_dotenv()`
at import time, so without this a machine with a real `ZAI_API_KEY` would take
the live-model path and fail every assertion about the fallback engine — and,
worse, a test run would make billable API calls against a real provider.

pytest loads conftest before any test module, and `load_dotenv()` does not
override variables that are already set, so blanking them here wins over
whatever `.env` contains. Tests that need a configured provider monkeypatch
`llm_client.API_KEY` directly and stub the transport, so they never leave the
process.
"""

from __future__ import annotations

import os

for _var in ("ZAI_API_KEY", "LLM_API_KEY", "WATSONX_API_KEY", "WATSONX_PROJECT_ID"):
    os.environ[_var] = ""

# Keep the suite off any real database and on a small, fast corpus.
os.environ.setdefault("FIR_STORAGE", "memory")
os.environ.setdefault("FIR_SEED_SIZE", "40")
