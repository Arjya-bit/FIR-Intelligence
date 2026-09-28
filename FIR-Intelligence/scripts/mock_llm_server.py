"""Development stub of an OpenAI-compatible /chat/completions endpoint.

NOT a model. It exists so the LLM integration — request shape, SSE streaming,
grounding, error handling and the fallback path — can be exercised without a
provider key or outbound network access.

    python scripts/mock_llm_server.py            # listens on 127.0.0.1:8899

    LLM_BASE_URL=http://127.0.0.1:8899/v1 \
    ZAI_API_KEY=dev-key \
    python main.py

It echoes back the grounding it was given, so if the wiring drops the corpus
facts the output visibly loses them. Force failures with:

    MOCK_LLM_FAIL=500    # every request returns HTTP 500
    MOCK_LLM_FAIL=empty  # returns a well-formed but empty completion
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

FAIL_MODE = os.getenv("MOCK_LLM_FAIL", "").strip().lower()
CHUNK_DELAY = float(os.getenv("MOCK_LLM_DELAY", "0.02"))

app = FastAPI(title="Mock OpenAI-compatible LLM (development only)")


def _compose(messages: list[dict]) -> str:
    """Build a reply that demonstrably depends on the grounding it received."""
    system = " ".join(m.get("content", "") for m in messages if m["role"] == "system")
    user = next((m.get("content", "") for m in reversed(messages)
                 if m["role"] == "user"), "")

    is_report = "intelligence officer" in system.lower()
    question = ""
    match = re.search(r"Officer's question:\s*(.+)$", user, re.S)
    if match:
        question = match.group(1).strip()

    # Pull the grounding block through so a dropped hand-off is visible.
    grounding = ""
    marker = "PRE-COMPUTED ANALYSIS"
    if marker in user:
        grounding = user.split(marker, 1)[1].split("Officer's question:")[0]
        grounding = grounding.split(":", 1)[-1].strip()
    elif "VERIFIED ANALYSIS" in user:
        grounding = user.split("VERIFIED ANALYSIS OF THE FIR CORPUS:", 1)[1]
        grounding = grounding.split("SUPPORTING TOTALS:")[0].strip()

    fir_numbers = re.findall(r"\b[A-Z]{2,5}/\d{4}/[A-Z]{2}/\d{3}\b", grounding)[:5]
    cited = f"\n\nCited from the corpus: {', '.join(dict.fromkeys(fir_numbers))}" \
        if fir_numbers else ""

    if is_report:
        return (
            "[MOCK MODEL OUTPUT — development stub, not a real language model]\n\n"
            "1. Executive Summary\n"
            "The figures below are reproduced from the verified analysis supplied "
            "with this request.\n\n"
            f"{grounding[:2500]}\n\n"
            "Findings are automated correlations and require verification by the "
            "investigating officer."
        )

    return (
        "[MOCK MODEL OUTPUT — development stub, not a real language model]\n\n"
        f"Question received: {question[:200]}\n\n"
        f"Answer derived from the supplied analysis:\n\n{grounding[:1800]}{cited}"
    )


@app.post("/v1/chat/completions")
@app.post("/chat/completions")
@app.post("/api/paas/v4/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages") or []
    model = body.get("model", "mock-model")

    if FAIL_MODE == "500":
        return JSONResponse({"error": {"message": "mock failure"}}, status_code=500)

    text = "" if FAIL_MODE == "empty" else _compose(messages)

    if not body.get("stream"):
        return JSONResponse({
            "id": "mock-1",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": len(text.split()),
                      "total_tokens": len(text.split())},
        })

    async def events():
        for word in text.split(" "):
            frame = {
                "id": "mock-1", "object": "chat.completion.chunk",
                "created": int(time.time()), "model": model,
                "choices": [{"index": 0, "delta": {"content": word + " "}}],
            }
            yield f"data: {json.dumps(frame)}\n\n"
            await asyncio.sleep(CHUNK_DELAY)
        yield ('data: {"choices":[{"index":0,"delta":{},'
               '"finish_reason":"stop"}]}\n\n')
        yield "data: [DONE]\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("MOCK_LLM_PORT", "8899"))
    print(f"Mock LLM on http://127.0.0.1:{port}  (fail mode: {FAIL_MODE or 'none'})",
          file=sys.stderr)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
