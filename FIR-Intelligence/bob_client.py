"""IBM watsonx.ai client with a deterministic, data-driven fallback.

When ``WATSONX_API_KEY`` is set, crime classification, chat and report writing
go to a Granite model. When it is absent — or the call fails — the same
questions are answered from the analysed corpus by :mod:`intel_qa` rather than
from canned prose, so an unconfigured deployment degrades to *fewer* words, not
to invented ones.
"""

from __future__ import annotations

import asyncio
import json
import os
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

WATSONX_API_KEY = os.getenv("WATSONX_API_KEY", "")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID", "")
WATSONX_URL = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
WATSONX_MODEL = os.getenv("WATSONX_MODEL", "ibm/granite-3-8b-instruct")
REQUEST_TIMEOUT = float(os.getenv("WATSONX_TIMEOUT", "60"))

#: IBM IAM access tokens are valid for one hour. The previous implementation
#: cached the first token forever, so every deployment started failing with
#: 401s roughly an hour after boot. Refresh a minute before expiry.
_TOKEN_SKEW_SECONDS = 60

_token: str | None = None
_token_expires_at: float = 0.0
_token_lock = asyncio.Lock()


def is_configured() -> bool:
    """True when watsonx.ai credentials are present."""
    return bool(WATSONX_API_KEY and WATSONX_PROJECT_ID)


class WatsonxError(RuntimeError):
    """Raised when watsonx.ai cannot fulfil a request."""


async def _get_iam_token() -> str:
    global _token, _token_expires_at

    async with _token_lock:
        if _token and time.monotonic() < _token_expires_at:
            return _token

        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(
                "https://iam.cloud.ibm.com/identity/token",
                data={
                    "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                    "apikey": WATSONX_API_KEY,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            payload = resp.json()

        _token = payload["access_token"]
        lifetime = int(payload.get("expires_in", 3600))
        _token_expires_at = time.monotonic() + max(lifetime - _TOKEN_SKEW_SECONDS, 60)
        return _token


async def generate(prompt: str, model_id: str | None = None,
                   max_tokens: int = 2048, temperature: float = 0.1) -> str:
    """Call watsonx.ai text generation. Raises :class:`WatsonxError` on failure."""
    if not is_configured():
        raise WatsonxError("watsonx.ai credentials are not configured")

    payload = {
        "model_id": model_id or WATSONX_MODEL,
        "input": prompt,
        "parameters": {
            "max_new_tokens": max_tokens,
            "temperature": temperature,
            "top_p": 0.95,
            "repetition_penalty": 1.05,
            "stop_sequences": ["\n\n---", "```"],
        },
        "project_id": WATSONX_PROJECT_ID,
    }

    try:
        token = await _get_iam_token()
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            resp = await client.post(
                f"{WATSONX_URL}/ml/v1/text/generation?version=2024-05-31",
                json=payload,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )
            resp.raise_for_status()
            results = resp.json().get("results") or []
    except httpx.HTTPStatusError as exc:
        raise WatsonxError(
            f"watsonx.ai returned {exc.response.status_code}: "
            f"{exc.response.text[:200]}"
        ) from exc
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise WatsonxError(f"watsonx.ai request failed: {exc}") from exc

    if not results:
        raise WatsonxError("watsonx.ai returned no completions")
    return (results[0].get("generated_text") or "").strip()


# ── Rule-based crime classification ────────────────────────────────────────

#: Ordered most-specific first: a narrative mentioning both a weapon and a
#: death should classify as murder, not assault.
_CLASSIFIER_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("murder", ("murder", "killed", "found dead", "stab wound", "302 ipc",
                "post-mortem", "deceased")),
    ("dacoity", ("dacoity", "395 ipc", "396 ipc", "gang of", "at gunpoint, looted")),
    ("kidnapping", ("kidnap", "abduct", "missing person", "did not return",
                    "363 ipc", "366 ipc", "ransom")),
    ("sexual_offense", ("376 ipc", "354 ipc", "pocso", "molest", "rape")),
    ("drug_offense", ("ndps", "heroin", "smack", "ganja", "mdma", "brown sugar",
                      "narcotic", "charas")),
    ("extortion", ("extortion", "protection money", "384 ipc", "385 ipc",
                   "threatening call")),
    ("cybercrime", ("cyber", "otp", "kyc", "phishing", "digital arrest",
                    "66c", "66d", "fake profile", "online fraud")),
    ("robbery", ("robbery", "snatch", "looted", "392 ipc", "394 ipc", "397 ipc",
                 "bike-borne")),
    ("burglary", ("burgl", "broke into", "break-in", "gas cutter", "457 ipc",
                  "cutting the lock", "shutter")),
    ("arson", ("arson", "set on fire", "435 ipc", "436 ipc", "inflammable")),
    ("rioting", ("riot", "147 ipc", "148 ipc", "149 ipc", "mob", "group clash")),
    ("fraud", ("fraud", "cheated", "forged", "420 ipc", "ponzi", "fake investment")),
    ("assault", ("assault", "attacked", "beaten", "323 ipc", "324 ipc", "307 ipc",
                 "injuries", "hospitalized")),
    ("theft", ("theft", "stolen", "pickpocket", "379 ipc", "380 ipc")),
]


def classify_crime_rule_based(fir_text: str) -> str:
    text = (fir_text or "").lower()
    for crime_type, keywords in _CLASSIFIER_RULES:
        if any(keyword in text for keyword in keywords):
            return crime_type
    return "other"


VALID_CRIME_TYPES = {
    "theft", "robbery", "burglary", "assault", "murder", "fraud", "cybercrime",
    "drug_offense", "kidnapping", "sexual_offense", "extortion", "dacoity",
    "arson", "rioting", "other",
}


async def classify_crime(fir_text: str) -> str:
    """Classify an FIR, preferring watsonx.ai and falling back to rules."""
    if not is_configured():
        return classify_crime_rule_based(fir_text)

    prompt = f"""You are an expert Indian police crime analyst. Classify the following FIR into exactly one crime type.

Crime types: {', '.join(sorted(VALID_CRIME_TYPES))}

FIR Text:
{fir_text[:2000]}

Respond with ONLY the crime type (single word from the list above):"""

    try:
        result = await generate(prompt, max_tokens=20, temperature=0.0)
    except WatsonxError:
        return classify_crime_rule_based(fir_text)

    cleaned = result.strip().lower().strip('"\'.,')
    return cleaned if cleaned in VALID_CRIME_TYPES else classify_crime_rule_based(fir_text)


async def extract_entities_llm(fir_text: str) -> dict:
    """Best-effort LLM entity extraction. Returns ``{}`` when unavailable."""
    if not is_configured():
        return {}

    prompt = f"""You are an expert NLP system for Indian police FIR analysis. Extract all named entities from this FIR.

FIR Text:
{fir_text[:2000]}

Return a JSON object with these keys:
- accused: list of objects with name, aliases, age, gender, address, id_marks
- victims: list of objects with name, age, gender, occupation, address
- locations: list of place names
- weapons: list of weapons mentioned
- vehicles: list of vehicles with descriptions
- stolen_property: list of stolen items with values
- ipc_sections: list of IPC/Act sections mentioned
- phone_numbers: list of phone numbers
- modus_operandi: description of how the crime was committed

JSON:"""

    try:
        result = await generate(prompt, max_tokens=1500, temperature=0.0)
        start, end = result.find("{"), result.rfind("}") + 1
        if start >= 0 and end > start:
            parsed = json.loads(result[start:end])
            return parsed if isinstance(parsed, dict) else {}
    except (WatsonxError, json.JSONDecodeError, ValueError):
        pass
    return {}


async def generate_intelligence_report(analysis_data: dict, *,
                                       deterministic_report: str = "") -> str:
    """Produce an intelligence report.

    ``deterministic_report`` is the report computed from the corpus. It is
    returned as-is when watsonx.ai is unavailable, and supplied to the model as
    grounding when it is, so the narrative cannot drift from the real figures.
    """
    if not is_configured():
        return deterministic_report

    prompt = f"""You are a senior intelligence officer of Uttar Pradesh Police. Rewrite the following verified analysis into a polished crime intelligence report.

Use ONLY the facts below. Do not invent offenders, FIR numbers, districts or figures.

Verified analysis:
{deterministic_report[:6000]}

Supporting totals:
- Total FIRs analysed: {analysis_data.get('total_firs', 0)}
- Crime breakdown: {json.dumps(analysis_data.get('crime_breakdown', {}))}
- Repeat offenders found: {analysis_data.get('repeat_offender_count', 0)}
- Districts covered: {json.dumps(analysis_data.get('districts', []))}
- Networks: {json.dumps(analysis_data.get('patterns', []))}

Keep the section structure (Executive Summary, Crime Pattern Analysis, Repeat
Offender Alerts, Organised Networks, Station-wise Trend Analysis, Recommended
Actions, Risk Assessment).

Report:"""

    try:
        return await generate(prompt, max_tokens=2048, temperature=0.3)
    except WatsonxError:
        return deterministic_report


async def chat_with_bob(message: str, context: str = "", *,
                        deterministic_answer: str = "") -> str:
    """Answer an officer's question, grounded in the analysed corpus."""
    if not is_configured():
        return deterministic_answer

    prompt = f"""You are Bob, an AI-powered FIR Intelligence Assistant deployed for Uttar Pradesh Police. You help officers analyse FIR data, identify crime patterns, and track repeat offenders.

Answer using ONLY the facts below. If they do not cover the question, say so —
never invent FIR numbers, offender names or statistics.

Corpus summary:
{context[:3000]}

Pre-computed answer from the database (authoritative):
{deterministic_answer[:3000]}

Officer's question: {message}

Give a clear, specific answer. Reference the FIR numbers and names that appear above.

Response:"""

    try:
        return await generate(prompt, max_tokens=1024, temperature=0.3)
    except WatsonxError:
        return deterministic_answer
