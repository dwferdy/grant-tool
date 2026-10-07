"""Officer inbox. Run with:  streamlit run app.py

Flow: application arrives -> AI + code review it -> officer checks only the flagged items -> officer sends the decision.
"""
from __future__ import annotations
import html, re, time
from datetime import datetime
import pandas as pd
import streamlit as st
from engine.loader import load_applications
from engine.models import Verdict, OfficerDecision
from engine.assess import assess, outcome
from engine.ai_checks import api_available, cached_cells, offline_mode, MODEL
from engine.letters import render_letter
from engine import audit, intake, users, rules_admin, ai_settings
from engine.rules_admin import TEMPLATES, REQUIRED_FIELDS
import ui

st.set_page_config(page_title="Grant Inbox", page_icon="📨", layout="wide")
st.markdown("""<style>
.msg {border:1px solid rgba(128,128,128,.25); border-radius:12px; padding:18px 22px; line-height:1.55}
.msg .lbl {font-size:.75rem; text-transform:uppercase; letter-spacing:.05em; opacity:.6; margin-top:14px}
.msg table {width:100%; border-collapse:collapse; margin-top:4px; font-size:.9rem}
.msg td {padding:4px 6px; border-bottom:1px solid rgba(128,128,128,.15)}
.msg td.amt {text-align:right; white-space:nowrap}
mark {background:#ffe08a; color:#111; padding:0 3px; border-radius:3px}
.quote {border-left:3px solid #f0b400; padding:2px 10px; margin:6px 0; font-size:.9rem}
.steps {display:flex; gap:6px; flex-wrap:wrap; margin:4px 0 14px}
.step {padding:4px 12px; border-radius:999px; font-size:.85rem; border:1px solid rgba(128,128,128,.3); opacity:.55}
.step.done {opacity:1; background:rgba(46,160,67,.15); border-color:rgba(46,160,67,.5)}
.step.now {opacity:1; background:rgba(240,180,0,.18); border-color:rgba(240,180,0,.6); font-weight:600}
</style>""", unsafe_allow_html=True)
ui.inject_css()

RB = rules_admin.active_rubric()                  # official rules + active rules added by a super admin
SAMPLES = load_applications()                     # synthetic demo set
APPS = {**SAMPLES, **intake.load_received()}     # + applications received by email
RULES = {r.id: r for r in RB.rules}
SHORT = {"R01": "Applicant type", "R02": "ABN or auspice", "R03": "Group has auspicing body", "R04": "Link to the NT",
         "R05": "No outstanding acquittals", "R06": "Within funding dates", "R07": "Open to all students",
         "R08": "Not started before approval", "R09": "Wellbeing focus", "R10": "Meets grant objectives",
         "R11": "Application complete", "R12": "Max $10,000", "R13": "Budget adds up", "R14": "Travel ≤ 50%",
         "R15": "Facilitator fees ≤ 50%", "R16": "Catering ≤ 25%", "R17": "No portable assets", "R18": "No profit-making",
         "R19": "No running costs", "R20": "No membership fees", "R21": "No fundraising", "R22": "No alcohol",
         "R23": "Nothing illegal", "R24": "No application prep costs", "R25": "Not political", "R26": "Not discriminatory"}
ICON = {Verdict.MET: "✅", Verdict.NOT_MET: "❌", Verdict.INSUFFICIENT_EVIDENCE: "❓",
        Verdict.NEEDS_OFFICER_JUDGEMENT: "👤", Verdict.NOT_APPLICABLE: "➖"}
LABEL = {Verdict.MET: "Met", Verdict.NOT_MET: "Not met", Verdict.INSUFFICIENT_EVIDENCE: "Ask applicant",
         Verdict.NEEDS_OFFICER_JUDGEMENT: "You decide", Verdict.NOT_APPLICABLE: "Not applicable"}
OUTCOME = {"approve": "🟢 Approve", "reject": "🔴 Reject", "clarify": "🟡 Ask to clarify", "officer_decides": "👤 You decide"}
# Outcome as a coloured status pill (inbox list).
OUTCOME_PILL = {"approve": ("Approve", "green"), "reject": ("Reject", "red"), "clarify": ("Ask to clarify", "amber"),
                "officer_decides": ("You decide", "purple")}
OFFICER_CHOICES = [Verdict.MET, Verdict.NOT_MET, Verdict.INSUFFICIENT_EVIDENCE, Verdict.NOT_APPLICABLE]
FLAG_ORDER = [Verdict.NOT_MET, Verdict.INSUFFICIENT_EVIDENCE, Verdict.NEEDS_OFFICER_JUDGEMENT, Verdict.MET, Verdict.NOT_APPLICABLE]

def short(rid: str) -> str:
    return SHORT.get(rid) or RULES[rid].short_name or rid

# ---------- login ----------
def auth_gate() -> dict:
    if st.session_state.get("user"):
        return st.session_state.user
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        if users.count() == 0:
            ui.auth_header("First-time setup", "Create the first super admin account")
            st.write("Create the first **super admin** account. Super admins manage rules and users, and can review too.")
            with st.form("setup"):
                name = st.text_input("Your name")
                username = st.text_input("Username")
                pw = st.text_input(f"Password (at least {users.MIN_PASSWORD} characters)", type="password")
                pw2 = st.text_input("Repeat password", type="password")
                if st.form_submit_button("Create super admin", type="primary"):
                    try:
                        if pw != pw2:
                            raise ValueError("The passwords don't match.")
                        users.create(username, name, "super_admin", pw, created_by="first-time setup")
                        st.session_state.user = users.verify(username, pw)
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
        else:
            ui.auth_header("Welcome back", "Sign in to review grant applications")
            with st.form("login"):
                username = st.text_input("Username")
                pw = st.text_input("Password", type="password")
                if st.form_submit_button("Sign in", type="primary"):
                    user = users.verify(username, pw)
                    if user:
                        st.session_state.user = user
                        st.rerun()
                    st.error("Wrong username or password, or the account is deactivated.")
    st.stop()

USER = auth_gate()
officer = USER["display_name"]
IS_ADMIN = USER["role"] == "super_admin"

# ---------- state ----------
if "cells" not in st.session_state:
    st.session_state.cells = {}
def cells_for(aid: str) -> dict:
    if aid not in st.session_state.cells:
        # Uses cached AI results. Never calls Claude here; the free offline reviewer may re-run (e.g. after a rule change).
        st.session_state.cells[aid] = assess(APPS[aid], RB, call_api=offline_mode() and aid in RECEIVED)
    return st.session_state.cells[aid]

RECEIVED = {a: t for a, t in audit.received().items() if a in APPS}
FINALS, DECISIONS = audit.finals(), audit.latest()

def decisions_for(aid: str) -> dict:
    return {rid: d for (a, rid), d in DECISIONS.items() if a == aid}

def effective(aid: str) -> dict:
    cells, dec = cells_for(aid), decisions_for(aid)
    return {rid: dec[rid].officer_verdict if rid in dec else cells[rid].verdict for rid in RULES}

def to_review(aid: str, blind: bool) -> list[str]:
    """Items the officer must decide one by one. Blind review: every rule."""
    cells = cells_for(aid)
    if blind:
        return list(RULES)
    flagged = [rid for rid, c in cells.items()
               if c.verdict not in (Verdict.MET, Verdict.NOT_APPLICABLE) or RULES[rid].check_method == "officer_judgement"]
    return sorted(flagged, key=lambda r: (FLAG_ORDER.index(cells[r].verdict), r))

def ai_suggestion(aid: str) -> str:
    return outcome(RB, {rid: c.verdict for rid, c in cells_for(aid).items()})

def receive(aid: str) -> None:
    audit.receive(aid)
    if api_available() and cached_cells(APPS[aid], RB) is None:
        with st.spinner(f"AI is reviewing {APPS[aid].applicant.name}…"):
            try:
                st.session_state.cells[aid] = assess(APPS[aid], RB, call_api=True)
            except Exception as e:
                st.error(f"AI review failed for {aid}: {e}. Code checks still ran; AI items go to you.")

def open_app(aid):
    st.query_params["app"] = aid

def close_app():
    st.query_params.clear()

# ---------- sidebar ----------
NAV_INBOX, NAV_AUDIT = ":material/inbox: Inbox", ":material/history: Audit log"
NAV_RULES, NAV_USERS = ":material/rule: Rules", ":material/group: Users"
NAV_AI = ":material/smart_toy: AI mode"

def go_ai_mode():
    st.session_state.nav = NAV_AI

with st.sidebar:
    ui.brand()
    pages = [NAV_INBOX, NAV_AUDIT] + ([NAV_RULES, NAV_USERS, NAV_AI] if IS_ADMIN else [])
    page = st.radio("Go to", pages, label_visibility="collapsed", key="nav")
    st.divider()
    blind = st.toggle("Blind review", help="Hide everything the AI found until you have decided each rule yourself. "
                                           "Use this to check you are not just agreeing with the AI.")
    ui.mode_status(ai_settings.mode(), bool(ai_settings.api_key()))
    if IS_ADMIN and page != NAV_AI:
        st.button(":material/tune: Change AI mode", on_click=go_ai_mode, width="stretch")
    elif not IS_ADMIN:
        st.caption("A super admin can switch between offline and online mode.")
    with st.expander("How it works"):
        st.markdown("1. **📨 An application arrives** in your inbox.\n"
                    f"2. **🤖 The AI and code check it** against all {len(RULES)} rules.\n"
                    "3. **👤 You review** only what was flagged (and the 3 rules a person must always decide).\n"
                    "4. **✉️ You send the decision.** The letter explains each reason in plain English.")
    ui.user_card(officer, f"{users.ROLES[USER['role']]} · @{USER['username']}")
    if st.button(":material/logout: Sign out", width="stretch"):
        st.session_state.clear()
        st.rerun()

# ---------- email ----------
def show_intake(results):
    for r in results:
        if r.application_id and r.problems == ["Already received."]:
            continue
        if r.application_id:
            receive(r.application_id)
            st.toast(f"New application from {r.sender}", icon="📩")
        else:
            st.toast(f"Couldn't read the email from {r.sender}", icon="⚠️")
    new = [r for r in results if r.problems != ["Already received."]]
    if not new:
        st.toast("No new emails.", icon="📭")

def mail_box():
    c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
    configured = intake.mail_configured()
    if c1.button("📬 Check mail", type="primary", width="stretch", disabled=not configured,
                 help=None if configured else "Set MAIL_IMAP_HOST, MAIL_USER and MAIL_PASSWORD in .env"):
        try:
            with st.spinner("Checking the mailbox…"):
                show_intake(intake.check_mailbox())
            st.rerun()
        except Exception as e:
            st.error(f"Could not read the mailbox: {e}")
    up = c2.file_uploader("Or drop an email file (.eml)", type=["eml"], accept_multiple_files=True,
                          key=f"eml_{st.session_state.get('eml_n', 0)}")
    if up:
        show_intake([intake.ingest(f.getvalue()) for f in up])
        st.session_state.eml_n = st.session_state.get("eml_n", 0) + 1   # clear the uploader
        st.rerun()
    if not configured:
        st.caption("📭 Mailbox not connected yet. See **Connect a mailbox** below, or test with the sample "
                   "emails in `data/sample_emails/`.")
    bad = audit.unreadable_mail()
    if bad:
        with st.expander(f"⚠️ {len(bad)} email(s) we couldn't turn into an application — reply to the sender"):
            for i, m in enumerate(bad):
                with st.container(border=True, key=f"card_mail_{i}"):
                    st.markdown(f"**{html.escape(m['sender'])}** · {html.escape(m['subject'])}")
                    st.markdown("\n".join(f"- {p}" for p in m["problems"].splitlines()))
                    st.code(m["body"], language=None)
    with st.expander("📝 Template applicants should use"):
        st.caption("Applicants paste this into the email body. Subject must contain “Grant application”.")
        st.code(intake.TEMPLATE.read_text(), language=None)
    if not configured:
        with st.expander("🔌 Connect a mailbox"):
            st.markdown("""Add these lines to `.env` and restart the app:
```
MAIL_IMAP_HOST=imap.gmail.com
MAIL_USER=you@gmail.com
MAIL_PASSWORD=your-16-character-app-password
MAIL_SUBJECT=Grant application
```
**Gmail:** turn on 2-Step Verification, then create an App Password at
https://myaccount.google.com/apppasswords (your normal password will not work).
The app only *reads* emails whose subject contains `MAIL_SUBJECT`; it never deletes or marks them as read.""")

# ---------- inbox ----------
def inbox():
    ui.page_header("Inbox", f"Good to see you, {officer.split()[0].title()}. Here's what needs your review.")
    waiting = [a for a in RECEIVED if a not in FINALS]
    ui.kpi_cards([
        ("inbox", "Waiting for you", len(waiting), ""),
        ("check", "Decided", len(FINALS), "green"),
        ("mail", "Emails we couldn't read", len(audit.unreadable_mail()), "amber"),
    ])

    if ai_settings.mode() == "online" and not ai_settings.api_key():
        with st.container(border=True, key="card_needkey"):
            a, b = st.columns([4, 1.3], vertical_alignment="center")
            a.markdown("**Online mode is on, but Claude isn't connected yet.**  \n"
                       "<small>Add an Anthropic API key to let Claude check applications. Until then, "
                       "the rules that need AI come to you.</small>", unsafe_allow_html=True)
            if IS_ADMIN:
                b.button("Connect Claude", type="primary", on_click=go_ai_mode, width="stretch")
    mail_box()
    if api_available() and not offline_mode():
        stale = [a for a in RECEIVED if a not in FINALS and cached_cells(APPS[a], RB) is None]
        if stale:
            st.warning(f"{len(stale)} open application(s) haven't been checked by the AI against the current rules "
                       "(new arrivals while AI was off, or the rules changed). Their AI items are waiting for you.")
            if st.button(f"🤖 Re-check {len(stale)} with AI (uses API credits)"):
                for a in stale:
                    st.session_state.cells.pop(a, None)
                    receive(a)
                st.rerun()
    not_arrived = [a for a in SAMPLES if a not in RECEIVED]
    with st.expander("🧪 Demo: sample applications (no email needed)"):
        b1, b2, b3 = st.columns([2, 2, 1])
        if b1.button("📩 Simulate one arriving", disabled=not not_arrived, width="stretch"):
            receive(not_arrived[0])
            st.rerun()
        if b2.button(f"📥 Receive all samples ({len(not_arrived)})", disabled=not not_arrived, width="stretch"):
            for a in not_arrived:
                receive(a)
            st.rerun()
        if b3.button("↺ Reset", help="Empty the inbox, delete all decisions and received emails (demo only)", width="stretch"):
            audit.reset_demo()
            st.session_state.cells = {}
            st.rerun()

    if not RECEIVED:
        st.info("Your inbox is empty. Click **Check mail**, upload an email, or open the demo section above.")
        return

    show = st.radio("Show", ["Waiting for you", "Decided", "All"], horizontal=True, label_visibility="collapsed")
    ids = {"Waiting for you": waiting, "Decided": [a for a in RECEIVED if a in FINALS]}.get(show, list(RECEIVED))
    if not ids:
        st.success("Nothing here. 🎉" if show == "Waiting for you" else "Nothing here yet.")
    for aid in ids:
        app, cells = APPS[aid], cells_for(aid)
        with st.container(border=True, key=f"card_inbox_{aid}"):
            left, mid, right = st.columns([6, 2, 1.3], vertical_alignment="center")
            unread = "🔵 " if aid not in FINALS and not decisions_for(aid) else ""
            left.markdown(f"{unread}**{html.escape(app.applicant.name)}**  ·  <small>{RECEIVED[aid]:%d %b %H:%M} · {aid}</small>",
                          unsafe_allow_html=True)
            left.markdown(f"{app.project.title} — ${app.total_requested:,.0f}")
            if aid in FINALS:
                mid.markdown(f"<small style='color:#667085'>Sent</small><br>{ui.pill(*OUTCOME_PILL[FINALS[aid]['outcome']])}",
                             unsafe_allow_html=True)
                left.caption(f"Decided by {FINALS[aid]['officer']}")
            elif blind:
                mid.markdown(ui.pill("Blind review", "grey"), unsafe_allow_html=True)
            else:
                mid.markdown(f"<small style='color:#667085'>AI suggests</small><br>{ui.pill(*OUTCOME_PILL[ai_suggestion(aid)])}",
                             unsafe_allow_html=True)
                issues = [r for r in to_review(aid, False) if cells[r].verdict in (Verdict.NOT_MET, Verdict.INSUFFICIENT_EVIDENCE)]
                left.caption("Flagged: " + ", ".join(f"{ICON[cells[r].verdict]} {short(r)}" for r in issues)
                             if issues else "No problems found by the checks.")
            right.button("Open →" if aid not in FINALS else "View", key=f"open_{aid}", on_click=open_app, args=(aid,),
                         width="stretch", type="primary" if aid not in FINALS else "secondary")

# ---------- one application ----------
def highlight(text: str, quotes: list[str]) -> str:
    out = html.escape(str(text) if text else "—")
    for q in quotes:
        out = re.sub(re.escape(html.escape(q)), lambda m: f"<mark>{m[0]}</mark>", out, flags=re.I)
    return out

def message_html(aid: str, show_quotes: bool) -> str:
    app, a, p = APPS[aid], APPS[aid].applicant, APPS[aid].project
    q = {}
    if show_quotes:
        for c in cells_for(aid).values():
            for quote in c.applicant_quotes:
                q.setdefault(quote.field, []).append(quote.text)
    h = lambda field, value: highlight(value, q.get(field, []))
    ausp = (f"<div class='lbl'>Auspicing body</div>{h('applicant.auspicing_body.name', a.auspicing_body.name)}"
            f" {'(confirmed)' if a.auspicing_body.confirmed else '(not confirmed)'}") if a.auspicing_body else ""
    budget = "".join(f"<tr><td>{h(f'budget[{i}].item', b.item)}</td><td><small>{b.category.replace('_', ' ')}</small></td>"
                     f"<td class='amt'>${b.amount:,.2f}</td></tr>" for i, b in enumerate(app.budget))
    return f"""<div class='msg'>
<div><b>From:</b> {html.escape(a.name)} <small>({a.type.replace('_', ' ')}{', ' + html.escape(a.contact_role) if a.contact_role else ''})</small></div>
<div><b>ABN:</b> {html.escape(a.abn or '—')} · <b>NT based:</b> {'yes' if a.nt_based else 'no' if a.nt_based is False else '—'}</div>
{ausp}
<div class='lbl'>Project</div><b>{h('project.title', p.title)}</b>
<div>{p.start_date:%d %b %Y} → {p.end_date:%d %b %Y} · {h('project.location', p.location)}</div>
<div class='lbl'>Description</div>{h('project.description', p.description)}
<div class='lbl'>Who can attend</div>{h('project.who_can_attend', p.who_can_attend)}
<div class='lbl'>Wellbeing benefit</div>{h('project.wellbeing_benefit', p.wellbeing_benefit)}
<div class='lbl'>Budget</div><table>{budget}<tr><td><b>Total requested</b></td><td></td><td class='amt'><b>${app.total_requested:,.2f}</b></td></tr></table>
</div>"""

def rule_card(aid: str, rid: str, blind: bool, locked: bool):
    rule, cell = RULES[rid], cells_for(aid)[rid]
    dec = decisions_for(aid).get(rid)
    edit_key = f"edit_{aid}_{rid}"
    st.session_state.setdefault(f"t_{aid}_{rid}", time.time())
    show_ai = not blind or dec is not None

    with st.container(border=True, key=f"card_rule_{aid}_{rid}"):
        top_l, top_r = st.columns([4, 1.4], vertical_alignment="center")
        icon = ICON[dec.officer_verdict] if dec else (ICON[cell.verdict] if show_ai else "▫️")
        top_l.markdown(f"{icon} **{short(rid)}** <small style='opacity:.6'>{rid}</small>", unsafe_allow_html=True)
        if dec:
            top_r.markdown(f"<div style='text-align:right'><small>✔ You: <b>{LABEL[dec.officer_verdict]}</b></small></div>",
                           unsafe_allow_html=True)
        st.caption(rule.rule)
        if show_ai:
            ai_label = "🧪 Keyword checker (test mode)" if offline_mode() else "🤖 AI"
            who = {"code": "🧮 Code", "ai": ai_label, "officer": "👤 Only you can check this"}[cell.checked_by]
            st.markdown(f"**{who}:** {LABEL[cell.verdict] if cell.checked_by != 'officer' else ''}"
                        f"{' — ' if cell.checked_by != 'officer' else ''}{cell.reasoning}")
            if cell.missing:
                st.markdown(f"<small>**What would change this:** {html.escape(cell.missing)}</small>", unsafe_allow_html=True)
            for q in cell.applicant_quotes:
                st.markdown(f"<div class='quote'>“{html.escape(q.text)}”<br><small style='opacity:.6'>{q.field}</small></div>",
                            unsafe_allow_html=True)
        if dec and dec.officer_note:
            st.markdown(f"<small>📝 {html.escape(dec.officer_note)}</small>", unsafe_allow_html=True)

        if locked:
            return
        if dec and not st.session_state.get(edit_key):
            st.button("Change", key=f"chg_{aid}_{rid}", on_click=lambda: st.session_state.update({edit_key: True}))
            return
        with st.form(f"f_{aid}_{rid}", border=False):
            default = dec.officer_verdict if dec else (cell.verdict if show_ai and cell.verdict in OFFICER_CHOICES else None)
            choice = st.radio("Your verdict", OFFICER_CHOICES, horizontal=True, key=f"r_{aid}_{rid}",
                              index=OFFICER_CHOICES.index(default) if default else None,
                              format_func=lambda v: f"{ICON[v]} {LABEL[v]}")
            note = st.text_input("Note (required for Not met)", value=(dec.officer_note or "") if dec else "",
                                 key=f"n_{aid}_{rid}", placeholder="In your own words")
            if st.form_submit_button("Save", type="primary"):
                if not officer.strip():
                    st.error("Type your name in the sidebar first.")
                elif choice is None:
                    st.error("Pick a verdict.")
                elif choice == Verdict.NOT_MET and not note.strip():
                    st.error("Write a short reason for Not met. The applicant will see it.")
                else:
                    audit.record(OfficerDecision(
                        application_id=aid, rule_id=rid, ai_verdict=cell.verdict, officer_verdict=choice,
                        overridden=choice != cell.verdict, blind_review=blind, officer_note=note.strip() or None,
                        officer=officer.strip(), decided_at=datetime.now(),
                        seconds_spent=round(time.time() - st.session_state.pop(f"t_{aid}_{rid}", time.time()), 1)))
                    st.session_state[edit_key] = False
                    st.rerun()

def steps(done: int):
    names = ["📩 Received", "🤖 Checked", "👤 Your review", "✉️ Decision sent"]
    st.markdown("<div class='steps'>" + "".join(
        f"<span class='step {'done' if i < done else 'now' if i == done else ''}'>{n}</span>" for i, n in enumerate(names))
        + "</div>", unsafe_allow_html=True)

def detail(aid: str):
    app, cells = APPS[aid], cells_for(aid)
    final = FINALS.get(aid)
    review = to_review(aid, blind)
    pending = [r for r in review if r not in decisions_for(aid)]

    st.button("← Back to inbox", on_click=close_app)
    st.markdown(f"## {html.escape(app.project.title)}")
    st.caption(f"From **{app.applicant.name}** · received {RECEIVED[aid]:%d %b %Y %H:%M} · {aid}"
               + (f" · synthetic test case: {app.test_purpose}" if aid in SAMPLES else f" · {app.test_purpose}"))
    steps(4 if final else 3 if not pending else 2)

    left, right = st.columns([1, 1.15], gap="large")
    with left:
        st.markdown("#### 📩 The application")
        original = intake.original_email(aid)
        if original:
            t1, t2 = st.tabs(["As read by the system", "Original email"])
            t1.markdown(message_html(aid, show_quotes=not blind), unsafe_allow_html=True)
            t2.code(original, language=None)
        else:
            st.markdown(message_html(aid, show_quotes=not blind), unsafe_allow_html=True)
        if not blind:
            st.caption("Highlighted text is what the AI quoted as evidence. Every quote is checked by code to be real.")

    with right:
        if final:
            st.success(f"Decision sent: **{OUTCOME[final['outcome']]}** by {final['officer']} "
                       f"on {datetime.fromisoformat(final['decided_at']):%d %b %Y %H:%M}")
            st.text_area("Letter sent", final["letter"], height=380, disabled=True)
            with st.expander("Rules you reviewed"):
                for rid in review:
                    rule_card(aid, rid, blind=False, locked=True)
            return

        if blind:
            st.info("🙈 **Blind review is on.** Decide every rule yourself; the AI's view appears after you save each one.")
        else:
            sugg = ai_suggestion(aid)
            st.markdown(f"#### 🤖 Checks suggest: {OUTCOME[sugg]}")
            if not api_available() and cached_cells(app, RB) is None:
                st.caption("AI review is off, so the 13 AI rules are waiting for you. The 10 code rules were checked automatically.")

        done = len(review) - len(pending)
        st.markdown(f"#### 👤 Your review — {done} of {len(review)} done")
        st.progress(done / len(review) if review else 1.0)
        for rid in review:
            rule_card(aid, rid, blind, locked=False)

        passed = [r for r in RULES if r not in review]
        if passed:
            with st.expander(f"✅ {len(passed)} rules passed automatically (open to check or change any)"):
                for rid in passed:
                    rule_card(aid, rid, blind, locked=False)

        st.markdown("#### ✉️ Send the decision")
        if pending:
            st.info(f"Review the {len(pending)} remaining item(s) above, then the decision and letter appear here.")
            return
        verdicts, decided = effective(aid), set(decisions_for(aid))
        based_on = outcome(RB, verdicts, decided)
        st.markdown(f"Based on your review: **{OUTCOME[based_on]}**")
        options = ["approve", "clarify", "reject"]
        choice = st.radio("Decision", options, index=options.index(based_on) if based_on in options else None,
                          horizontal=True, format_func=OUTCOME.get, key=f"final_{aid}")
        why = ""
        if choice and choice != based_on:
            why = st.text_area("You chose a different outcome from your rule review. Explain why (goes in the letter):",
                               key=f"why_{aid}")
        if not choice:
            return
        letter = render_letter(RB, app, choice, cells, verdicts, decisions_for(aid), officer, why.strip() or None)
        letter = st.text_area("Letter to the applicant (you can edit it)", letter, height=360, key=f"letter_{aid}_{choice}")
        if st.button(f"Send decision: {OUTCOME[choice]}", type="primary"):
            if not officer.strip():
                st.error("Type your name in the sidebar first.")
            elif choice != based_on and not why.strip():
                st.error("Explain why you chose a different outcome.")
            else:
                audit.record_final(aid, choice, based_on, why.strip() or None, letter, officer.strip())
                st.toast(f"Decision sent to {app.applicant.name}", icon="✉️")
                close_app()
                st.rerun()

# ---------- audit log ----------
def audit_log():
    ui.page_header("Audit log", "Every decision is stored and never overwritten.")
    st.caption("A changed decision is a new row.")
    finals, rows = audit.all_finals(), audit.all_rows()
    st.subheader("Decisions sent")
    if finals:
        st.dataframe(pd.DataFrame(finals), hide_index=True, width="stretch")
    else:
        st.info("None yet.")
    st.subheader("Rule-by-rule review")
    if rows:
        df = pd.DataFrame(rows)
        st.caption(f"{len(df)} rule decisions · {int(df.overridden.sum())} disagreed with the checks · "
                   f"median {df.seconds_spent.median():.0f}s each")
        st.dataframe(df, hide_index=True, width="stretch")
    else:
        st.info("None yet.")
    if IS_ADMIN:
        st.subheader("Rule changes")
        changes = audit.rule_changes()
        if changes:
            st.dataframe(pd.DataFrame(changes), hide_index=True, width="stretch")
        else:
            st.info("None yet.")

# ---------- super admin: rules ----------
METHODS = {"code": "🧮 Automatic check (numbers or a required field)",
           "ai_evidence": "🤖 AI looks for evidence in the application",
           "officer_judgement": "👤 An officer always decides"}

def rules_page():
    ui.page_header("Grant rules", f"{RB.grant} · round {RB.round.name}")
    custom = rules_admin.load_custom()
    tab_list, tab_add = st.tabs([f"📋 All rules ({len(RULES)} active)", "➕ Add a rule"])

    with tab_list:
        st.markdown("#### Added by super admins")
        if not custom:
            st.info("No rules added yet. Use the **Add a rule** tab.")
        for r in custom:
            with st.container(border=True, key=f"card_custom_{r.id}"):
                a, b = st.columns([5, 1.2], vertical_alignment="center")
                a.markdown(f"{'🟢' if r.active else '⚪️'} **{html.escape(r.short_name or r.id)}** "
                           f"<small style='opacity:.6'>{r.id} · {METHODS[r.check_method]}</small>", unsafe_allow_html=True)
                a.caption(r.rule)
                if b.button("Switch off" if r.active else "Switch on", key=f"tog_{r.id}", width="stretch"):
                    rules_admin.set_active(r.id, not r.active, USER["username"])
                    st.session_state.cells = {}
                    st.toast(f"{r.id} switched {'off' if r.active else 'on'}")
                    st.rerun()
                with st.expander("Details"):
                    st.markdown(f"**Check:** `{r.check}`  \n**Letter text:** {r.plain_english_reason}  \n"
                                f"**Keywords (offline mode):** {', '.join(r.keywords) or '—'}  \n"
                                f"**Added by** {r.added_by} on {r.added_at:%d %b %Y %H:%M}" if r.added_at else "")
        st.markdown("#### Official rules (from the published guidelines, read-only)")
        st.dataframe(pd.DataFrame([{"ID": r.id, "Rule": short(r.id), "Checked by": METHODS[r.check_method].split(" ", 1)[1],
                                    "Source": r.source.section, "Full text": r.rule}
                                   for r in RB.rules if not r.custom]), hide_index=True, width="stretch")

    with tab_add:
        add_rule_form()

def add_rule_form():
    st.markdown("Rules apply to every application that hasn't been decided yet. Decisions already sent don't change.")
    if api_available() and not offline_mode():
        st.warning("With Claude on, adding a rule means open applications need a new AI check (uses API credits). "
                   "You'll get a button for that in the inbox.")
    method = st.radio("How should this rule be checked?", list(METHODS), format_func=METHODS.get, key="new_method")
    name = st.text_input("Short name (shown to officers)", placeholder="e.g. Marketing ≤ 20%", key="new_name")
    params, keywords, rtype, text = None, [], "eligibility_gate", {}

    if method == "code":
        template = st.selectbox("Type of check", list(TEMPLATES), format_func=TEMPLATES.get, key="new_tpl")
        if template == "category_cap":
            c1, c2 = st.columns(2)
            cat = c1.selectbox("Budget category", RB.budget_categories, format_func=lambda c: c.replace("_", " "))
            pct = c2.number_input("Maximum % of the total grant", 1, 100, 20)
            params = {"template": template, "category": cat, "pct": pct / 100}
        elif template == "max_total":
            params = {"template": template, "amount": float(st.number_input("Maximum amount ($)", 100, 100000, 5000, step=500))}
        else:
            params = {"template": template, "field": st.selectbox("Field", list(REQUIRED_FIELDS), format_func=REQUIRED_FIELDS.get)}
        text = rules_admin.code_rule_text(template, params)
        rtype = text["type"]
        rule_text = st.text_area("Rule", text["rule"], key=f"rt_{template}_{params}")
        check = text["check"]
        evidence = "Budget and application fields"
        reason_default = text["plain_english_reason"]
        st.caption(f"Code check: `{check}`")
    else:
        if method == "ai_evidence":
            rtype = st.radio("What kind of rule?", ["exclusion", "eligibility_gate"], horizontal=True,
                             format_func={"exclusion": "🚫 Something we can't fund",
                                          "eligibility_gate": "✔️ Something the applicant must show"}.get)
        else:
            rtype = "assessment_criterion"
        rule_text = st.text_area("Rule (one clear sentence)", placeholder="e.g. Funding cannot be used for gift cards or vouchers.",
                                 key="new_rule_text")
        check = st.text_area("How should it be checked? (instructions for the AI / officer)",
                             placeholder="e.g. Look in the budget items and description for gift cards, vouchers or prepaid cards.",
                             key="new_check")
        evidence = st.text_input("Evidence needed", placeholder="e.g. Budget items", key="new_evidence")
        if method == "ai_evidence":
            kw = st.text_input("Keywords for offline test mode (comma separated, optional)",
                               placeholder="gift card, voucher, prepaid card", key="new_kw")
            keywords = [k for k in kw.split(",")]
        reason_default = rules_admin.default_ai_reason(rule_text or "[rule]", rtype)

    reason = st.text_area("What the applicant reads in the letter", reason_default, key=f"reason_{method}_{rtype}_{hash(reason_default)}",
                          help="{amount}, {limit}, {total_requested}, {evidence}, {item} are filled in automatically.")
    with st.expander("Source (optional)"):
        doc = st.text_input("Document", rules_admin.INTERNAL_SOURCE["document"])
        sec = st.text_input("Section", "")
        url = st.text_input("Link", "")

    if st.button("➕ Add rule", type="primary"):
        if not name.strip() or not rule_text.strip() or not check.strip():
            st.error("Short name, rule and how-to-check are required.")
            return
        r = rules_admin.add_rule(by=USER["username"], short_name=name, rule=rule_text, check_method=method, rtype=rtype,
                                 check=check, evidence_needed=evidence or "Application text", plain_english_reason=reason,
                                 source={"document": doc, "section": sec, "url": url}, params=params, keywords=keywords)
        st.session_state.cells = {}
        st.toast(f"Rule {r.id} added", icon="✅")
        st.rerun()

# ---------- super admin: users ----------
def users_page():
    ui.page_header("Users", "Who can review applications and manage rules.")
    rows = users.list_users()
    for u in rows:
        with st.container(border=True, key=f"card_user_{u['username']}"):
            a, b, c = st.columns([4, 1.4, 1.4], vertical_alignment="center")
            a.markdown(f"{'🟢' if u['active'] else '⚪️'} **{html.escape(u['display_name'])}** · @{u['username']} · "
                       f"{users.ROLES[u['role']]}  \n<small style='opacity:.6'>added by {u['created_by']} "
                       f"on {datetime.fromisoformat(u['created_at']):%d %b %Y}</small>", unsafe_allow_html=True)
            if u["username"] != USER["username"]:
                if b.button("Deactivate" if u["active"] else "Activate", key=f"act_{u['username']}", width="stretch"):
                    try:
                        users.set_active(u["username"], not u["active"])
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
            with c.popover("Reset password", width="stretch"):
                pw = st.text_input("New password", type="password", key=f"pw_{u['username']}")
                if st.button("Save", key=f"pws_{u['username']}"):
                    try:
                        users.set_password(u["username"], pw)
                        st.success("Password changed.")
                    except ValueError as e:
                        st.error(str(e))

    st.markdown("#### ➕ Add a user")
    with st.form("new_user", clear_on_submit=True):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name")
        username = c2.text_input("Username")
        role = c1.selectbox("Role", list(users.ROLES), index=1, format_func=users.ROLES.get)
        pw = c2.text_input(f"Temporary password (≥ {users.MIN_PASSWORD} characters)", type="password")
        if st.form_submit_button("Add user", type="primary"):
            try:
                users.create(username, name, role, pw, created_by=USER["username"])
                st.toast(f"Added {name}", icon="✅")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    st.caption("Grant officers review applications and send decisions. Super admins can also manage rules and users.")

# ---------- AI mode ----------
def ai_mode_page():
    ui.page_header("AI mode", "Choose who checks the rules that need someone to read the application.")
    if flash := st.session_state.pop("ai_flash", None):
        st.success(flash)
    current = ai_settings.mode()
    has_key = bool(ai_settings.api_key())

    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(border=True, key="card_mode_active" if current == "offline" else "card_mode_offline"):
            ui.mode_option("flask", "amber", "Offline", "Free · for practice & demos", [
                "A keyword checker stands in for Claude: <b>no API calls, no cost</b>.",
                "It only spots words on its lists, so reworded answers can slip through.",
                "Use it to learn the workflow or demo the tool.",
            ])
            if current == "offline":
                st.button("✓ In use", disabled=True, width="stretch", key="use_off")
            elif st.button("Switch to offline", width="stretch", key="use_off"):
                ai_settings.set_mode("offline")
                st.session_state.cells = {}
                st.session_state.ai_flash = "Switched to offline mode. The free keyword checker now handles the AI rules."
                st.rerun()
    with right:
        with st.container(border=True, key="card_mode_active" if current == "online" else "card_mode_online"):
            ui.mode_option("cloud", "green", "Online (Claude)", f"Uses API credits · {MODEL}", [
                "Claude <b>reads each application</b> and quotes the evidence for every AI rule.",
                "Catches meaning, not just keywords. Each application is checked twice for consistency.",
                "Results are cached, so the same application is never billed twice.",
            ])
            if current == "online":
                st.button("✓ In use", disabled=True, width="stretch", key="use_on")
            elif st.button("Switch to online", type="primary", width="stretch", key="use_on"):
                ai_settings.set_mode("online")
                st.session_state.cells = {}
                st.session_state.ai_flash = "Switched to online mode." + (
                    "" if has_key else " Connect Claude below to start using it.")
                st.rerun()

    if current == "offline":
        st.caption("Your API key (if any) stays saved. Switch to online any time.")
        return

    st.markdown("### Claude connection")
    if has_key and not st.session_state.get("replace_key"):
        with st.container(border=True, key="card_key_status"):
            a, b, c = st.columns([3, 1.1, 1.1], vertical_alignment="center")
            a.markdown(f"{ui.pill('Connected', 'green')} &nbsp; API key `{ai_settings.key_hint()}`  \n"
                       "<small>Saved on this computer only, in <code>.env</code> (never committed to git).</small>",
                       unsafe_allow_html=True)
            if b.button("Test key", width="stretch"):
                with st.spinner("Checking with Anthropic…"):
                    res = ai_settings.test_api_key(ai_settings.api_key())
                (st.success if res.ok else st.error)(res.message)
            if c.button("Replace key", width="stretch"):
                st.session_state.replace_key = True
                st.rerun()
        if st.button("Remove key from this computer", type="tertiary"):
            ai_settings.remove_api_key()
            st.session_state.ai_flash = "API key removed from this computer."
            st.rerun()
        return

    with st.container(border=True, key="card_key_setup"):
        st.markdown("#### Connect Claude in 3 steps")
        ui.step(1, "Create an API key",
                "Sign in to the Anthropic Console, open <b>API keys</b> and click <b>Create key</b>. "
                "Name it something like “Grant Inbox”, then copy it (it starts with <code>sk-ant-</code>).")
        st.link_button("Open Anthropic Console ↗", ai_settings.CONSOLE_KEYS_URL)
        ui.step(2, "Make sure your account has credits",
                "Online mode is billed per use. Check or add credits under <b>Billing</b>.")
        st.link_button("Open Billing ↗", ai_settings.CONSOLE_BILLING_URL)
        ui.step(3, "Paste the key and test it",
                "We send one tiny test request (well under $0.001) before saving. The key is stored only on this "
                "computer, in <code>.env</code>.")
        key = st.text_input("Anthropic API key", type="password", placeholder="sk-ant-…", label_visibility="collapsed")
        a, b = st.columns([1.4, 3])
        if a.button("Test & save key", type="primary", disabled=not key.strip(), width="stretch"):
            with st.spinner("Checking with Anthropic…"):
                res = ai_settings.test_api_key(key)
            if res.ok:
                ai_settings.save_api_key(key.strip())
                st.session_state.replace_key = False
                st.session_state.cells = {}
                st.session_state.ai_flash = res.message
                st.rerun()
            else:
                st.error(res.message)
        if has_key and b.button("Cancel"):
            st.session_state.replace_key = False
            st.rerun()

# ---------- router ----------
if page == NAV_AI and IS_ADMIN:
    ai_mode_page()
elif page == NAV_AUDIT:
    audit_log()
elif page == NAV_RULES and IS_ADMIN:
    rules_page()
elif page == NAV_USERS and IS_ADMIN:
    users_page()
elif st.query_params.get("app") in RECEIVED:
    detail(st.query_params["app"])
else:
    inbox()
