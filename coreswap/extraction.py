import json
import fitz  # PyMuPDF
import anthropic
from .models import ExtractedEPDData, InsulationType
from .prompts import EPD_EXTRACTION_SYSTEM, EPD_EXTRACTION_USER


def extract_text_from_pdf(file_bytes: bytes) -> str:
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = [page.get_text() for page in doc]
    doc.close()
    return "\n".join(pages)


def extract_text_from_txt(content: str | bytes) -> str:
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return content


def extract_epd_data_via_llm(raw_text: str, insulation_type: InsulationType) -> ExtractedEPDData:
    client = anthropic.Anthropic()
    system = EPD_EXTRACTION_SYSTEM.format(insulation_type=insulation_type)
    user = EPD_EXTRACTION_USER.format(epd_raw_text=raw_text)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user}],
    )

    raw = message.content[0].text.strip()
    # Strip accidental markdown fences if model includes them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    data = json.loads(raw)
    return ExtractedEPDData(**data)
