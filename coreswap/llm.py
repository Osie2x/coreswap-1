"""
coreswap/llm.py
───────────────
Unified LLM client for CORESWAP.

Priority (checked at call-time, not import-time):
  1. GROQ_API_KEY   → groq, model: llama-3.3-70b-versatile
  2. ANTHROPIC_API_KEY → anthropic, model: claude-sonnet-4-6

Both providers expose an OpenAI-compatible chat interface.
The public API of this module is a single function:

    chat(system: str, user: str, max_tokens: int = 1024) -> str

Raises RuntimeError if neither key is set.
"""

import os
from typing import Optional


# ── Model names ────────────────────────────────────────────────────────────
GROQ_MODEL = "llama-3.3-70b-versatile"
ANTHROPIC_MODEL = "claude-sonnet-4-6"


def _active_provider() -> str:
    """Return 'groq' or 'anthropic' based on which API key is present."""
    if os.environ.get("GROQ_API_KEY", "").strip():
        return "groq"
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "anthropic"
    raise RuntimeError(
        "No LLM API key found. Set GROQ_API_KEY (free at console.groq.com) "
        "or ANTHROPIC_API_KEY in your .env file."
    )


def chat(system: str, user: str, max_tokens: int = 1024) -> str:
    """
    Send a system + user message pair and return the assistant text.

    Works identically regardless of whether Groq or Anthropic is active.
    """
    provider = _active_provider()

    if provider == "groq":
        from groq import Groq  # type: ignore
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        return response.choices[0].message.content.strip()

    else:  # anthropic
        import anthropic as _anthropic
        client = _anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        message = client.messages.create(
            model=ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return message.content[0].text.strip()


def active_provider_label() -> str:
    """Human-readable label shown in the Streamlit sidebar."""
    try:
        p = _active_provider()
        if p == "groq":
            return f"Groq · {GROQ_MODEL}"
        return f"Anthropic · {ANTHROPIC_MODEL}"
    except RuntimeError:
        return "No LLM configured"
