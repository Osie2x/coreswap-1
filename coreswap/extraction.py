import json
import re
from typing import Union
import fitz  # PyMuPDF
from .models import ExtractedEPDData, InsulationType
from .prompts import EPD_EXTRACTION_SYSTEM, EPD_EXTRACTION_USER
from .llm import chat


def extract_text_from_pdf(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(pages)


def extract_text_from_txt(content: Union[str, bytes]) -> str:
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return content


def _extract_json(raw: str) -> dict:
    """
    Robustly pull a JSON object out of a model response.
    Handles: plain JSON, ```json ... ```, ``` ... ```,
    leading/trailing whitespace, newlines before the opening brace.
    """
    # 1. Strip markdown fences (handles newlines before/after the brace)
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()

    # 2. Try to parse the whole cleaned string first
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # 3. Pull out the first {...} block as a fallback
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        return json.loads(match.group())

    raise ValueError(f"No valid JSON object found in model response:\n{raw[:300]}")


def extract_epd_data_via_llm(raw_text: str, insulation_type: InsulationType) -> ExtractedEPDData:
    # Truncate to ~12 000 chars so we stay within Groq context limits
    truncated = raw_text[:12000]

    system = EPD_EXTRACTION_SYSTEM.format(insulation_type=insulation_type)
    user = EPD_EXTRACTION_USER.format(epd_raw_text=truncated)

    raw = chat(system=system, user=user, max_tokens=1024)
    data = _extract_json(raw)
    return ExtractedEPDData(**data)
