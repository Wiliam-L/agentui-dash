"""Shared visual components (KPI cards, page headers, chart styling)."""
import re
import pandas as pd
import plotly.express as px
import streamlit as st

from ..styles import chart_colors, PALETTE


_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{3,8}$")


def _is_hex_color(value) -> bool:
    """Return True if *value* looks like a CSS hex color (e.g. '#246bfd')."""
    return isinstance(value, str) and _HEX_COLOR_RE.match(value) is not None


def page_header(icon: str, title: str, ruta: str, description: str) -> None:
    st.markdown(
        f"""
        <div class="breadcrumb">{ruta}</div>
        <div class="page-title">
            <span class="pt-ic"><span class="mi">{icon}</span></span>
            <div>
                <h1>{title}</h1>
                <div class="page-desc">{description}</div>
            </div>
        </div>
        <hr style="margin: 14px 0 22px; border:0; border-top:1px solid var(--border);">
        """,
        unsafe_allow_html=True,
    )


def open_card(title: str, subtitle: str = None, icon: str = "insights") -> str:
    head = (
        f'<div class="card-head"><span class="chip-ic"><span class="mi">{icon}</span></span>'
        f'<div><div class="card-title">{title}</div>'
        + (f'<div class="card-sub">{subtitle}</div>' if subtitle else "")
        + "</div></div>"
    )
    return f'<div class="card">{head}<div class="card-body">'


def close_card() -> str:
    return "</div></div>"


def kpi(icon: str, title: str, value, subtitle: str, accent: str, neg: bool = False) -> str:
    cls = "kpi-sub neg" if neg else "kpi-sub"
    return (
        f'<div class="kpi" style="--acc:{accent};">'
        f'<div class="kpi-top"><span class="kpi-ic"><span class="mi">{icon}</span></span>'
        f'<span class="kpi-label">{title}</span></div>'
        f'<div class="kpi-value">{value}</div>'
        f'<div class="{cls}">{subtitle}</div></div>'
    )


def fmt_num(n) -> str:
    return f"{n:,.0f}".replace(",", ".")


def fmt_money(n) -> str:
    return f"${n:,.2f}".replace(",", ".")


def fmt_short_money(n) -> str:
    """Abbreviate large monetary values: $2.3M, $2.3K, $2.3B."""
    n = float(n)
    if n < 0:
        return "-" + fmt_short_money(-n)
    if n >= 1_000_000_000:
        return f"${n / 1_000_000_000:.1f}B"
    elif n >= 1_000_000:
        return f"${n / 1_000_000:.1f}M"
    elif n >= 1_000:
        return f"${n / 1_000:.1f}K"
    else:
        return f"${n:,.2f}".replace(",", ".")


def badge(icon: str, text: str) -> str:
    return f'<span class="badge"><span class="mi">{icon}</span> {text}</span>'


def style_chart(fig, height: int = 330, hover: str = None):
    colors = chart_colors()
    fig.update_layout(
        height=height,
        paper_bgcolor=colors["paper"],
        plot_bgcolor=colors["plot"],
        font=dict(
            family="-apple-system, Segoe UI, Roboto, sans-serif",
            color=colors["font"],
            size=13,
        ),
        margin=dict(l=10, r=10, t=8, b=40),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            title_text="",
        ),
        xaxis=dict(
            tickangle=-45,
            tickfont=dict(size=11),
        ),
    )
    fig.update_xaxes(showgrid=False, linecolor=colors["line"], zeroline=False)
    fig.update_yaxes(showgrid=True, gridcolor=colors["grid"], zeroline=False)
    if hover:
        fig.update_traces(hovertemplate=hover)
    return fig


# --------------------------------------------------------------------------- #
# Dynamic chart renderer — reads JSON config and dispatches to Plotly
# --------------------------------------------------------------------------- #
def render_chart(chart_config: dict, df: pd.DataFrame) -> None:
    """Render a Plotly chart from a JSON config dict and DataFrame.

    Supports chart types: bar, pie, line, scatter, bar_h, heatmap,
    bar_grouped, bar_stacked.

    The config dict keys map to Plotly parameters:
      - tipo: chart type (bar, pie, line, scatter, bar_h, heatmap, bar_grouped, bar_stacked)
      - x, y: column names for axes
      - columna: column name for pie charts (names)
      - valores: column name for pie/heatmap values
      - color: column name for color grouping
      - titulo: chart title (displayed in card header, not used here)
      - alto: figure height (default 350)
    """
    if df.empty:
        return

    tipo = chart_config.get("tipo", "bar")
    alto = chart_config.get("alto", 350)

    if tipo == "bar":
        x = chart_config.get("x")
        y = chart_config.get("y")
        color_raw = chart_config.get("color")
        if not x or not y:
            return
        # Distinguish: hex color (styling) vs column name (grouping)
        if _is_hex_color(color_raw):
            fig = px.bar(df, x=x, y=y, color_discrete_sequence=[color_raw])
            show_legend = False
        else:
            color_col = color_raw  # treat as column name for grouping
            fig = px.bar(df, x=x, y=y, color=color_col,
                         color_discrete_sequence=PALETTE)
            show_legend = bool(color_col)
        fig.update_traces(marker_line_width=0,
                          hovertemplate="<b>%{x}</b><br>%{y:$,.2f}<extra></extra>")
        style_chart(fig, height=alto)
        fig.update_layout(showlegend=show_legend, xaxis=dict(title=""), yaxis=dict(title=""))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    elif tipo == "bar_h":
        x = chart_config.get("x")
        y = chart_config.get("y")
        color_raw = chart_config.get("color")
        if not x or not y:
            return
        if _is_hex_color(color_raw):
            fig = px.bar(df, x=x, y=y, orientation="h",
                         color_discrete_sequence=[color_raw])
            show_legend = False
        elif color_raw:
            fig = px.bar(df, x=x, y=y, orientation="h", color=color_raw,
                         color_discrete_sequence=PALETTE)
            show_legend = True
        else:
            fig = px.bar(df, x=x, y=y, orientation="h",
                         color_discrete_sequence=PALETTE)
            show_legend = False
        fig.update_traces(marker_line_width=0,
                          hovertemplate="<b>%{y}</b><br>%{x:$,.2f}<extra></extra>")
        style_chart(fig, height=alto)
        fig.update_layout(showlegend=show_legend, xaxis=dict(showticklabels=False), yaxis=dict(title=""))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    elif tipo == "pie":
        columna = chart_config.get("columna")
        valores = chart_config.get("valores")
        if not columna or not valores:
            return
        fig = px.pie(df, names=columna, values=valores, hole=0.58,
                     color_discrete_sequence=PALETTE)
        fig.update_traces(textinfo="percent", textposition="inside",
                          textfont=dict(color="white", size=12),
                          hovertemplate="<b>%{label}</b><br>%{value:$,.2f} · %{percent}<extra></extra>")
        style_chart(fig, height=alto)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    elif tipo == "line":
        x = chart_config.get("x")
        y = chart_config.get("y")
        color_raw = chart_config.get("color")
        if not x or not y:
            return
        if _is_hex_color(color_raw):
            fig = px.line(df, x=x, y=y, color_discrete_sequence=[color_raw])
            show_legend = False
        else:
            fig = px.line(df, x=x, y=y, color=color_raw,
                          color_discrete_sequence=PALETTE)
            show_legend = bool(color_raw)
        style_chart(fig, height=alto)
        fig.update_layout(showlegend=show_legend, xaxis=dict(title=""), yaxis=dict(title=""))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    elif tipo == "scatter":
        x = chart_config.get("x")
        y = chart_config.get("y")
        color_raw = chart_config.get("color")
        size = chart_config.get("size")
        if not x or not y:
            return
        if _is_hex_color(color_raw):
            fig = px.scatter(df, x=x, y=y, size=size,
                             color_discrete_sequence=[color_raw], opacity=0.8)
        else:
            fig = px.scatter(df, x=x, y=y, color=color_raw, size=size,
                             color_discrete_sequence=PALETTE, opacity=0.8)
        fig.update_traces(marker=dict(line=dict(width=1, color="#ffffff")),
                          hovertemplate="<b>%{color}</b><br>%{x:,.0f}<br>%{y:.1f}<extra></extra>")
        style_chart(fig, height=alto)
        fig.update_layout(xaxis=dict(title=""), yaxis=dict(title=""))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    elif tipo == "heatmap":
        x = chart_config.get("x")
        y = chart_config.get("y")
        valores = chart_config.get("valores")
        if not x or not y or not valores:
            return
        cruz = pd.pivot_table(df, index=y, columns=x, values=valores, aggfunc="sum").fillna(0)
        fig = px.imshow(cruz, text_auto=True, aspect="auto",
                        color_continuous_scale=["#e0f2fe", "#246bfd"])
        fig.update_layout(height=alto, margin=dict(l=10, r=10, t=8, b=10),
                          paper_bgcolor="rgba(0,0,0,0)",
                          font=dict(color="#334155", size=12))
        fig.update_traces(textfont=dict(color="#0f172a"))
        fig.update_xaxes(title="")
        fig.update_yaxes(title="")
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    elif tipo == "bar_grouped":
        x = chart_config.get("x")
        y = chart_config.get("y")
        color_raw = chart_config.get("color")
        if not x or not y:
            return
        if _is_hex_color(color_raw):
            fig = px.bar(df, x=x, y=y, barmode="group",
                         color_discrete_sequence=[color_raw])
        else:
            fig = px.bar(df, x=x, y=y, color=color_raw, barmode="group",
                         color_discrete_sequence=PALETTE)
        fig.update_traces(hovertemplate="<b>%{x}</b><br>%{color}: %{y:,}<extra></extra>")
        style_chart(fig, height=alto)
        fig.update_layout(xaxis=dict(title=""), yaxis=dict(title=""))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    elif tipo == "bar_stacked":
        x = chart_config.get("x")
        y = chart_config.get("y")
        color_raw = chart_config.get("color")
        if not x or not y:
            return
        if _is_hex_color(color_raw):
            fig = px.bar(df, x=x, y=y, barmode="stack",
                         color_discrete_sequence=[color_raw])
        else:
            fig = px.bar(df, x=x, y=y, color=color_raw, barmode="stack",
                         color_discrete_sequence=PALETTE)
        fig.update_traces(hovertemplate="<b>%{x}</b><br>%{color}: %{y:,}<extra></extra>")
        style_chart(fig, height=alto)
        fig.update_layout(xaxis=dict(title=""), yaxis=dict(title=""))
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
