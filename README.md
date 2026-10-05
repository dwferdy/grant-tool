# Grant Eligibility Assistant: IT Code Fair starter kit

Challenge 2: map each application to each eligibility rule, cite rule + applicant text, draft reasons a rejected applicant can understand and challenge. A human officer signs off every decision.

Grant used: **International Student Wellbeing Grant Program (Study NT), 2024-25 round** (closed; real published rules, fictional applications).

## Run
```
pip install -r requirements.txt
python -m pytest -q          # 37 tests should pass
```
Put your API key in `.env` as `ANTHROPIC_API_KEY=...` (never commit it; `.env` is in .gitignore).

Officer UI: `./run_app.sh` then open http://localhost:8501. Flow: an application arrives in the inbox → code + AI check it → the officer reviews only the flagged items → the officer sends the decision letter. Without an API key the code checks still run and the AI rules go straight to the officer.

## What's here
| Path | What | Owner |
|---|---|---|
| `data/rubric.json` | 26 atomic rules, each with source, check method, and a plain-English reason for applicants | Team A (maintain), everyone reads |
| `engine/models.py` | **The A<->B contract.** Rubric, Application, `Cell` (one grid square), `OfficerDecision`. Change only by agreement. | A + B |
| `engine/code_checks.py` | 10 rules checked by plain code (caps, dates, auspice, completeness) + `verify_quote()` anti-hallucination guard | Team A |
| `data/applications/A01-A15.json` | 15 synthetic applications (A01-A05 demo set, A06-A15 targeted test set) | Team C |
| `data/expected.json` | Answer key: expected verdict per application and rule | Team C |
| `tests/` | pytest: caps, clarification-not-rejection, fairness pair, quote guard | Team C |
| `scripts/` | Regenerate rubric/applications | - |

## Rubric at a glance
- **Code (10):** R02 ABN-or-auspice, R03 group auspice, R06 date window, R08 not started before approval, R11 complete, R12 <= $10k, R13 budget adds up, R14 travel <= 50%, R15 facilitators <= 50%, R16 catering <= 25%
- **AI finds evidence (13):** R01 applicant type, R04 NT link, R07 open to all / >= 3 providers, R17-R26 exclusions (portable assets, profit, running costs, memberships, fundraising, alcohol, illegal, application prep, political, discriminatory)
- **Officer judges (3):** R05 outstanding acquittals (department records), R09 wellbeing focus, R10 grant objectives

## Expected demo outcomes
| App | Story | Expected |
|---|---|---|
| A01 | NFP futsal cup | Approve: all met |
| A02 | Business harbour cruise | Reject: R16 catering 45%, R22 alcohol, R17 laptops, R18 profit, R07 one university only |
| A03 | Student group workshops | **Clarify, not reject:** R03 auspice unconfirmed, R07 "Students are welcome" too vague |
| A04 / A05 | Same walks program, polished vs plain/second-language English | **Identical verdicts** (approve) |

### Test set 2 (each case breaks exactly one thing)
| App | Targets | Expected |
|---|---|---|
| A06 | Travel 67% | R14 not_met |
| A07 | Consultant fees 69% | R15 not_met |
| A08 | Asks $12,500 | R12 not_met |
| A09 | Budget adds to $7,200, asks $7,500 | R13 insufficient (clarify) |
| A10 | Event in July 2025 | R06 not_met |
| A11 | "Who can attend" blank | R11 insufficient (clarify) |
| A12 | Business, no ABN, no auspice | R02 insufficient (clarify) |
| A13 | Catering exactly 25%, travel exactly 50% | All met (boundary test) |
| A14 / A15 | Fairness pair P2 + insurance grey area | Identical; R19 officer judgement |

Known limit: R08 (started before approval) can't fail on its own, because any start before the assumed approval date is also outside the R06 window. Keep this in mind if you change `earliest_approval_date`.

## Before you lock the rubric (do this first!)
1. Rules were built from the official NT.GOV.AU grant page. The full PDF guidelines could not be fetched automatically. **Download the PDF manually**, check every rule against it, and set `verified_against_pdf: true`.
2. The PDF may contain **weighted assessment criteria** not on the web page. Add them to R10 or as new rules.
3. `round.earliest_approval_date` is an assumption. Replace with a real date or label it clearly.
4. Known grey area: public liability insurance is *required* but "insurances" are an excluded running cost. Good `needs_officer_judgement` example for the demo.

## Next steps
- **Team A:** `engine/ai_checks.py`: per AI rule, call Claude (temperature 0, JSON output), return `Cell` with quotes, run `verify_quote` on every quote (unverified quote -> drop it; no verified evidence -> insufficient_evidence), run twice, disagreement -> needs_officer_judgement. System prompt must say: judge substance only, never grammar or fluency.
- **Team B:** Streamlit grid (applications x rules), click a cell -> rule text + highlighted quotes, confirm/override, typed reason required for not_met, no "approve all", blind-review toggle, SQLite audit log of `OfficerDecision`.
- **Team C:** `letters/` jinja2 template using `plain_english_reason` + `reason_values`; more test pairs; fairness test that runs the AI checks on A04/A05 and asserts identical verdicts; demo script.

## Attribution (credits slide)
Northern Territory Government, Northern Territory. "Grants for international student wellbeing". https://nt.gov.au/community/grants-and-volunteers/grants/grants-for-international-student-wellbeing. Sourced 5 October 2026.

## Email intake
Applications can arrive by email. Applicants paste `letters/email_template.txt` into the email body (subject contains "Grant application"). In the inbox: **📬 Check mail** reads an IMAP mailbox (settings in `engine/intake.py` docstring; Gmail needs an App Password), or drop `.eml` files onto the uploader. Try it with `data/sample_emails/`. Parsed applications are saved to `data/received/` (git-ignored: real personal data). Emails that can't be read are listed with the reasons so the officer can reply.
