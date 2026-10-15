"""SaaS-dashboard styling for the Streamlit app (inspired by FlourishON): white sidebar with
icon navigation, soft canvas, white rounded cards, KPI tiles with tinted icon badges.

Colours and fonts live in .streamlit/config.toml; this module adds the layout polish that the
theme can't express, plus a few small HTML components. Containers get the card look when
their `key` starts with "card_".
"""
from __future__ import annotations
import html
import streamlit as st

# Inline SVG icons (Lucide-style, 24px grid, stroke = currentColor).
_ICONS = {
    "inbox": '<path d="M22 12h-6l-2 3h-4l-2-3H2"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/>',
    "check": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="m9 11 3 3L22 4"/>',
    "alert": '<circle cx="12" cy="12" r="10"/><path d="M12 8v4"/><path d="M12 16h.01"/>',
    "mail": '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m22 7-10 6L2 7"/>',
    "flask": '<path d="M9 3h6"/><path d="M10 3v6.5L4.6 18.4A1.7 1.7 0 0 0 6 21h12a1.7 1.7 0 0 0 1.4-2.6L14 9.5V3"/><path d="M7.5 15h9"/>',
    "cloud": '<path d="M17.5 19a4.5 4.5 0 1 0-1.4-8.8A6 6 0 0 0 4.5 12a4 4 0 0 0 .5 7z"/>',
    "key": '<circle cx="7.5" cy="15.5" r="4.5"/><path d="m10.7 12.3 9.8-9.8"/><path d="m16 7 3 3"/><path d="m19 4 2 2"/>',
    "spark": '<path d="M12 3l1.9 5.8L20 10l-6.1 1.2L12 17l-1.9-5.8L4 10l6.1-1.2z"/>',
}


def icon(name: str, size: int = 20) -> str:
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">{_ICONS[name]}</svg>')


CSS = """
<style>
/* ── chrome: hide Streamlit's header bar, deploy button and menu ── */
/* Keep the toolbar itself: it holds the button that re-opens a collapsed sidebar. */
[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbarActions"], [data-testid="stAppDeployButton"], [data-testid="stMainMenu"],
[data-testid="stDecoration"], footer { display: none !important; }
[data-testid="stExpandSidebarButton"] { background:#fff; border:1px solid #EAECF0; border-radius:10px;
  box-shadow: 0 1px 2px rgba(16,24,40,.05); color:#344054; }
[data-testid="stExpandSidebarButton"]:hover { background:#F4EBFF; color:#6941C6; }
[data-testid="stMainBlockContainer"] { padding-top: 2.6rem; padding-bottom: 4rem; max-width: 1240px; }

/* ── sidebar ── */
[data-testid="stSidebar"] { border-right: 1px solid #EAECF0; }
[data-testid="stSidebarUserContent"] { padding-top: .5rem; }
.ui-brand { display:flex; align-items:center; gap:12px; margin: 0 0 18px; }
.ui-brand-mark { width:38px; height:38px; border-radius:11px; display:grid; place-items:center; color:#fff;
  background: radial-gradient(circle at 30% 25%, #B692F6, #7F56D9 55%, #53389E); box-shadow: 0 6px 16px rgba(127,86,217,.35); }
.ui-brand-name { font-size: 1.15rem; font-weight: 700; letter-spacing: -.02em; color:#101828; line-height:1.1; }
.ui-brand-sub { font-size: .78rem; color:#667085; }

/* navigation: turn the radio into menu rows */
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has([role="radiogroup"]),
[data-testid="stSidebar"] [data-testid="stRadio"], [data-testid="stSidebar"] [data-testid="stRadio"] > div { width: 100% !important; }
[data-testid="stSidebar"] [role="radiogroup"] { gap: 4px; width: 100%; display: flex; flex-direction: column; }
[data-testid="stSidebar"] [role="radiogroup"] label {
  width: 100%; margin: 0; padding: 9px 12px; border-radius: 10px; cursor: pointer;
  transition: background .15s, color .15s; }
[data-testid="stSidebar"] [role="radiogroup"] label > div:first-child { display: none; }
[data-testid="stSidebar"] [role="radiogroup"] label p { font-size: .95rem; font-weight: 500; color:#344054; }
[data-testid="stSidebar"] [role="radiogroup"] label:hover { background: #F9FAFB; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) { background: #F4EBFF; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p { color: #6941C6; font-weight: 600; }
[data-testid="stSidebar"] [role="radiogroup"] label p span[role="img"] { font-size: 1.35rem; margin-right: 8px;
  vertical-align: -5px !important; color: #667085; }
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p span[role="img"] { color: #7F56D9; }
[data-testid="stSidebar"] [data-testid="stAlert"] > div { border-radius: 12px; }

.ui-user { display:flex; align-items:center; gap:12px; padding: 14px 4px 4px; border-top: 1px solid #EAECF0; margin-top: 8px; }
.ui-avatar { width:40px; height:40px; border-radius:50%; display:grid; place-items:center; font-weight:700; color:#6941C6;
  background:#F4EBFF; position:relative; flex-shrink:0; }
.ui-avatar::after { content:""; position:absolute; right:0; bottom:0; width:10px; height:10px; border-radius:50%;
  background:#12B76A; border:2px solid #fff; }
.ui-user-name { font-weight:600; color:#101828; font-size:.92rem; line-height:1.2; }
.ui-user-meta { color:#667085; font-size:.8rem; }

/* ── page header ── */
.ui-page-head { margin: 0 0 22px; }
.ui-page-title { font-size: 2rem; font-weight: 700; letter-spacing: -.03em; color:#101828; margin:0; line-height:1.15; }
.ui-page-sub { color:#667085; margin-top: 6px; font-size: .98rem; }

/* ── KPI tiles ── */
.ui-kpis { display:grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 18px; margin: 4px 0 22px; }
.ui-kpi { background:#fff; border:1px solid #EAECF0; border-radius:16px; padding: 20px 22px;
  box-shadow: 0 1px 2px rgba(16,24,40,.05); display:flex; gap:16px; align-items:flex-start; }
.ui-kpi-icon { width:46px; height:46px; border-radius:50%; display:grid; place-items:center; flex-shrink:0;
  background:#F4EBFF; color:#7F56D9; }
.ui-kpi-icon.green { background:#ECFDF3; color:#12B76A; }
.ui-kpi-icon.amber { background:#FFFAEB; color:#F79009; }
.ui-kpi-label { color:#475467; font-size:.92rem; font-weight:500; }
.ui-kpi-value { color:#101828; font-size:2rem; font-weight:700; letter-spacing:-.03em; line-height:1.15; margin-top:4px; }

/* ── cards: any container whose key starts with card_ ── */
[class*="st-key-card_"] { background:#fff; border-radius:16px !important; border-color:#EAECF0 !important;
  box-shadow: 0 1px 2px rgba(16,24,40,.05); transition: box-shadow .2s, border-color .2s; }
[class*="st-key-card_inbox"]:hover { border-color:#D6BBFB !important; box-shadow: 0 8px 24px rgba(16,24,40,.08); }

/* expanders, uploader, alerts and tabs as soft white cards */
[data-testid="stExpander"] details { background:#fff; border-radius:14px; border-color:#EAECF0; }
[data-testid="stExpander"] summary p { font-weight: 600; }
[data-testid="stFileUploaderDropzone"] { background:#fff; border:1px dashed #D0D5DD; border-radius:14px; }
[data-testid="stMain"] [data-testid="stAlert"] > div { border-radius: 12px; }
[data-testid="stTabs"] [role="tablist"] { gap: 6px; }
.msg { background:#fff; border-color:#EAECF0 !important; border-radius:14px !important; }

/* buttons */
[data-testid^="stBaseButton"] { font-weight: 600; border-radius: 10px; }
[data-testid="stBaseButton-primary"] { box-shadow: 0 1px 2px rgba(16,24,40,.05); }

/* status pills used in lists */
.ui-pill { display:inline-flex; align-items:center; gap:6px; padding: 2px 10px; border-radius:999px; font-size:.8rem;
  font-weight:600; border:1px solid transparent; white-space:nowrap; }
.ui-pill.purple { background:#F4EBFF; color:#6941C6; border-color:#E9D7FE; }
.ui-pill.green { background:#ECFDF3; color:#027A48; border-color:#ABEFC6; }
.ui-pill.red { background:#FEF3F2; color:#B42318; border-color:#FECDCA; }
.ui-pill.amber { background:#FFFAEB; color:#B54708; border-color:#FEDF89; }
.ui-pill.grey { background:#F2F4F7; color:#344054; border-color:#EAECF0; }

/* AI mode: sidebar status + option cards */
.ui-mode { display:flex; gap:12px; align-items:center; padding:12px; border-radius:14px; border:1px solid #EAECF0; background:#fff; }
.ui-mode .ui-kpi-icon { width:38px; height:38px; }
.ui-mode-title { font-weight:600; color:#101828; font-size:.9rem; line-height:1.2; }
.ui-mode-sub { color:#667085; font-size:.78rem; margin-top:2px; }
.ui-mode.warn { border-color:#FEDF89; background:#FFFCF5; }
.ui-option { display:flex; flex-direction:column; gap:12px; }
.ui-option-head { display:flex; gap:14px; align-items:center; }
.ui-option-title { font-size:1.15rem; font-weight:700; color:#101828; letter-spacing:-.01em; }
.ui-option ul { margin:0; padding-left:1.1rem; color:#475467; font-size:.92rem; line-height:1.6; }
[class*="st-key-card_mode_"].is-active, .st-key-card_mode_active { border-color:#7F56D9 !important;
  box-shadow: 0 0 0 3px #F4EBFF, 0 1px 2px rgba(16,24,40,.05); }
.ui-step { display:flex; gap:14px; align-items:flex-start; margin: 4px 0 2px; }
.ui-step-num { width:30px; height:30px; border-radius:50%; background:#F4EBFF; color:#6941C6; font-weight:700;
  display:grid; place-items:center; flex-shrink:0; font-size:.9rem; }
.ui-step-title { font-weight:600; color:#101828; }
.ui-step-text { color:#475467; font-size:.92rem; line-height:1.55; }

/* public demo banner */
.ui-demo { display:flex; gap:12px; align-items:center; padding:12px 16px; margin: 0 0 18px; border-radius:14px;
  border:1px solid #FEDF89; background:#FFFCF5; color:#344054; font-size:.92rem; line-height:1.45; }
.ui-demo .ui-kpi-icon { width:36px; height:36px; }
.ui-demo b { color:#101828; }
.ui-demo a { color:#6941C6; font-weight:600; }

/* sign-in screen */
.ui-auth { text-align:center; margin: 6vh 0 18px; }
.ui-auth .ui-brand { justify-content:center; }
.ui-auth-title { font-size: 1.9rem; font-weight:700; letter-spacing:-.03em; color:#101828; margin: 18px 0 6px; }
.ui-auth-sub { color:#667085; }
[data-testid="stForm"] { background:#fff; border-radius:16px; border-color:#EAECF0; padding: 22px 22px 18px;
  box-shadow: 0 12px 32px rgba(16,24,40,.08); }
</style>
"""


def inject_css() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def brand(subtitle: str = "Grant eligibility") -> None:
    st.markdown(
        f'<div class="ui-brand"><div class="ui-brand-mark">{icon("spark", 20)}</div>'
        f'<div><div class="ui-brand-name">Grant Inbox</div><div class="ui-brand-sub">{html.escape(subtitle)}</div></div></div>',
        unsafe_allow_html=True)


def page_header(title: str, subtitle: str = "") -> None:
    sub = f'<div class="ui-page-sub">{html.escape(subtitle)}</div>' if subtitle else ""
    st.markdown(f'<div class="ui-page-head"><h1 class="ui-page-title">{html.escape(title)}</h1>{sub}</div>',
                unsafe_allow_html=True)


def auth_header(title: str, subtitle: str) -> None:
    st.markdown(
        f'<div class="ui-auth"><div class="ui-brand"><div class="ui-brand-mark">{icon("spark", 20)}</div>'
        f'<div style="text-align:left"><div class="ui-brand-name">Grant Inbox</div>'
        f'<div class="ui-brand-sub">Grant eligibility</div></div></div>'
        f'<div class="ui-auth-title">{html.escape(title)}</div><div class="ui-auth-sub">{html.escape(subtitle)}</div></div>',
        unsafe_allow_html=True)


def kpi_cards(items: list[tuple[str, str, object, str]]) -> None:
    """items: (icon name, label, value, tone) where tone is "", "green" or "amber"."""
    tiles = "".join(
        f'<div class="ui-kpi"><div class="ui-kpi-icon {tone}">{icon(ic)}</div>'
        f'<div><div class="ui-kpi-label">{html.escape(label)}</div><div class="ui-kpi-value">{html.escape(str(value))}</div></div></div>'
        for ic, label, value, tone in items)
    st.markdown(f'<div class="ui-kpis">{tiles}</div>', unsafe_allow_html=True)


def user_card(name: str, meta: str) -> None:
    initials = "".join(p[0] for p in name.split()[:2]).upper() or "?"
    st.markdown(
        f'<div class="ui-user"><div class="ui-avatar">{html.escape(initials)}</div>'
        f'<div><div class="ui-user-name">{html.escape(name)}</div><div class="ui-user-meta">{html.escape(meta)}</div></div></div>',
        unsafe_allow_html=True)


def pill(text: str, tone: str = "grey") -> str:
    return f'<span class="ui-pill {tone}">{html.escape(text)}</span>'


def mode_status(mode: str, has_key: bool) -> None:
    """Compact card in the sidebar showing which reviewer is active."""
    if mode == "offline":
        ic, tone, title, sub, cls = "flask", "amber", "Offline mode", "Free keyword checker · no API", ""
    elif has_key:
        ic, tone, title, sub, cls = "cloud", "green", "Online mode", "Claude reviews applications", ""
    else:
        ic, tone, title, sub, cls = "key", "amber", "Online · key needed", "Add an API key to use Claude", "warn"
    st.markdown(
        f'<div class="ui-mode {cls}"><div class="ui-kpi-icon {tone}">{icon(ic, 18)}</div>'
        f'<div><div class="ui-mode-title">{title}</div><div class="ui-mode-sub">{sub}</div></div></div>',
        unsafe_allow_html=True)


def mode_option(ic: str, tone: str, title: str, tag: str, bullets: list[str]) -> None:
    items = "".join(f"<li>{b}</li>" for b in bullets)
    st.markdown(
        f'<div class="ui-option"><div class="ui-option-head"><div class="ui-kpi-icon {tone}">{icon(ic)}</div>'
        f'<div><div class="ui-option-title">{html.escape(title)}</div>{pill(tag, tone or "purple")}</div></div>'
        f'<ul>{items}</ul></div>', unsafe_allow_html=True)


def step(n: int, title: str, text: str) -> None:
    st.markdown(f'<div class="ui-step"><div class="ui-step-num">{n}</div><div><div class="ui-step-title">'
                f'{html.escape(title)}</div><div class="ui-step-text">{text}</div></div></div>', unsafe_allow_html=True)


def demo_banner(text: str, repo_url: str) -> None:
    """Public demo notice at the top of every page."""
    st.markdown(
        f'<div class="ui-demo" role="note"><div class="ui-kpi-icon amber">{icon("flask", 18)}</div>'
        f'<div><b>{html.escape(text)}</b><br><span>Decisions stay in this browser tab only and disappear when you '
        f'close it. <a href="{html.escape(repo_url)}" target="_blank" rel="noopener">View the code on GitHub ↗</a>'
        f'</span></div></div>', unsafe_allow_html=True)
