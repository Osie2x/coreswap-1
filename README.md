# CORESWAP

AI-powered embodied carbon advisory for Canadian prefab home manufacturers.

Upload an insulation Environmental Product Declaration, get a validated lifecycle
assessment and a Bill C-59 aligned ESG report in minutes instead of weeks.

## Origin

Built as a follow-up to a BDO Future Leaders Challenge (BU121, Winter 2026)
semifinal case competition entry proposing recycled cellulose as a drop-in
replacement for spray foam and fiberglass in Canadian prefab construction.
The original proposal described a digital advisory dashboard — this is the
working prototype of that concept.

## What it does

1. Collects a factory profile (province, annual units, home size, current insulation)
2. Extracts embodied carbon data from an uploaded EPD PDF using Claude
3. Validates extracted values against plausible ranges per insulation type
4. Runs a deterministic LCA comparing current insulation to cellulose
5. Generates a written ESG narrative + downloadable PDF report

## Stack

Python · Streamlit · Anthropic Claude · PyMuPDF · Pandas · ReportLab · SQLite · Pydantic

## Quickstart

See `PRD.md` for full setup. Short version:

    pip install -r requirements.txt
    cp .env.example .env   # add your Anthropic API key
    streamlit run app.py

## Scope

This is an MVP. Features deliberately out of scope for V1 are listed in PRD.md §16.
The design choice to ship one end-to-end pipeline (rather than a wider but shallower
set of features) was intentional.

## Key technical decision

EPDs are inconsistently formatted across manufacturers. Regex extraction was brittle
and pure LLM extraction occasionally hallucinated edge cases (pulling biogenic-only
carbon values instead of total GWP, unit conversion errors). The solution in this
repo: LLM extraction feeds a validation layer that cross-checks every extracted
value against plausible GWP ranges per insulation category derived from CIMA BEAM
industry data. Out-of-range values flag for human review rather than silently
producing bad numbers.

## License

MIT
