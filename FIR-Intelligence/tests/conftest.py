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


# ── Shared clients ─────────────────────────────────────────────────────────

import pytest  # noqa: E402

DEMO_LOGINS = {
    "admin": "Admin@FIR2024",
    "supervisor": "Super@FIR2024",
    "investigator": "Invest@FIR2024",
    "analyst": "Analyst@FIR2024",
    "viewer": "Viewer@FIR2024",
}


@pytest.fixture(scope="session")
def app_client():
    """Boots the app once; the startup analysis is the slow part."""
    from fastapi.testclient import TestClient

    import main

    with TestClient(main.app) as test_client:
        yield test_client


@pytest.fixture
def anon_client(app_client):
    """A client with no session cookie."""
    app_client.cookies.clear()
    return app_client


@pytest.fixture
def sign_in(app_client):
    """Factory: sign the shared client in as a given role."""
    def _sign_in(role: str):
        app_client.cookies.clear()
        response = app_client.post("/api/auth/login", json={
            "username": role, "password": DEMO_LOGINS[role]})
        assert response.status_code == 200, response.text
        return app_client
    return _sign_in


@pytest.fixture
def client(sign_in):
    """Default client for feature tests: full access, so a test failure means
    the feature is broken rather than the permission being wrong."""
    return sign_in("admin")
