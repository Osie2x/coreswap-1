from typing import Optional, Union
import plotly.graph_objects as go
from plotly.subplots import make_subplots


def _gwp_color(gwp: float) -> str:
    """Return hex fill color for an insulation rectangle given its GWP."""
    if gwp <= -0.4:
        return "#2C5F3E"
    elif gwp <= 0.0:
        return "#8FBC8F"
    elif gwp <= 1.0:
        return "#F4A460"
    elif gwp <= 2.5:
        return "#CD5C5C"
    else:
        return "#8B0000"


def _add_wall_panel(
    fig: go.Figure,
    col: int,
    insulation_label: str,
    insulation_color: str,
    panel_title: str,
) -> None:
    """
    Draw a 4-layer wall cross-section into the given subplot column.

    Layer y-ranges (bottom to top, out of a 10-unit canvas):
        Drywall    0.0 – 1.0   (thin, white)
        Insulation 1.0 – 7.5   (thick, colored)
        Sheathing  7.5 – 8.5   (thin, medium grey)
        Cladding   8.5 – 10.0  (thin, dark grey)

    x-range: 0 – 4  (normalised)
    """
    layers = [
        # (y0, y1, fill, line_color, label, hover)
        (0.0,  1.0,  "#F5F5F5", "#AAAAAA", "Drywall",    "Interior drywall — gypsum board finish layer"),
        (1.0,  7.5,  insulation_color, "#555555", insulation_label,
         f"{insulation_label} — primary thermal & carbon layer"),
        (7.5,  8.5,  "#999999", "#555555", "Sheathing",  "Structural sheathing — OSB or plywood"),
        (8.5,  10.0, "#444444", "#222222", "Cladding",   "Exterior cladding — weather barrier"),
    ]

    x0, x1 = 0.0, 4.0
    row = 1

    for y0, y1, fill, line_col, label, hover_text in layers:
        fig.add_shape(
            type="rect",
            x0=x0, y0=y0, x1=x1, y1=y1,
            fillcolor=fill,
            line=dict(color=line_col, width=1),
            row=row, col=col,
        )
        # Layer label centred inside the rectangle
        text_color = "#FFFFFF" if fill in ("#444444", "#2C5F3E", "#CD5C5C", "#8B0000") else "#222222"
        fig.add_annotation(
            x=(x0 + x1) / 2,
            y=(y0 + y1) / 2,
            text=label,
            showarrow=False,
            font=dict(size=11, color=text_color, family="Arial"),
            xref=f"x{col if col > 1 else ''}",
            yref=f"y{col if col > 1 else ''}",
        )

    # Invisible scatter trace to carry hover text for each layer
    # (shapes don't support hover natively in plotly)
    for y0, y1, fill, line_col, label, hover_text in layers:
        fig.add_trace(
            go.Scatter(
                x=[(x0 + x1) / 2],
                y=[(y0 + y1) / 2],
                mode="markers",
                marker=dict(size=1, color="rgba(0,0,0,0)"),
                hovertemplate=f"<b>{label}</b><br>{hover_text}<extra></extra>",
                showlegend=False,
            ),
            row=row, col=col,
        )

    # Panel title annotation (above the wall)
    fig.add_annotation(
        x=(x0 + x1) / 2,
        y=10.6,
        text=panel_title,
        showarrow=False,
        font=dict(size=10, color="#333333", family="Arial"),
        align="center",
        xref=f"x{col if col > 1 else ''}",
        yref=f"y{col if col > 1 else ''}",
    )


def build_wall_assembly_figure(
    current_label: str,
    current_gwp: float,
    compare_label: str,
    compare_gwp: float,
    profile,  # FactoryProfile — typed loosely to avoid circular import
) -> go.Figure:
    """
    Return a Plotly Figure with two side-by-side wall cross-section panels.

    Left  — current insulation (recolors with current_gwp).
    Right — comparison insulation (recolors with compare_gwp).
    Arrow annotation between panels shows the annual CO2e benefit.

    No Streamlit imports. Pure function.
    """
    from coreswap.lca import compute_annual_emissions_tonnes, compute_insulated_sqft_per_home

    insulated_sqft = compute_insulated_sqft_per_home(profile)
    current_tonnes = compute_annual_emissions_tonnes(current_gwp, insulated_sqft, profile.annual_units)
    compare_tonnes = compute_annual_emissions_tonnes(compare_gwp, insulated_sqft, profile.annual_units)
    annual_benefit = round(current_tonnes - compare_tonnes, 2)

    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=["", ""],  # We use custom annotations instead
        horizontal_spacing=0.18,
    )

    left_title = (
        f"Current: {current_label}<br>"
        f"GWP {round(current_gwp, 2)} kg CO\u2082e/sqft | "
        f"Annual {round(current_tonnes, 2)} t CO\u2082e"
    )
    right_title = (
        f"{compare_label}<br>"
        f"GWP {round(compare_gwp, 2)} kg CO\u2082e/sqft | "
        f"Annual {round(compare_tonnes, 2)} t CO\u2082e"
    )

    _add_wall_panel(fig, col=1, insulation_label=current_label,
                    insulation_color=_gwp_color(current_gwp), panel_title=left_title)
    _add_wall_panel(fig, col=2, insulation_label=compare_label,
                    insulation_color=_gwp_color(compare_gwp), panel_title=right_title)

    # Arrow between panels (paper-space coordinates)
    benefit_sign = "-" if annual_benefit >= 0 else "+"
    benefit_abs = abs(annual_benefit)
    arrow_label = f"{benefit_sign}{benefit_abs:.2f} t CO\u2082e/yr saved"

    fig.add_annotation(
        x=0.62,      # right end of arrow (paper coords)
        y=0.50,
        ax=-80,      # pixel offset leftward for arrow tail
        ay=0,
        xref="paper",
        yref="paper",
        axref="pixel",
        ayref="pixel",
        text=arrow_label,
        showarrow=True,
        arrowhead=3,
        arrowsize=1.4,
        arrowwidth=2.5,
        arrowcolor="#2C5F3E",
        font=dict(size=11, color="#2C5F3E", family="Arial Bold"),
        align="center",
    )

    fig.update_layout(
        height=500,
        showlegend=False,
        plot_bgcolor="white",
        paper_bgcolor="white",
        margin=dict(t=90, b=30, l=30, r=30),
    )

    # Fix axis ranges for both panels so shapes align properly
    for axis in ["xaxis", "xaxis2"]:
        fig.update_layout(**{axis: dict(range=[-0.2, 4.2], showticklabels=False,
                                         showgrid=False, zeroline=False)})
    for axis in ["yaxis", "yaxis2"]:
        fig.update_layout(**{axis: dict(range=[-0.5, 11.5], showticklabels=False,
                                         showgrid=False, zeroline=False)})

    return fig
