import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from coreswap.db import init_db, save_report, list_reports, load_report
from coreswap.models import FactoryProfile
from coreswap.extraction import extract_text_from_pdf, extract_text_from_txt, extract_epd_data_via_llm
from coreswap.validation import validate_extraction
from coreswap.lca import run_lca
from coreswap.lca import compute_annual_emissions_tonnes, compute_insulated_sqft_per_home
from coreswap.visualizer import build_wall_assembly_figure
from coreswap.report import generate_narrative, render_pdf
from coreswap.llm import active_provider_label

init_db()

st.set_page_config(page_title="CORESWAP", layout="wide")

# Sidebar navigation
PAGES = ["1. Factory Profile", "2. Carbon Baseline", "3. Switch Modeler", "4. ESG Report"]

with st.sidebar:
    st.title("CORESWAP")
    st.caption("Embodied Carbon Advisory")
    st.caption(f"LLM: {active_provider_label()}")
    page = st.radio("Navigation", PAGES, key="nav_page")
    st.divider()
    st.subheader("Past Reports")
    past = list_reports()
    if past:
        for rec in past:
            label = f"{rec['id']} — {rec['company_name']} ({rec['created_at'][:10]})"
            if st.button(label, key=f"past_{rec['id']}"):
                loaded = load_report(rec["id"])
                if loaded:
                    st.session_state["profile"] = loaded.profile
                    st.session_state["lca"] = loaded.lca
                    st.session_state["narrative"] = loaded.narrative_summary
                    st.session_state["pdf_path"] = loaded.pdf_path
                    st.session_state["report_id"] = loaded.id
                    st.rerun()
    else:
        st.caption("No reports yet.")

# ─── Page 1: Factory Profile ───────────────────────────────────────────────
if page == PAGES[0]:
    st.header("Factory Profile")
    st.caption("Enter your manufacturing facility details.")

    with st.form("profile_form"):
        company_name = st.text_input("Company Name", value=st.session_state.get("profile", FactoryProfile(
            company_name="", province="ON", annual_units=100, avg_home_sqft=1500,
            current_insulation="spray_foam_hfc")).company_name)
        province = st.selectbox("Province / Territory", [
            "ON", "QC", "BC", "AB", "MB", "SK", "NS", "NB", "PE", "NL", "YT", "NT", "NU"
        ])
        annual_units = st.number_input("Annual Homes Produced", min_value=1, max_value=100000, value=100)
        avg_home_sqft = st.number_input("Average Home Size (sq ft)", min_value=400, max_value=10000, value=1500)
        current_insulation = st.selectbox("Current Insulation Type", [
            "spray_foam_hfc", "spray_foam_hfo", "fiberglass", "mineral_wool", "cellulose"
        ], format_func=lambda x: x.replace("_", " ").title())
        wall_assembly_ratio = st.slider(
            "Wall Assembly Ratio (insulated area / floor area)",
            min_value=1.0, max_value=3.0, value=1.6, step=0.1,
            help="Industry heuristic: 1.6 accounts for walls, roof, and floor insulation."
        )
        submitted = st.form_submit_button("Save Profile & Continue")

    if submitted:
        if not company_name.strip():
            st.error("Company name is required.")
        else:
            profile = FactoryProfile(
                company_name=company_name.strip(),
                province=province,
                annual_units=annual_units,
                avg_home_sqft=avg_home_sqft,
                current_insulation=current_insulation,
                wall_assembly_ratio=wall_assembly_ratio,
            )
            st.session_state["profile"] = profile
            st.success(f"Profile saved for {profile.company_name}. Navigate to Carbon Baseline.")

    if "profile" in st.session_state:
        st.subheader("Saved Profile")
        p = st.session_state["profile"]
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Company", p.company_name)
            st.metric("Province", p.province)
            st.metric("Annual Units", p.annual_units)
        with col2:
            st.metric("Home Size", f"{p.avg_home_sqft:,} sq ft")
            st.metric("Insulation", p.current_insulation.replace("_", " ").title())
            st.metric("Wall Ratio", p.wall_assembly_ratio)


# ─── Page 2: Carbon Baseline ───────────────────────────────────────────────
elif page == PAGES[1]:
    st.header("Carbon Baseline")

    if "profile" not in st.session_state:
        st.warning("Complete Factory Profile first.")
        st.stop()

    profile = st.session_state["profile"]

    # ── What is an EPD? ────────────────────────────────────────────────────
    with st.expander("ℹ️  What is an EPD and where do I get one?", expanded=False):
        st.markdown("""
**EPD = Environmental Product Declaration**

An EPD is a standardised document published by a product manufacturer that reports
the environmental impact of their product — including its **Global Warming Potential (GWP)**,
measured in kg CO₂e per unit. Think of it like a nutrition label, but for carbon.

**Where to download a free EPD for your insulation:**
- [EC3 Tool (buildingtransparency.org)](https://buildingtransparency.org/ec3) — largest free database, filter by "Insulation"
- [EPD International Library (environdec.com)](https://www.environdec.com/library) — global registry
- Your insulation manufacturer's website — search "[brand name] EPD PDF"

**What file to upload here:**
Upload the PDF your insulation manufacturer published. The AI will read it and
extract the GWP number automatically. If you don't have a PDF, use the
**"Enter GWP manually"** option below instead.

**Typical GWP values by insulation type:**
| Type | Typical GWP (kg CO₂e/sqft) |
|---|---|
| Spray Foam HFC | 3.0 – 5.5 (high emitter) |
| Spray Foam HFO | 0.5 – 1.8 |
| Fiberglass | 0.3 – 1.5 |
| Mineral Wool | 0.3 – 1.2 |
| Cellulose | −1.0 to −0.4 (carbon sink) |
        """)

    st.caption(f"Insulation type from your profile: **{profile.current_insulation.replace('_', ' ').title()}**")

    # ── Input mode toggle ──────────────────────────────────────────────────
    input_mode = st.radio(
        "How do you want to enter your carbon data?",
        ["Upload EPD document (PDF or TXT)", "Enter GWP manually (skip upload)"],
        horizontal=True,
    )

    if input_mode == "Upload EPD document (PDF or TXT)":
        uploaded = st.file_uploader("Upload your insulation EPD", type=["pdf", "txt"])

        if uploaded:
            with st.spinner("Reading document..."):
                if uploaded.name.endswith(".pdf"):
                    raw_text = extract_text_from_pdf(uploaded.read())
                else:
                    raw_text = extract_text_from_txt(uploaded.read())

            st.success(f"Extracted {len(raw_text):,} characters from document.")

            with st.spinner("AI is extracting the GWP value..."):
                try:
                    extracted = extract_epd_data_via_llm(raw_text, profile.current_insulation)
                    extraction_ok = True
                except Exception as e:
                    st.error(f"AI extraction failed: {e}")
                    st.warning("You can still continue — enter the GWP manually below.")
                    extraction_ok = False
                    extracted = None

            if extraction_ok and extracted:
                st.subheader("Extracted EPD Data")
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Product:** {extracted.product_name}")
                    st.write(f"**Manufacturer:** {extracted.manufacturer}")
                    st.write(f"**Declared Unit:** {extracted.declared_unit}")
                    st.write(f"**Confidence:** {extracted.extraction_confidence}")
                with col2:
                    st.write(f"**Reference Standard:** {extracted.reference_standard or 'N/A'}")
                    st.write(f"**Validity Year:** {extracted.validity_year or 'N/A'}")
                    st.write(f"**Notes:** {extracted.extraction_notes}")

                gwp = extracted.gwp_kg_co2e_per_sqft
                st.metric("Extracted GWP", f"{gwp:.4f} kg CO₂e / sq ft")

                validation = validate_extraction(extracted, profile.current_insulation)
                if validation.passed:
                    st.success(f"Value validated — within expected range {validation.expected_range} for {profile.current_insulation}.")
                    st.session_state["extracted_gwp"] = gwp
                    st.session_state["extracted"] = extracted
                else:
                    st.warning(f"Validation note: {validation.flagged_reason}")
                    st.info("You can accept this value or override it below.")
                    override = st.number_input("Override GWP (kg CO₂e / sq ft)", value=float(gwp), step=0.01)
                    if st.button("Accept & Use This Value"):
                        st.session_state["extracted_gwp"] = override
                        st.session_state["extracted"] = extracted

            if not extraction_ok:
                st.subheader("Enter GWP manually")
                manual_gwp = st.number_input(
                    "GWP value from your EPD (kg CO₂e / sq ft)",
                    min_value=-2.0, max_value=10.0,
                    value=4.20, step=0.01,
                    help="Find this number in your EPD under 'Global Warming Potential' or 'GWP', modules A1-A3."
                )
                if st.button("Use This Value →"):
                    st.session_state["extracted_gwp"] = manual_gwp
                    st.session_state["extracted"] = None

    else:
        # Manual entry path — no upload needed
        st.info("Enter the GWP value directly from your insulation manufacturer's EPD or data sheet.")
        col_m1, col_m2 = st.columns([2, 1])
        with col_m1:
            manual_gwp = st.number_input(
                "GWP (kg CO₂e per sq ft) — find this in your EPD under 'Global Warming Potential', modules A1–A3",
                min_value=-2.0, max_value=10.0,
                value=4.20, step=0.01,
            )
        with col_m2:
            st.metric("Selected GWP", f"{manual_gwp:.2f} kg CO₂e/sqft")
        if st.button("Use This Value →", key="manual_submit"):
            st.session_state["extracted_gwp"] = manual_gwp
            st.session_state["extracted"] = None
            st.success("GWP saved. See the estimate below.")

    # ── Emissions estimate + Run LCA ───────────────────────────────────────
    if "extracted_gwp" in st.session_state:
        st.divider()
        gwp = st.session_state["extracted_gwp"]
        from coreswap.lca import compute_insulated_sqft_per_home, compute_annual_emissions_tonnes
        insulated_sqft = compute_insulated_sqft_per_home(profile)
        annual_tonnes = compute_annual_emissions_tonnes(gwp, insulated_sqft, profile.annual_units)

        st.subheader("Annual Emissions Estimate")
        st.metric(
            label="Annual Embodied Carbon — Current Insulation",
            value=f"{annual_tonnes:,.2f} tonnes CO₂e",
        )
        st.caption(f"Based on {profile.annual_units} homes/yr × {insulated_sqft:,.0f} sq ft insulated/home × {gwp:.4f} kg CO₂e/sq ft")

        if st.button("Run LCA & go to Switch Modeler →", type="primary"):
            lca = run_lca(profile, gwp)
            st.session_state["lca"] = lca
            st.success("LCA complete. Click '3. Switch Modeler' in the sidebar.")


# ─── Page 3: Switch Modeler ────────────────────────────────────────────────
elif page == PAGES[2]:
    st.header("Switch Modeler")

    if "lca" not in st.session_state:
        st.warning("Complete Carbon Baseline first.")
        st.stop()

    lca = st.session_state["lca"]
    p = lca.profile

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Current Annual Emissions", f"{lca.annual_emissions_current_tonnes:,.2f} t CO2e")
        st.metric("Current GWP", f"{lca.current_gwp_per_sqft:.4f} kg CO2e/sqft")
    with col2:
        st.metric("Cellulose Annual Emissions", f"{lca.annual_emissions_cellulose_tonnes:,.2f} t CO2e")
        st.metric("Cellulose GWP", f"{lca.cellulose_gwp_per_sqft:.4f} kg CO2e/sqft")
    with col3:
        st.metric("Annual Switch Benefit", f"{lca.annual_switch_benefit_tonnes:,.2f} t CO2e", delta="improvement")
        st.metric("50-Year Benefit", f"{lca.lifetime_switch_benefit_tonnes:,.2f} t CO2e")

    st.divider()

    # ── Wall Assembly Visualizer ────────────────────────────────────────────
    st.subheader("Wall Assembly Visualizer")
    st.caption(
        "Explore how changing insulation GWP or comparing against alternatives "
        "shifts embodied carbon across your annual build volume."
    )

    _COMPARE_OPTIONS = {
        "Cellulose (-0.73)": ("Cellulose", -0.73),
        "Fiberglass (0.70)": ("Fiberglass", 0.70),
        "Mineral Wool (0.60)": ("Mineral Wool", 0.60),
    }

    viz_col1, viz_col2 = st.columns([3, 2])
    with viz_col1:
        whatif_gwp = st.slider(
            "What-if: override current insulation GWP (kg CO\u2082e/sqft)",
            min_value=-2.0,
            max_value=6.0,
            step=0.1,
            value=float(round(lca.current_gwp_per_sqft, 1)),
        )
    with viz_col2:
        compare_choice = st.radio(
            "Compare against",
            list(_COMPARE_OPTIONS.keys()),
            index=0,
            horizontal=True,
        )

    _compare_label, _compare_gwp = _COMPARE_OPTIONS[compare_choice]
    _current_label = p.current_insulation.replace("_", " ").title()

    _viz_fig = build_wall_assembly_figure(
        current_label=_current_label,
        current_gwp=whatif_gwp,
        compare_label=_compare_label,
        compare_gwp=_compare_gwp,
        profile=p,
    )
    st.plotly_chart(_viz_fig, use_container_width=True)

    st.divider()

    # Emissions comparison chart
    import pandas as pd
    chart_data = pd.DataFrame({
        "Insulation": [p.current_insulation.replace("_", " ").title(), "Cellulose (Baseline)"],
        "Annual Emissions (tonnes CO2e)": [
            lca.annual_emissions_current_tonnes,
            lca.annual_emissions_cellulose_tonnes,
        ],
    }).set_index("Insulation")
    st.subheader("Annual Emissions Comparison")
    st.bar_chart(chart_data)

    st.divider()

    # Carbon credit value
    col_a, col_b = st.columns(2)
    with col_a:
        st.metric("Carbon Credit Value @ $80/tonne", f"${lca.carbon_credit_value_low_cad:,.2f} CAD/yr")
    with col_b:
        st.metric("Carbon Credit Value @ $170/tonne", f"${lca.carbon_credit_value_high_cad:,.2f} CAD/yr")

    st.divider()

    # Stubbed compliance badges
    st.subheader("Compliance Indicators")
    badge_col1, badge_col2 = st.columns(2)
    with badge_col1:
        st.success("✅ CAN/ULC 703:2025 — Code Compliance: Green Light")
    with badge_col2:
        st.success("✅ Fire Rating: Class I")

    st.caption("Note: Compliance indicators are static stubs. Full code compliance RAG is a V2 feature.")

    # Stubbed incentives
    st.subheader("Available Incentive Programs")
    st.info(
        "**Demo data — not verified for current eligibility.**\n\n"
        "- Ontario Home Renovation Savings Program (HRSP)\n"
        "- Low Carbon Economy Fund — SME Stream (Natural Resources Canada)\n"
        "- SR&ED Investment Tax Credit (Canada Revenue Agency)"
    )

    if st.button("Generate ESG Report →", type="primary"):
        st.info("Navigate to ESG Report in the sidebar to continue.")


# ─── Page 4: ESG Report ────────────────────────────────────────────────────
elif page == PAGES[3]:
    st.header("ESG Report")

    if "lca" not in st.session_state:
        st.warning("Complete Carbon Baseline first.")
        st.stop()

    lca = st.session_state["lca"]

    # Generate if not already done
    if "narrative" not in st.session_state:
        with st.spinner("Generating executive summary..."):
            try:
                narrative = generate_narrative(lca)
                st.session_state["narrative"] = narrative
            except Exception as e:
                st.error(f"Narrative generation failed: {e}")
                st.stop()

    narrative = st.session_state["narrative"]

    if "pdf_path" not in st.session_state:
        # Determine report_id (temp 0 for first render, real id after save)
        with st.spinner("Rendering PDF..."):
            try:
                report_id = save_report(lca.profile, lca, narrative, "pending")
                pdf_path = render_pdf(lca.profile, lca, narrative, report_id)
                # Update db with real path
                from coreswap.db import _conn
                with _conn() as con:
                    con.execute("UPDATE reports SET pdf_path=? WHERE id=?", (pdf_path, report_id))
                    con.commit()
                st.session_state["pdf_path"] = pdf_path
                st.session_state["report_id"] = report_id
            except Exception as e:
                st.error(f"PDF generation failed: {e}")
                st.stop()

    pdf_path = st.session_state["pdf_path"]
    report_id = st.session_state.get("report_id", "—")

    st.subheader(f"Executive Summary — Report #{report_id}")
    st.write(narrative)

    st.divider()

    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        st.download_button(
            label="Download PDF Report",
            data=pdf_bytes,
            file_name=f"coreswap_report_{report_id}.pdf",
            mime="application/pdf",
        )
    else:
        st.warning("PDF file not found. It may have been moved or deleted.")
