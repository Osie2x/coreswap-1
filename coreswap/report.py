import os
from datetime import datetime, timezone
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_LEFT, TA_CENTER

from .config import REPORTS_DIR
from .models import FactoryProfile, LCAResult
from .prompts import REPORT_NARRATIVE_SYSTEM, REPORT_NARRATIVE_USER
from .llm import chat

FOREST_GREEN = colors.HexColor("#2C5F3E")


def generate_narrative(lca: LCAResult) -> str:
    p = lca.profile
    user = REPORT_NARRATIVE_USER.format(
        company_name=p.company_name,
        province=p.province,
        annual_units=p.annual_units,
        current_insulation=p.current_insulation,
        current_gwp_per_sqft=lca.current_gwp_per_sqft,
        cellulose_gwp_per_sqft=lca.cellulose_gwp_per_sqft,
        annual_emissions_current_tonnes=lca.annual_emissions_current_tonnes,
        annual_emissions_cellulose_tonnes=lca.annual_emissions_cellulose_tonnes,
        annual_switch_benefit_tonnes=lca.annual_switch_benefit_tonnes,
        carbon_credit_value_low_cad=lca.carbon_credit_value_low_cad,
        carbon_credit_value_high_cad=lca.carbon_credit_value_high_cad,
    )
    return chat(system=REPORT_NARRATIVE_SYSTEM, user=user, max_tokens=1024)


def render_pdf(profile: FactoryProfile, lca: LCAResult, narrative: str, report_id: int) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"{REPORTS_DIR}/report_{report_id}.pdf"

    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        rightMargin=inch,
        leftMargin=inch,
        topMargin=inch,
        bottomMargin=inch,
    )

    styles = getSampleStyleSheet()
    heading1 = ParagraphStyle("H1", parent=styles["Heading1"], textColor=FOREST_GREEN, fontSize=16)
    heading2 = ParagraphStyle("H2", parent=styles["Heading2"], textColor=FOREST_GREEN, fontSize=12)
    normal = styles["Normal"]
    small = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=colors.grey)

    story = []

    # Header
    story.append(Paragraph("CORESWAP", ParagraphStyle("Brand", parent=heading1, fontSize=22, spaceAfter=4)))
    story.append(Paragraph("Embodied Carbon Advisory Report", ParagraphStyle("Sub", parent=heading2, textColor=colors.black)))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Prepared for: {profile.company_name}", normal))
    story.append(Paragraph(f"Date: {datetime.now(timezone.utc).strftime('%B %d, %Y')}", normal))
    story.append(Paragraph(f"Report ID: {report_id}", normal))
    story.append(HRFlowable(width="100%", thickness=1, color=FOREST_GREEN, spaceAfter=12))

    # Section 1: Factory Profile
    story.append(Paragraph("Factory Profile", heading2))
    profile_data = [
        ["Field", "Value"],
        ["Company", profile.company_name],
        ["Province", profile.province],
        ["Annual Units Produced", str(profile.annual_units)],
        ["Average Home Size", f"{profile.avg_home_sqft:,} sq ft"],
        ["Current Insulation Type", profile.current_insulation.replace("_", " ").title()],
        ["Wall Assembly Ratio", str(profile.wall_assembly_ratio)],
    ]
    _add_table(story, profile_data)

    story.append(Spacer(1, 12))

    # Section 2: LCA Findings
    story.append(Paragraph("LCA Findings", heading2))
    lca_data = [
        ["Metric", "Value"],
        ["Insulated Area per Home", f"{lca.insulated_sqft_per_home:,.0f} sq ft"],
        ["Current Insulation GWP", f"{lca.current_gwp_per_sqft:.4f} kg CO2e / sq ft"],
        ["Cellulose Baseline GWP", f"{lca.cellulose_gwp_per_sqft:.4f} kg CO2e / sq ft"],
        ["Annual Emissions — Current", f"{lca.annual_emissions_current_tonnes:,.2f} tonnes CO2e"],
        ["Annual Emissions — Cellulose", f"{lca.annual_emissions_cellulose_tonnes:,.2f} tonnes CO2e"],
        ["Annual Switch Benefit", f"{lca.annual_switch_benefit_tonnes:,.2f} tonnes CO2e"],
        ["50-Year Lifetime Benefit", f"{lca.lifetime_switch_benefit_tonnes:,.2f} tonnes CO2e"],
        ["Carbon Credit Value @ $80/t", f"${lca.carbon_credit_value_low_cad:,.2f} CAD / yr"],
        ["Carbon Credit Value @ $170/t", f"${lca.carbon_credit_value_high_cad:,.2f} CAD / yr"],
    ]
    _add_table(story, lca_data)

    story.append(Spacer(1, 12))

    # Section 3: Narrative
    story.append(Paragraph("Executive Summary", heading2))
    for para in narrative.split("\n\n"):
        if para.strip():
            story.append(Paragraph(para.strip(), normal))
            story.append(Spacer(1, 6))

    story.append(Spacer(1, 12))

    # Section 4: Regulatory Note
    story.append(Paragraph("Regulatory Context", heading2))
    reg_text = (
        "Bill C-59 (An Act to implement certain provisions of the fall economic statement "
        "tabled in Parliament on November 21, 2023), which received Royal Assent on June 20, 2024, "
        "amended the Competition Act to reverse the burden of proof for environmental marketing claims. "
        "Companies making public carbon reduction claims must now be able to substantiate those claims "
        "with adequate and proper tests. The Treasury Board of Canada Secretariat Standard on Embodied "
        "Carbon in Construction (effective July 2025) requires federal procurement projects to report "
        "embodied carbon using EPD-based lifecycle assessment methodology. The analysis in this report "
        "was produced using EPD-sourced GWP data and deterministic LCA calculations, and is intended "
        "to support substantiation under these frameworks."
    )
    story.append(Paragraph(reg_text, normal))

    story.append(Spacer(1, 24))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.lightgrey))
    story.append(Spacer(1, 4))
    story.append(Paragraph(
        "Generated by CORESWAP MVP — this is a demonstration artifact, not a certified LCA.",
        small
    ))

    doc.build(story)
    return filename


def _add_table(story, data):
    t = Table(data, colWidths=[3 * inch, 3.5 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), FOREST_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F5F5")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
