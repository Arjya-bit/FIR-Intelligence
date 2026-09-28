"""Verify the configured LLM endpoint before starting the app.

Reads .env, makes one buffered call and one streaming call, and reports exactly
what came back. Run it whenever the dashboard says the assistant is in fallback
mode and you expected a model:

    python scripts/check_llm.py

Exit code 0 means both calls succeeded.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import llm_client  # noqa: E402

OK, BAD, WARN = "\033[92m✓\033[0m", "\033[91m✗\033[0m", "\033[93m!\033[0m"


def _redact(key: str) -> str:
    if not key:
        return "(not set)"
    return f"{key[:6]}…{key[-4:]} ({len(key)} chars)"


async def main() -> int:
    print("FIR Intelligence — LLM connectivity check\n")
    print(f"  API key   : {_redact(llm_client.API_KEY)}")
    print(f"  Base URL  : {llm_client.BASE_URL}")
    print(f"  Model     : {llm_client.MODEL}")
    print(f"  Endpoint  : {llm_client.BASE_URL}/chat/completions")
    print(f"  Timeout   : {llm_client.TIMEOUT}s")
    print(f"  Thinking  : {'on' if llm_client.THINKING else 'off'}\n")

    if not llm_client.is_configured():
        print(f"{BAD} No API key. Set ZAI_API_KEY in .env, then re-run.")
        print("    cp .env.example .env")
        return 1

    probe = [
        {"role": "system", "content": "You are a terse assistant."},
        {"role": "user", "content": "Reply with exactly: CONNECTION OK"},
    ]

    print("1. Buffered call (/chat/completions)…")
    try:
        text = await llm_client.complete(probe, max_tokens=32, temperature=0)
        print(f"   {OK} replied: {text[:120]!r}\n")
    except llm_client.LLMError as exc:
        print(f"   {BAD} {exc}\n")
        _diagnose(str(exc))
        return 1

    print("2. Streaming call (stream=true)…")
    try:
        chunks = [c async for c in llm_client.stream(probe, max_tokens=32,
                                                     temperature=0)]
        print(f"   {OK} {len(chunks)} chunks: {''.join(chunks)[:120]!r}\n")
    except llm_client.LLMError as exc:
        print(f"   {WARN} buffered works but streaming failed: {exc}")
        print("     The assistant will still answer; replies just will not "
              "stream in token by token.\n")
        return 1

    print(f"{OK} Both calls succeeded. Start the app with: python main.py")
    return 0


def _diagnose(error: str) -> None:
    """Map the common failures onto the thing to actually change."""
    lowered = error.lower()
    print("   Likely cause:")
    if "403" in lowered and "request failed" in lowered:
        # A proxy that denies CONNECT answers 403 too, which reads exactly like
        # the API rejecting the key. Distinguish them: an API 403 arrives as an
        # HTTP status with a JSON body, a proxy 403 kills the tunnel first.
        print("     The TLS tunnel was refused before the request reached Z.ai —"
              " an egress proxy or firewall is\n"
              "     blocking api.z.ai. This is NOT your key being rejected.")
        print("     Check:  curl -sS -o /dev/null -w '%{http_code}\\n' "
              "https://api.z.ai")
        print("     If you are behind a proxy, ensure HTTPS_PROXY is set and "
              "api.z.ai is on its allow-list.")
    elif "401" in lowered or "unauthorized" in lowered or "invalid" in lowered:
        print("     The key was rejected. Check ZAI_API_KEY, and that the key "
              "matches the plan behind LLM_BASE_URL — Z.ai serves coding-plan\n"
              "     keys from /api/coding/paas/v4 and general keys from "
              "/api/paas/v4.")
    elif "404" in lowered:
        print("     Endpoint or model not found. Check LLM_BASE_URL (it should "
              "end in /v4, with no trailing /chat/completions) and that\n"
              "     LLM_MODEL names a model your account can use.")
    elif "429" in lowered:
        print("     Rate limited or out of quota. Check your Z.ai plan usage.")
    elif "connect" in lowered or "timeout" in lowered or "failed" in lowered:
        print("     The host was unreachable — DNS, a firewall, a corporate "
              "proxy, or no outbound internet access.\n"
              "     Try: curl -I https://api.z.ai")
    else:
        print("     See the error above.")
    print("\n   The app runs fine without a model: it answers from the analysed "
          "corpus instead.")


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
