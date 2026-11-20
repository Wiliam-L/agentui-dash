"""Styles, icon fonts and presentation helpers (light theme CSS)."""
import base64
from pathlib import Path

import streamlit as st

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ICON_FONT = BASE_DIR / "assets" / "fonts" / "MaterialIcons-Regular.ttf"


@st.cache_resource
def _font_iconos_b64() -> str:
    if ICON_FONT.exists():
        return base64.b64encode(ICON_FONT.read_bytes()).decode()
    return ""


def colores_grafico() -> dict:
    return {
        "paper": "rgba(0,0,0,0)",
        "plot": "rgba(0,0,0,0)",
        "grid": "#e2e8f0",
        "font": "#334155",
        "line": "#cbd5e1",
    }


def aplicar_estilos() -> None:
    st.markdown(_css(), unsafe_allow_html=True)


PALETA = [
    "#246bfd",
    "#12b76a",
    "#f59e0b",
    "#8b5cf6",
    "#ef4444",
    "#06b6d4",
    "#f97316",
    "#14b8a6",
    "#e11d48",
    "#6366f1",
]


def _css() -> str:
    return f"""
<style>
@font-face {{
    font-family: "Material Icons";
    src: url(data:font/ttf;base64,{_font_iconos_b64()}) format("truetype");
}}

:root {{
    color-scheme: light;
    --bg: #f8fafc;
    --card: #ffffff;
    --border: #e2e8f0;
    --head: #0f172a;
    --body: #334155;
    --muted: #64748b;
    --primary: #2563eb;
    --green: #10b981;
    --shadow: 0 1px 3px rgba(0,0,0,.04);
    --chip-bg: #eff6ff;
    --tab-inactive: #64748b;
    --table-border: #e2e8f0;
    --badge-bg: #ecfdf5;
    --badge-color: #047857;
    --badge-border: #a7f3d0;
    --toolbar: #0f172a;
    --side-bg: #ffffff;
    --side-border: #e2e8f0;
    --side-text: #334155;
    --side-strong: #0f172a;
    --side-muted: #64748b;
    --side-input-bg: #f8fafc;
    --side-input-border: #cbd5e1;
    --side-input-text: #0f172a;
    --side-tag-bg: #e2e8f0;
    --side-sep: #f1f5f9;
    --side-focus-bg: #eff6ff;
    --side-focus-border: #2563eb;
    --nav-color: #475569;
    --nav-hover: #f1f5f9;
    --nav-hover-color: #0f172a;
    --input-panel-bg: #f8fafc;
    --field-bg: #f8fafc;
    --field-border: #cbd5e1;
    --field-text: #0f172a;
    --tag-bg: #e2e8f0;
    --tag-text: #0f172a;
}}

html, body, [class*="css"] {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }}
.stApp {{ background-color: var(--bg); color: var(--head); }}
div.block-container {{ padding-top: 1.6rem; padding-bottom: 2.5rem; max-width: 1400px; }}

[data-testid="stHeader"] {{ background: var(--bg); }}
[data-testid="stToolbar"] {{ background: var(--bg); }}
[data-testid="stToolbar"] [data-testid="stElementToolbar"] button,
[data-testid="stToolbar"] [data-testid="stBaseButton-header"],
[data-testid="stToolbar"] button {{
    color: var(--toolbar) !important;
}}
[data-testid="stToolbar"] [data-testid="stElementToolbar"] button:hover,
[data-testid="stToolbar"] button:hover {{ color: var(--primary) !important; }}
[data-testid="stStatusWidget"] {{ color: var(--toolbar) !important; }}

.card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 22px;
    box-shadow: var(--shadow);
    margin-bottom: 18px;
}}
.card-head {{ display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }}
.card-title {{ font-size: 1.05rem; font-weight: 700; color: var(--head); letter-spacing: -.01em; }}
.card-sub {{ font-size: .85rem; color: var(--muted); margin-top: 2px; }}
.mi {{
    font-family: "Material Icons";
    font-weight: normal; font-style: normal;
    line-height: 1; letter-spacing: normal; text-transform: none;
    display: inline-block; white-space: nowrap; word-wrap: normal;
    direction: ltr; font-feature-settings: "liga"; -webkit-font-feature-settings: "liga";
    vertical-align: middle; font-size: 20px; user-select: none;
}}
.chip-ic {{
    width: 34px; height: 34px; border-radius: 9px; flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    background: var(--chip-bg); color: var(--primary); font-size: 18px;
}}

.kpi {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px 20px;
    box-shadow: var(--shadow);
    height: 100%;
    flex: 1;
    display: flex;
    flex-direction: column;
}}
.kpi-top {{ display: flex; align-items: center; gap: 14px; }}
.kpi-ic {{
    width: 40px; height: 40px; border-radius: 10px; flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    background: color-mix(in srgb, var(--acc) 12%, transparent);
    color: var(--acc); font-size: 22px;
}}
.kpi-label {{ font-size: .8rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .07em; }}
.kpi-value {{ font-size: 1.8rem; font-weight: 800; color: var(--head); margin-top: 12px; letter-spacing: -.02em; }}
.kpi-sub {{ font-size: .85rem; color: var(--green); margin-top: 5px; font-weight: 500; }}
.kpi-sub.neg {{ color: #ef4444; }}

.page-title {{ display: flex; align-items: center; gap: 14px; margin-bottom: 4px; }}
.page-title .pt-ic {{
    width: 46px; height: 46px; border-radius: 12px; flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg,#2563eb,#60a5fa); color: #fff; font-size: 24px;
    box-shadow: 0 4px 12px rgba(37,99,235,.2);
}}
.page-title h1 {{ font-size: 1.6rem; font-weight: 800; color: var(--head); margin: 0; letter-spacing: -.02em; }}
.breadcrumb {{ color: var(--muted); font-size: .82rem; letter-spacing: .05em; margin-bottom: 4px; }}
.page-desc {{ color: var(--body); font-size: .95rem; margin-bottom: 6px; }}

section[data-testid="stSidebar"] {{ background-color: var(--side-bg); border-right: 1px solid var(--side-border); }}
section[data-testid="stSidebar"] * {{ color: var(--side-text); }}
section[data-testid="stSidebar"] .stMarkdown p {{ margin-bottom: 0; }}
.brand {{ display: flex; align-items: center; gap: 12px; padding: 8px 2px 6px; }}
.brand-ic {{
    width: 38px; height: 38px; border-radius: 10px; flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg,#2563eb,#38bdf8); color: #fff; font-size: 22px;
    box-shadow: 0 4px 10px rgba(37,99,235,.25);
}}
.brand-name {{ font-size: 1rem; font-weight: 800; color: var(--side-strong); letter-spacing: -.01em; }}
.brand-sub {{ font-size: .8rem; color: var(--side-muted); }}
.side-sep {{ height: 1px; background: var(--side-sep); margin: 14px 0; }}
.side-label {{ color: var(--side-muted); font-size: .78rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; margin-bottom: 8px; }}

section[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 2px; }}
section[data-testid="stSidebar"] [role="radiogroup"] label {{
    display: flex; align-items: center; gap: 10px;
    padding: 9px 12px; margin: 1px 0; border-radius: 9px;
    color: var(--nav-color); font-size: .95rem; font-weight: 500;
    cursor: pointer; transition: background .15s ease, color .15s ease;
}}
section[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: var(--nav-hover); color: var(--nav-hover-color); }}
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
    background: var(--side-focus-bg); color: var(--side-strong);
    box-shadow: inset 0 0 0 1px var(--side-focus-border);
}}
section[data-testid="stSidebar"] [role="radiogroup"] input {{ accent-color: #2563eb; }}

section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {{
    color: var(--side-muted); font-size: .78rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
}}
section[data-testid="stSidebar"] [data-baseweb="select"] > div,
section[data-testid="stSidebar"] [data-testid="stMultiSelect"] [role="group"][data-rac],
section[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="group"][data-rac] {{
    background: var(--side-input-bg); border-color: var(--side-input-border) !important; border-radius: 9px;
}}
section[data-testid="stSidebar"] [data-baseweb="select"] span,
section[data-testid="stSidebar"] [data-baseweb="select"] input,
section[data-testid="stSidebar"] [data-testid="stMultiSelect"] input,
section[data-testid="stSidebar"] [data-testid="stSelectbox"] input {{ color: var(--side-input-text) !important; }}
section[data-testid="stSidebar"] [data-baseweb="tag"],
section[data-testid="stSidebar"] [data-testid="stMultiSelect"] [data-tag] {{ background-color: var(--side-tag-bg) !important; border-radius: 6px; }}
section[data-testid="stSidebar"] [data-testid="stExpander"] {{
    border: 1px solid var(--side-border); border-radius: 10px; background: var(--input-panel-bg);
}}
section[data-testid="stSidebar"] [data-testid="stExpanderDetails"] {{ padding: 6px 4px 8px; }}
section[data-testid="stSidebar"] hr {{ border-color: var(--side-sep); }}

/* ------------------------------------------------------------------ */
/* Theme-proof widget surfaces.                                        */
/* Streamlit builds widgets from the *client* theme. If the app runs    */
/* from a folder without .streamlit/config.toml and the OS uses dark    */
/* mode, those fields render near-black while the shell stays light     */
/* (painted by the CSS above). These rules pin every field to the light */
/* palette so the UI looks the same on every machine.                   */
/* ------------------------------------------------------------------ */
[data-testid="stFileUploaderDropzone"] {{
    background: var(--field-bg) !important;
    border: 1px dashed var(--field-border) !important;
    color: var(--field-text) !important;
}}
[data-testid="stFileUploaderDropzone"]:hover {{ border-color: var(--primary) !important; }}
[data-testid="stFileUploaderDropzoneInstructions"] span,
[data-testid="stFileUploaderDropzoneInstructions"] div {{ color: var(--muted) !important; }}
[data-testid="stFileUploaderDropzone"] button {{
    background: var(--card) !important;
    color: var(--field-text) !important;
    border: 1px solid var(--field-border) !important;
}}
[data-testid="stFileUploaderDropzone"] button:hover {{
    border-color: var(--primary) !important; color: var(--primary) !important;
}}
[data-testid="stFileUploaderDropzone"] button * {{ color: inherit !important; }}

/* Multiselect / selectbox / date input. Streamlit >= 1.6x uses react-aria
   markup, so the old [data-baseweb="select"] hooks no longer match. */
[data-testid="stMultiSelect"] [role="group"][data-rac],
[data-testid="stSelectbox"] [role="group"][data-rac],
[data-testid="stDateInput"] [role="group"][data-rac] {{
    background: var(--field-bg) !important;
    border: 1px solid var(--field-border) !important;
    color: var(--field-text) !important;
    border-radius: 9px !important;
}}
[data-testid="stMultiSelect"] input,
[data-testid="stSelectbox"] input,
[data-testid="stDateInput"] input {{ color: var(--field-text) !important; }}
[data-testid="stMultiSelect"] [data-tag] {{
    background: var(--tag-bg) !important;
    color: var(--tag-text) !important;
    border-radius: 6px !important;
}}
[data-testid="stMultiSelect"] [data-tag] span,
[data-testid="stMultiSelect"] [data-tag] button {{ color: var(--tag-text) !important; }}

/* Unselected radios inherit the dark surface color as a filled circle */
[data-testid="stRadioOption"]:not([data-selected="true"]) > div > div {{
    background: var(--card) !important;
    border-color: var(--field-border) !important;
}}

/* Dropdown menus are portalled outside the sidebar/main containers */
[role="listbox"],
div[data-baseweb="popover"] > div {{
    background: var(--card) !important;
    color: var(--field-text) !important;
}}
[role="option"] {{ color: var(--field-text) !important; }}
[role="option"][aria-selected="true"],
[role="option"][data-selected="true"] {{
    background: var(--side-focus-bg) !important;
    color: var(--side-strong) !important;
}}


.badge {{
    display: inline-flex; align-items: center; gap: 8px;
    background: var(--badge-bg); color: var(--badge-color); border: 1px solid var(--badge-border);
    padding: 8px 14px; border-radius: 999px; font-size: .8rem; font-weight: 600;
}}
[data-testid="stDataFrame"] {{
    border: 1px solid var(--table-border); border-radius: 12px; overflow: hidden;
}}

div[data-baseweb="input"] > div, div[data-baseweb="textarea"] > div {{ border-radius: 9px; border-color: var(--border); }}
.stButton > button, .stDownloadButton > button {{
    border-radius: 9px; border: 1px solid var(--border);
    background: var(--card); color: var(--head); font-weight: 500; padding: .5rem 1rem;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color: var(--primary); color: var(--primary); }}
section[data-testid="stSidebar"] .stButton > button, section[data-testid="stSidebar"] .stDownloadButton > button {{
    background: var(--side-input-bg); color: var(--side-input-text); border-color: var(--side-input-border);
}}
section[data-testid="stSidebar"] .stButton > button:hover {{
    border-color: var(--primary); color: var(--side-strong);
}}

.stTabs [data-baseweb="tab-list"] {{ gap: 18px; border-bottom: 1px solid var(--border); }}
.stTabs [data-baseweb="tab"] {{ font-weight: 600; color: var(--tab-inactive); padding: 8px 2px; }}
.stTabs [aria-selected="true"] {{ color: var(--primary); }}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: var(--primary); }}

.footer {{
    text-align: center; color: var(--muted); font-size: .8rem;
    margin-top: 26px; padding-top: 16px; border-top: 1px solid var(--border);
}}
</style>
"""


def icono(nombre: str, tam: str = "20px", color: str | None = None) -> str:
    estilo = f"font-size:{tam};"
    if color:
        estilo += f" color:{color};"
    return f'<span class="mi" style="{estilo}">{nombre}</span>'


def render_estado_sin_datos(empty_state_title=None, empty_state_desc=None, empty_state_hint=None) -> None:
    """Render the empty state screen. All text can be configured via JSON."""
    title = empty_state_title or "No data to display"
    desc = empty_state_desc or "Upload your data files from the side panel to start analyzing."
    hint = empty_state_hint or ""

    st.markdown(
        '<div style="height:8vh;"></div>',
        unsafe_allow_html=True,
    )
    
    hint_html = ""
    if hint:
        hint_html = f'<span class="badge"><span class="mi">info</span> {hint}</span>'
    
    st.markdown(
        f"""
        <div class="card" style="text-align:center; padding:48px 32px; max-width:680px; margin:0 auto;">
            <div style="font-size:52px; line-height:1; margin-bottom:14px;">
                <span class="mi" style="font-size:52px; color:var(--muted);">upload_file</span>
            </div>
            <div class="card-title" style="font-size:1.3rem; margin-bottom:10px;">{title}</div>
            <div class="page-desc" style="max-width:460px; margin:0 auto 22px; color:var(--body);">
                {desc}
            </div>
            {hint_html}
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="height:8vh;"></div>',
        unsafe_allow_html=True,
    )
