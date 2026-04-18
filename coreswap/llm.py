"""
coreswap/llm.py
Unified LLM client. Groq is used with JSON mode enforced to prevent
markdown-wrapped responses. Falls back to Anthropic if no Groq key.
"""
import os
from typing import Optional

GROQ_MODEL = "llama-3.3-70b-versatile"
ANTHROPIC_MODEL = "claude-sonnet-4-6"


def _active_provider() -> str:
    if os.environ.get("GROQ_API_KEY", "").strip():
        return "groq"
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "anthropic"
    raise RuntimeError(
        "No LLM API key found. Set GROQ_API_KEY (free at console.groq.com) "
        "or ANTHROPIC_API_KEY in your .env file."
    )


def chat(system: str, user: str, max_tokens: int = 1024, json_mode: bool = False) -> str:
    """
    Send system + user message, return assistant text.
    Set json_mode=True to force the model to return valid JSON (Groq/OpenAI feature).
    """
    provider = _active_provider()

    if provider == "groq":
        from groq import Groq
        client = Groq(api_key=os.environ["GROQ_API_KEY"])
        kwargs = dict(
            model=GROQ_MODEL,
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content.strip()

    else:
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
    try:
        p = _active_provider()
        return f"Groq · {GROQ_MODEL}" if p == "groq" else f"Anthropic · {ANTHROPIC_MODEL}"
    except RuntimeError:
        return "No LLM configured"
