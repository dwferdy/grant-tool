"""Officer inbox. Run with:  streamlit run app.py

Flow: application arrives -> AI + code review it -> officer checks only the flagged items -> officer sends the decision.
"""
from __future__ import annotations
import html, re, time
from datetime import datetime
import pandas as pd
import streamlit as st
from engine.loader import load_rubric, load_applications
from engine.models import Verdict, OfficerDecision
from engine.assess import assess, outcome
from engine.ai_checks import api_available, cached_cells, offline_mode, MODEL
from engine.letters import render_letter
from engine import audit, intake

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

RB = load_rubric()
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
OFFICER_CHOICES = [Verdict.MET, Verdict.NOT_MET, Verdict.INSUFFICIENT_EVIDENCE, Verdict.NOT_APPLICABLE]
FLAG_ORDER = [Verdict.NOT_MET, Verdict.INSUFFICIENT_EVIDENCE, Verdict.NEEDS_OFFICER_JUDGEMENT, Verdict.MET, Verdict.NOT_APPLICABLE]

# ---------- state ----------
if "cells" not in st.session_state:
    st.session_state.cells = {}
def cells_for(aid: str) -> dict:
    if aid not in st.session_state.cells:
        st.session_state.cells[aid] = assess(APPS[aid], RB)   # uses cached AI results, never calls the API
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
with st.sidebar:
    st.markdown("### 👋 Officer")
    officer = st.text_input("Your name", key="officer", placeholder="Type your name to start")
    page = st.radio("Go to", ["📨 Inbox", "🗂 Audit log"], label_visibility="collapsed")
    st.divider()
    blind = st.toggle("Blind review", help="Hide everything the AI found until you have decided each rule yourself. "
                                           "Use this to check you are not just agreeing with the AI.")
    if offline_mode():
        st.warning("🧪 **Offline test mode.** A free keyword checker stands in for the AI (no API calls, no cost). "
                   "It only catches words on its lists. Remove `AI_MODE=offline` from `.env` to use Claude.")
    elif api_available():
        st.caption(f"🤖 AI review is on (`{MODEL}`)")
    else:
        st.caption("🤖 AI review is **off**: add `ANTHROPIC_API_KEY=...` to `.env`. "
                   "Code checks still run; anything that needs AI comes to you.")
    with st.expander("How it works"):
        st.markdown("1. **📨 An application arrives** in your inbox.\n"
                    "2. **🤖 The AI and code check it** against all 26 rules.\n"
                    "3. **👤 You review** only what was flagged (and the 3 rules a person must always decide).\n"
                    "4. **✉️ You send the decision.** The letter explains each reason in plain English.")

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
            for m in bad:
                with st.container(border=True):
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
    st.title("📨 Inbox")
    waiting = [a for a in RECEIVED if a not in FINALS]
    c1, c2, c3 = st.columns(3)
    c1.metric("Waiting for you", len(waiting))
    c2.metric("Decided", len(FINALS))
    c3.metric("Emails we couldn't read", len(audit.unreadable_mail()))

    mail_box()
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
        with st.container(border=True):
            left, mid, right = st.columns([6, 2, 1.3], vertical_alignment="center")
            unread = "🔵 " if aid not in FINALS and not decisions_for(aid) else ""
            left.markdown(f"{unread}**{html.escape(app.applicant.name)}**  ·  <small>{RECEIVED[aid]:%d %b %H:%M} · {aid}</small>",
                          unsafe_allow_html=True)
            left.markdown(f"{app.project.title} — ${app.total_requested:,.0f}")
            if aid in FINALS:
                mid.markdown(f"**Sent:** {OUTCOME[FINALS[aid]['outcome']]}")
                left.caption(f"Decided by {FINALS[aid]['officer']}")
            elif blind:
                mid.markdown("🙈 Blind review")
            else:
                mid.markdown(f"AI suggests  \n**{OUTCOME[ai_suggestion(aid)]}**")
                issues = [r for r in to_review(aid, False) if cells[r].verdict in (Verdict.NOT_MET, Verdict.INSUFFICIENT_EVIDENCE)]
                left.caption("Flagged: " + ", ".join(f"{ICON[cells[r].verdict]} {SHORT[r]}" for r in issues)
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

    with st.container(border=True):
        top_l, top_r = st.columns([4, 1.4], vertical_alignment="center")
        icon = ICON[dec.officer_verdict] if dec else (ICON[cell.verdict] if show_ai else "▫️")
        top_l.markdown(f"{icon} **{SHORT[rid]}** <small style='opacity:.6'>{rid}</small>", unsafe_allow_html=True)
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
    st.title("🗂 Audit log")
    st.caption("Every decision is stored and never overwritten. A changed decision is a new row.")
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

# ---------- router ----------
if page == "🗂 Audit log":
    audit_log()
elif st.query_params.get("app") in RECEIVED:
    detail(st.query_params["app"])
else:
    inbox()
