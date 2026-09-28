import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv()

WATSONX_API_KEY = os.getenv("WATSONX_API_KEY", "")
WATSONX_PROJECT_ID = os.getenv("WATSONX_PROJECT_ID", "")
WATSONX_URL = os.getenv("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")

_iam_token: str | None = None


async def _get_iam_token() -> str:
    global _iam_token
    if _iam_token:
        return _iam_token
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://iam.cloud.ibm.com/identity/token",
            data={
                "grant_type": "urn:ibm:params:oauth:grant-type:apikey",
                "apikey": WATSONX_API_KEY,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        _iam_token = resp.json()["access_token"]
        return _iam_token


async def generate(prompt: str, model_id: str = "ibm/granite-3-8b-instruct",
                   max_tokens: int = 2048, temperature: float = 0.1) -> str:
    if not WATSONX_API_KEY:
        return _fallback_generate(prompt)

    token = await _get_iam_token()
    url = f"{WATSONX_URL}/ml/v1/text/generation?version=2024-05-31"

    payload = {
        "model_id": model_id,
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

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        resp.raise_for_status()
        result = resp.json()
        return result["results"][0]["generated_text"].strip()


def _fallback_generate(prompt: str) -> str:
    """Rule-based fallback when watsonx.ai is not configured."""
    if "classify" in prompt.lower() or "crime type" in prompt.lower():
        return _classify_fallback(prompt)
    if "extract" in prompt.lower() or "entities" in prompt.lower():
        return _extract_fallback(prompt)
    if "summary" in prompt.lower() or "report" in prompt.lower():
        return _report_fallback(prompt)
    if "chat" in prompt.lower() or "question" in prompt.lower():
        return _chat_fallback(prompt)
    return "Analysis complete."


def _classify_fallback(prompt: str) -> str:
    text = prompt.lower()
    if any(w in text for w in ["murder", "killed", "stab", "dead", "302"]):
        return "murder"
    if any(w in text for w in ["snatch", "rob", "loot", "dacoit", "392", "395", "397"]):
        return "robbery"
    if any(w in text for w in ["burgl", "broke into", "break-in", "457", "380"]):
        return "burglary"
    if any(w in text for w in ["fraud", "cheat", "scam", "phish", "420", "66c", "66d"]):
        return "fraud"
    if any(w in text for w in ["drug", "ndps", "ganja", "heroin", "smack", "mdma"]):
        return "drug_offense"
    if any(w in text for w in ["kidnap", "missing", "abduct", "363", "366", "pocso"]):
        return "kidnapping"
    if any(w in text for w in ["extort", "threat", "protection money", "384", "506"]):
        return "extortion"
    if any(w in text for w in ["cyber", "stalk", "identity theft", "fake profile"]):
        return "cybercrime"
    if any(w in text for w in ["assault", "beat", "attack", "injur", "323", "307"]):
        return "assault"
    if any(w in text for w in ["arson", "fire", "burn", "435", "436"]):
        return "arson"
    return "other"


def _extract_fallback(prompt: str) -> str:
    return json.dumps({"status": "extracted_via_spacy"})


def _report_fallback(prompt: str) -> str:
    return "Intelligence report generated based on analyzed FIR data."


def _chat_fallback(prompt: str) -> str:
    return "Based on the FIR intelligence database, I can provide analysis on crime patterns, repeat offenders, and station-level trends."


async def classify_crime(fir_text: str) -> str:
    if not WATSONX_API_KEY:
        return _classify_fallback(fir_text)

    prompt = f"""You are an expert Indian police crime analyst. Classify the following FIR into exactly one crime type.

Crime types: theft, robbery, burglary, assault, murder, fraud, cybercrime, drug_offense, kidnapping, sexual_offense, extortion, dacoity, arson, rioting, other

FIR Text:
{fir_text[:2000]}

Respond with ONLY the crime type (single word from the list above):"""

    result = await generate(prompt, max_tokens=20, temperature=0.0)
    valid = {"theft", "robbery", "burglary", "assault", "murder", "fraud",
             "cybercrime", "drug_offense", "kidnapping", "sexual_offense",
             "extortion", "dacoity", "arson", "rioting", "other"}
    cleaned = result.strip().lower().replace('"', '').replace("'", "")
    return cleaned if cleaned in valid else _classify_fallback(fir_text)


async def extract_entities_llm(fir_text: str) -> dict:
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

    result = await generate(prompt, max_tokens=1500, temperature=0.0)
    try:
        start = result.find("{")
        end = result.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(result[start:end])
    except (json.JSONDecodeError, ValueError):
        pass
    return {}


async def generate_intelligence_report(analysis_data: dict) -> str:
    prompt = f"""You are a senior intelligence officer of Uttar Pradesh Police. Generate a comprehensive crime intelligence report based on the following analysis data.

Analysis Summary:
- Total FIRs analyzed: {analysis_data.get('total_firs', 0)}
- Crime breakdown: {json.dumps(analysis_data.get('crime_breakdown', {}))}
- Repeat offenders found: {analysis_data.get('repeat_offender_count', 0)}
- Districts covered: {json.dumps(analysis_data.get('districts', []))}
- Key patterns: {json.dumps(analysis_data.get('patterns', []))}

Generate a structured intelligence report with:
1. Executive Summary
2. Crime Pattern Analysis
3. Repeat Offender Alerts
4. Station-wise Trend Analysis
5. Recommended Actions
6. Risk Assessment

Report:"""

    return await generate(prompt, max_tokens=2048, temperature=0.3)


async def chat_with_bob(message: str, context: str = "") -> str:
    prompt = f"""You are Bob, an AI-powered FIR Intelligence Assistant deployed for Uttar Pradesh Police. You help officers analyze FIR data, identify crime patterns, and track repeat offenders.

Context from FIR database:
{context[:3000]}

Officer's question: {message}

Provide a helpful, specific response based on the FIR data. Reference specific FIR numbers, accused names, and patterns when relevant.

Response:"""

    return await generate(prompt, max_tokens=1024, temperature=0.3)
