"""Styles, icon fonts and presentation helpers (light theme CSS)."""
import streamlit as st

# Material Icons loaded via Google Fonts CDN (no local font file needed).
MATERIAL_ICONS_LINK = (
    '<link href="https://fonts.googleapis.com/icon?family=Material+Icons" '
    'rel="stylesheet">'
)


def chart_colors(primary_color: str = "#2563eb") -> dict:
    """Return chart color defaults derived from the primary color."""
    return {
        "paper": "#ffffff",
        "plot": "#ffffff",
        "grid": "#e2e8f0",
        "font": "#334155",
        "line": "#cbd5e1",
        "primary": primary_color,
    }


def apply_styles(primary_color: str | None = None) -> None:
    """Apply base CSS and optionally override the primary color.

    Args:
        primary_color: Hex color (e.g. "#e3000b") to use as the dashboard
            primary color. When provided, CSS custom properties are overridden
            so buttons, links, accents, and focus states all match.
    """
    # Inject Material Icons CDN link tag in the document head
    st.markdown(MATERIAL_ICONS_LINK, unsafe_allow_html=True)
    # Inject CSS rules — st.markdown with unsafe_allow_html=True injects
    # raw CSS rules into the page <head> in Streamlit when wrapped in <style>.
    # The key is to NOT include any text content outside the <style> tag.
    css = _css_body()
    if primary_color:
        css += _primary_color_override(primary_color)
    st.markdown(f"<style>{css}</style>", unsafe_allow_html=True)


def _primary_color_override(hex_color: str) -> str:
    """Generate CSS that overrides --primary and derived variables.

    Derives a light tint (10% opacity) for chip backgrounds and focus states.
    """
    safe = hex_color.lstrip("#")
    if len(safe) == 3:
        safe = safe[0]*2 + safe[1]*2 + safe[2]*2
    tint = f"{hex_color}1a"  # ~10% opacity hex
    return f"""
:root {{
    --primary: {hex_color} !important;
    --chip-bg: {tint};
    --side-focus-bg: {tint};
    --side-focus-border: {hex_color};
}}
a, .stButton > button {{ color: {hex_color} !important; }}
.stButton > button:hover {{ background-color: {tint} !important; }}
"""


PALETTE = [
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


def _hex_to_hsl(hex_color: str) -> tuple:
    """Convert hex color to (H, S, L) values."""
    safe = hex_color.lstrip("#")
    if len(safe) == 3:
        safe = safe[0]*2 + safe[1]*2 + safe[2]*2
    r, g, b = int(safe[0:2], 16)/255, int(safe[2:4], 16)/255, int(safe[4:6], 16)/255
    c_max, c_min = max(r, g, b), min(r, g, b)
    l = (c_max + c_min) / 2
    if c_max == c_min:
        h, s = 0, 0
    else:
        d = c_max - c_min
        s = d / (2 - c_max - c_min) if l > 0.5 else d / (c_max + c_min)
        if c_max == r:
            h = ((g - b) / d) % 6
        elif c_max == g:
            h = (b - r) / d + 2
        else:
            h = (r - g) / d + 4
        h *= 60
        if h < 0:
            h += 360
    return h, s, l


def _hsl_to_hex(h: float, s: float, l: float) -> str:
    """Convert HSL to hex color."""
    if s == 0:
        r = g = b = l
    else:
        def hue2rgb(p, q, t):
            if t < 0: t += 1
            if t > 1: t -= 1
            if t < 1/6: return p + (q - p) * 6 * t
            if t < 1/2: return q
            if t < 2/3: return p + (q - p) * (2/3 - t) * 6
            return p
        q = l * (1 + s) if l < 0.5 else l + s - l * s
        p = 2 * l - q
        h_norm = h / 360
        r = hue2rgb(p, q, h_norm + 1/3)
        g = hue2rgb(p, q, h_norm)
        b = hue2rgb(p, q, h_norm - 1/3)
    return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"


def derive_palette(primary_color: str) -> list:
    """Derive a 10-color palette from a primary color using hue rotation.

    Returns a list of hex colors that share the same saturation/lightness
    as the primary, rotated around the color wheel for variety.
    """
    h, s, l = _hex_to_hsl(primary_color)
    # Rotate hue to get complementary and analogous colors
    rotations = [0, 30, 60, 120, 180, 210, 240, 270, 300, 330]
    return [_hsl_to_hex((h + r) % 360, s, l) for r in rotations]


def _css_body() -> str:
    return """
:root {
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
}

html, body, [class*="css"] { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; }
.stApp { background-color: var(--bg); color: var(--head); }
div.block-container { padding-top: 1.6rem; padding-bottom: 2.5rem; max-width: 100%; padding-left: 24px; padding-right: 24px; }
@media (min-width: 1400px) { div.block-container { max-width: 1400px; margin: 0 auto; } }

[data-testid="stHeader"] { background: var(--bg); }
[data-testid="stToolbar"] { background: var(--bg); }
[data-testid="stToolbar"] [data-testid="stElementToolbar"] button,
[data-testid="stToolbar"] [data-testid="stBaseButton-header"],
[data-testid="stToolbar"] button {
    color: var(--toolbar) !important;
}
[data-testid="stToolbar"] [data-testid="stElementToolbar"] button:hover,
[data-testid="stToolbar"] button:hover { color: var(--primary) !important; }
[data-testid="stStatusWidget"] { color: var(--toolbar) !important; }

.card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px 22px;
    box-shadow: var(--shadow);
    margin-bottom: 18px;
}
.card-head { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.card-body { }

/* Plotly charts: white background is set directly in components.py via paper_bgcolor/plot_bgcolor.
   No extra CSS wrapper needed — let Plotly render cleanly inside the card. */
.card-title { font-size: 1.05rem; font-weight: 700; color: var(--head); letter-spacing: -.01em; }
.card-sub { font-size: .85rem; color: var(--muted); margin-top: 2px; }
.mi {
    font-family: "Material Icons";
    font-weight: normal; font-style: normal;
    line-height: 1; letter-spacing: normal; text-transform: none;
    display: inline-block; white-space: nowrap; word-wrap: normal;
    direction: ltr; font-feature-settings: "liga"; -webkit-font-feature-settings: "liga";
    vertical-align: middle; font-size: 20px; user-select: none;
}
.chip-ic {
    width: 34px; height: 34px; border-radius: 9px; flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    background: var(--chip-bg); color: var(--primary); font-size: 18px;
}

.kpi-row {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
    margin-bottom: 18px;
}
.kpi {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 18px 20px;
    box-shadow: var(--shadow);
    height: 100%;
    flex: 1 1 200px;
    min-width: 180px;
    display: flex;
    flex-direction: column;
}
.kpi-top { display: flex; align-items: center; gap: 14px; }
.kpi-ic {
    width: 40px; height: 40px; border-radius: 10px; flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    background: color-mix(in srgb, var(--acc) 12%, transparent);
    color: var(--acc); font-size: 22px;
}
.kpi-label { font-size: .8rem; font-weight: 700; color: var(--muted); text-transform: uppercase; letter-spacing: .07em; }
.kpi-value { font-size: 1.8rem; font-weight: 800; color: var(--head); margin-top: 12px; letter-spacing: -.02em; }
.kpi-sub { font-size: .85rem; color: var(--green); margin-top: 5px; font-weight: 500; }
.kpi-sub.neg { color: #ef4444; }

.page-title { display: flex; align-items: center; gap: 14px; margin-bottom: 4px; }
.page-title .pt-ic {
    width: 46px; height: 46px; border-radius: 12px; flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, var(--primary), color-mix(in srgb, var(--primary) 60%, white)); color: #fff; font-size: 24px;
    box-shadow: 0 4px 12px color-mix(in srgb, var(--primary) 20%, transparent);
}
.page-title h1 { font-size: 1.6rem; font-weight: 800; color: var(--head); margin: 0; letter-spacing: -.02em; }
.breadcrumb { color: var(--muted); font-size: .82rem; letter-spacing: .05em; margin-bottom: 4px; }
.page-desc { color: var(--body); font-size: .95rem; margin-bottom: 6px; }

section[data-testid="stSidebar"] { background-color: var(--side-bg); border-right: 1px solid var(--side-border); }
section[data-testid="stSidebar"] * { color: var(--side-text); }
section[data-testid="stSidebar"] .stMarkdown p { margin-bottom: 0; }
.brand { display: flex; align-items: center; gap: 12px; padding: 8px 2px 6px; }
.brand-ic {
    width: 38px; height: 38px; border-radius: 10px; flex: 0 0 auto;
    display: inline-flex; align-items: center; justify-content: center;
    background: linear-gradient(135deg, var(--primary), color-mix(in srgb, var(--primary) 70%, white)); color: #fff; font-size: 22px;
    box-shadow: 0 4px 10px color-mix(in srgb, var(--primary) 25%, transparent);
}
.brand-logo-img {
    width: 38px; height: 38px; border-radius: 10px; flex: 0 0 auto;
    object-fit: contain;
}
.brand-name { font-size: 1rem; font-weight: 800; color: var(--side-strong); letter-spacing: -.01em; }
.brand-sub { font-size: .8rem; color: var(--side-muted); }
.side-sep { height: 1px; background: var(--side-sep); margin: 14px 0; }
.side-label { color: var(--side-muted); font-size: .78rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; margin-bottom: 8px; }

section[data-testid="stSidebar"] [role="radiogroup"] { gap: 2px; }
section[data-testid="stSidebar"] [role="radiogroup"] label {
    display: flex; align-items: center; gap: 10px;
    padding: 9px 12px; margin: 1px 0; border-radius: 9px;
    color: var(--nav-color); font-size: .95rem; font-weight: 500;
    cursor: pointer; transition: background .15s ease, color .15s ease;
}
section[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: var(--nav-hover); color: var(--nav-hover-color); }
section[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background: var(--side-focus-bg); color: var(--side-strong);
    box-shadow: inset 0 0 0 1px var(--side-focus-border);
}
section[data-testid="stSidebar"] [role="radiogroup"] input { accent-color: var(--primary); }

section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    color: var(--side-muted); font-size: .78rem; font-weight: 700; letter-spacing: .1em; text-transform: uppercase;
}
section[data-testid="stSidebar"] [data-baseweb="select"] > div,
section[data-testid="stSidebar"] [data-testid="stMultiSelect"] [role="group"][data-rac],
section[data-testid="stSidebar"] [data-testid="stSelectbox"] [role="group"][data-rac] {
    background: var(--side-input-bg); border-color: var(--side-input-border) !important; border-radius: 9px;
}
section[data-testid="stSidebar"] [data-baseweb="select"] span,
section[data-testid="stSidebar"] [data-baseweb="select"] input,
section[data-testid="stSidebar"] [data-testid="stMultiSelect"] input,
section[data-testid="stSidebar"] [data-testid="stSelectbox"] input { color: var(--side-input-text) !important; }
section[data-testid="stSidebar"] [data-baseweb="tag"],
section[data-testid="stSidebar"] [data-testid="stMultiSelect"] [data-tag] { background-color: var(--side-tag-bg) !important; border-radius: 6px; }
section[data-testid="stSidebar"] [data-testid="stExpander"] {
    border: 1px solid var(--side-border); border-radius: 10px; background: var(--input-panel-bg);
}
section[data-testid="stSidebar"] [data-testid="stExpanderDetails"] { padding: 6px 4px 8px; }
section[data-testid="stSidebar"] hr { border-color: var(--side-sep); }

/* ------------------------------------------------------------------ */
/* Theme-proof widget surfaces.                                        */
/* Streamlit builds widgets from the *client* theme. If the app runs    */
/* from a folder without .streamlit/config.toml and the OS uses dark    */
/* mode, those fields render near-black while the shell stays light     */
/* (painted by the CSS above). These rules pin every field to the light */
/* palette so the UI looks the same on every machine.                   */
/* ------------------------------------------------------------------ */
[data-testid="stFileUploaderDropzone"] {
    background: var(--field-bg) !important;
    border: 1px dashed var(--field-border) !important;
    color: var(--field-text) !important;
}
[data-testid="stFileUploaderDropzone"]:hover { border-color: var(--primary) !important; }
[data-testid="stFileUploaderDropzoneInstructions"] span,
[data-testid="stFileUploaderDropzoneInstructions"] div { color: var(--muted) !important; }
[data-testid="stFileUploaderDropzone"] button {
    background: var(--card) !important;
    color: var(--field-text) !important;
    border: 1px solid var(--field-border) !important;
}
[data-testid="stFileUploaderDropzone"] button:hover {
    border-color: var(--primary) !important; color: var(--primary) !important;
}
[data-testid="stFileUploaderDropzone"] button * { color: inherit !important; }

/* Multiselect / selectbox / date input. Streamlit >= 1.6x uses react-aria
   markup, so the old [data-baseweb="select"] hooks no longer match. */
[data-testid="stMultiSelect"] [role="group"][data-rac],
[data-testid="stSelectbox"] [role="group"][data-rac],
[data-testid="stDateInput"] [role="group"][data-rac] {
    background: var(--field-bg) !important;
    border: 1px solid var(--field-border) !important;
    color: var(--field-text) !important;
    border-radius: 9px !important;
}
[data-testid="stMultiSelect"] input,
[data-testid="stSelectbox"] input,
[data-testid="stDateInput"] input { color: var(--field-text) !important; }
[data-testid="stMultiSelect"] [data-tag] {
    background: var(--tag-bg) !important;
    color: var(--tag-text) !important;
    border-radius: 6px !important;
}
[data-testid="stMultiSelect"] [data-tag] span,
[data-testid="stMultiSelect"] [data-tag] button { color: var(--tag-text) !important; }

/* Unselected radios inherit the dark surface color as a filled circle */
[data-testid="stRadioOption"]:not([data-selected="true"]) > div > div {
    background: var(--card) !important;
    border-color: var(--field-border) !important;
}

/* Dropdown menus are portalled outside the sidebar/main containers */
[role="listbox"],
div[data-baseweb="popover"] > div {
    background: var(--card) !important;
    color: var(--field-text) !important;
}
[role="option"] { color: var(--field-text) !important; }
[role="option"][aria-selected="true"],
[role="option"][data-selected="true"] {
    background: var(--side-focus-bg) !important;
    color: var(--side-strong) !important;
}


.badge {
    display: inline-flex; align-items: center; gap: 8px;
    background: var(--badge-bg); color: var(--badge-color); border: 1px solid var(--badge-border);
    padding: 8px 14px; border-radius: 999px; font-size: .8rem; font-weight: 600;
}
[data-testid="stDataFrame"] {
    border: 1px solid var(--table-border); border-radius: 12px; overflow: hidden;
}

div[data-baseweb="input"] > div, div[data-baseweb="textarea"] > div { border-radius: 9px; border-color: var(--border); }
.stButton > button, .stDownloadButton > button {
    border-radius: 9px; border: 1px solid var(--border);
    background: var(--card); color: var(--head); font-weight: 500; padding: .5rem 1rem;
    display: inline-flex; align-items: center; justify-content: center; gap: 6px;
}
.stButton > button:hover, .stDownloadButton > button:hover { border-color: var(--primary); color: var(--primary); }
section[data-testid="stSidebar"] .stButton > button, section[data-testid="stSidebar"] .stDownloadButton > button {
    background: var(--side-input-bg); color: var(--side-input-text); border-color: var(--side-input-border);
}
section[data-testid="stSidebar"] .stButton > button:hover {
    border-color: var(--primary); color: var(--side-strong);
}

/* Material Icons in sidebar buttons: convert icon names to actual icons */
section[data-testid="stSidebar"] .stButton > button,
section[data-testid="stSidebar"] .stDownloadButton > button {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}

.stTabs [data-baseweb="tab-list"] { gap: 18px; border-bottom: 1px solid var(--border); }
.stTabs [data-baseweb="tab"] { font-weight: 600; color: var(--tab-inactive); padding: 8px 2px; }
.stTabs [aria-selected="true"] { color: var(--primary); }
.stTabs [data-baseweb="tab-highlight"] { background-color: var(--primary); }

.footer {
    text-align: center; color: var(--muted); font-size: .8rem;
    margin-top: 26px; padding-top: 16px; border-top: 1px solid var(--border);
}

/* ------------------------------------------------------------------ */
/* Responsive design — adapt to smaller screens                        */
/* ------------------------------------------------------------------ */

/* Tablet (max-width 1024px) */
@media (max-width: 1024px) {
    div.block-container { padding-left: 16px; padding-right: 16px; }
    .kpi-value { font-size: 1.4rem; }
    .page-title h1 { font-size: 1.3rem; }
}

/* Mobile (max-width 768px) */
@media (max-width: 768px) {
    div.block-container { padding-left: 12px; padding-right: 12px; padding-top: 1rem; }
    
    /* Stack KPI cards vertically */
    .kpi-row { flex-direction: column; gap: 10px; }
    .kpi { flex: none; width: 100%; min-width: 0; }
    
    /* Smaller titles and text */
    .page-title h1 { font-size: 1.2rem; }
    .page-title .pt-ic { width: 38px; height: 38px; font-size: 20px; }
    .kpi-value { font-size: 1.3rem; }
    .kpi-label { font-size: .75rem; }
    .card-title { font-size: .95rem; }
    
    /* Compact cards */
    .card { padding: 14px 16px; }
    .kpi { padding: 14px 16px; }
    
    /* Sidebar adjustments */
    section[data-testid="stSidebar"] { min-width: 220px !important; width: 280px !important; }
    
    /* Brand adjustments */
    .brand-ic { width: 32px; height: 32px; font-size: 18px; }
    .brand-name { font-size: .9rem; }
    
    /* Make Plotly charts responsive */
    .stPlotlyChart > div { max-width: 100% !important; }
}

/* Small mobile (max-width 480px) */
@media (max-width: 480px) {
    div.block-container { padding-left: 8px; padding-right: 8px; }
    .page-title h1 { font-size: 1.1rem; }
    .kpi-value { font-size: 1.1rem; }
    .card { padding: 12px 14px; border-radius: 8px; }
    .kpi { padding: 12px 14px; }
    .kpi-ic { width: 34px; height: 34px; font-size: 18px; }
    .chip-ic { width: 28px; height: 28px; font-size: 16px; }
    section[data-testid="stSidebar"] { min-width: 180px !important; width: 240px !important; }
}
"""


def icon(name: str, size: str = "20px", color: str | None = None) -> str:
    style = f"font-size:{size};"
    if color:
        style += f" color:{color};"
    return f'<span class="mi" style="{style}">{name}</span>'


def render_empty_state(empty_state_title=None, empty_state_desc=None, empty_state_hint=None) -> None:
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
