import os
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from coreswap.db import init_db, save_report, list_reports, load_report
from coreswap.models import FactoryProfile
from coreswap.extraction import extract_text_from_pdf, extract_text_from_txt, extract_epd_data_via_llm
from coreswap.validation import validate_extraction
from coreswap.lca import run_lca
from coreswap.report import generate_narrative, render_pdf

init_db()

st.set_page_config(page_title="CORESWAP", layout="wide")

# Sidebar navigation
PAGES = ["1. Factory Profile", "2. Carbon Baseline", "3. Switch Modeler", "4. ESG Report"]

with st.sidebar:
    st.title("CORESWAP")
    st.caption("Embodied Carbon Advisory")
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
    st.caption(f"Upload the EPD PDF for your current insulation: **{profile.current_insulation.replace('_',' ').title()}**")

    uploaded = st.file_uploader("Upload EPD (PDF or TXT)", type=["pdf", "txt"])

    if uploaded:
        with st.spinner("Extracting text from document..."):
            if uploaded.name.endswith(".pdf"):
                raw_text = extract_text_from_pdf(uploaded.read())
            else:
                raw_text = extract_text_from_txt(uploaded.read())

        st.success(f"Extracted {len(raw_text):,} characters from document.")

        with st.spinner("Extracting carbon data with AI..."):
            try:
                extracted = extract_epd_data_via_llm(raw_text, profile.current_insulation)
            except Exception as e:
                st.error(f"LLM extraction failed: {e}")
                st.stop()

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
        st.metric("Extracted GWP", f"{gwp:.4f} kg CO2e / sq ft",
                  help="Normalized to per square foot at the EPD's stated R-value.")

        with st.spinner("Validating extracted value..."):
            validation = validate_extraction(extracted, profile.current_insulation)

        if validation.passed:
            st.success(f"Validation passed. Value is within expected range {validation.expected_range} for {profile.current_insulation}.")
            st.session_state["extracted_gwp"] = gwp
            st.session_state["extracted"] = extracted
        else:
            st.error(f"Validation failed: {validation.flagged_reason}")
            st.warning("You can override with a manual value, or re-upload the correct EPD.")
            manual_gwp = st.number_input(
                "Manual GWP override (kg CO2e / sq ft)",
                value=float(gwp), step=0.01
            )
            if st.button("Use Manual Value"):
                st.session_state["extracted_gwp"] = manual_gwp
                st.session_state["extracted"] = extracted
                st.success(f"Manual value {manual_gwp} accepted.")

    if "extracted_gwp" in st.session_state:
        st.divider()
        gwp = st.session_state["extracted_gwp"]
        from coreswap.lca import compute_insulated_sqft_per_home, compute_annual_emissions_tonnes
        insulated_sqft = compute_insulated_sqft_per_home(profile)
        annual_tonnes = compute_annual_emissions_tonnes(gwp, insulated_sqft, profile.annual_units)

        st.subheader("Annual Emissions Estimate")
        st.metric(
            label="Annual Embodied Carbon — Current Insulation",
            value=f"{annual_tonnes:,.2f} tonnes CO2e",
            delta=None,
        )
        st.caption(f"Based on {profile.annual_units} homes/yr × {insulated_sqft:,.0f} sq ft insulated/home × {gwp:.4f} kg CO2e/sq ft")

        if st.button("Run LCA →", type="primary"):
            lca = run_lca(profile, gwp)
            st.session_state["lca"] = lca
            st.success("LCA complete. Navigate to Switch Modeler.")


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
        st.session_state["nav_page"] = PAGES[3]
        st.rerun()


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
