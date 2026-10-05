"""A<->B contract. Team A (engine) produces these; Team B (officer UI) reads them.
Change this file only by agreement between teams."""
from __future__ import annotations
from datetime import date, datetime
from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field

class Verdict(str, Enum):
    MET = "met"
    NOT_MET = "not_met"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NEEDS_OFFICER_JUDGEMENT = "needs_officer_judgement"
    NOT_APPLICABLE = "not_applicable"  # rule does not apply to this applicant type

# ---------- Rubric ----------
class Source(BaseModel):
    document: str
    section: str
    url: str

class Rule(BaseModel):
    id: str
    type: Literal["eligibility_gate","numeric_cap","exclusion","assessment_criterion","integrity_check"]
    check_method: Literal["code","ai_evidence","officer_judgement"]
    rule: str
    source: Source
    check: str
    evidence_needed: str
    if_missing: str
    plain_english_reason: str
    verified_against_pdf: bool = False
    # Optional, for rules a super admin adds in the app (data/custom_rules.json). Official rules leave these unset.
    short_name: Optional[str] = None
    params: Optional[dict] = None       # code rule built from a template, e.g. {"template": "category_cap", ...}
    keywords: list[str] = []            # used only by the offline keyword reviewer (AI_MODE=offline)
    custom: bool = False
    active: bool = True
    added_by: Optional[str] = None
    added_at: Optional[datetime] = None

class Round(BaseModel):
    name: str
    window_start: date
    window_end: date
    earliest_approval_date: date

class Rubric(BaseModel):
    rubric_id: str
    grant: str
    round: Round
    allowed_applicant_types: list[str]
    budget_categories: list[str]
    rules: list[Rule]
    locked: bool = False
    locked_by: Optional[str] = None
    locked_at: Optional[datetime] = None

# ---------- Application (synthetic input) ----------
class AuspicingBody(BaseModel):
    name: Optional[str] = None
    abn: Optional[str] = None
    confirmed: bool = False

class Applicant(BaseModel):
    name: str
    type: str
    abn: Optional[str] = None
    nt_based: Optional[bool] = None
    contact_role: Optional[str] = None
    auspicing_body: Optional[AuspicingBody] = None

class BudgetLine(BaseModel):
    item: str
    category: str
    amount: float

class Project(BaseModel):
    title: str
    description: str
    location: str
    start_date: date
    end_date: date
    who_can_attend: str
    wellbeing_benefit: str

class Application(BaseModel):
    id: str
    test_purpose: str = Field(description="Why this synthetic case exists (demo/test only)")
    pair_id: Optional[str] = None
    applicant: Applicant
    project: Project
    budget: list[BudgetLine]
    total_requested: float

# ---------- Engine output: one cell of the application x rule grid ----------
class Quote(BaseModel):
    field: str           # e.g. "project.description" or "budget[2].item"
    text: str            # must appear verbatim in that field
    verified: bool = False  # set by code, never by the model

class Cell(BaseModel):
    application_id: str
    rule_id: str
    verdict: Verdict
    checked_by: Literal["code","ai","officer"]
    applicant_quotes: list[Quote] = []
    reasoning: str                     # short, for the officer
    missing: Optional[str] = None      # what evidence would change the outcome
    reason_values: dict = {}           # fills {placeholders} in plain_english_reason
    ai_runs_agree: Optional[bool] = None  # AI rules run twice; False -> needs_officer_judgement

# ---------- Officer layer (Team B) ----------
class OfficerDecision(BaseModel):
    application_id: str
    rule_id: str
    ai_verdict: Verdict
    officer_verdict: Verdict
    overridden: bool
    blind_review: bool                 # AI verdict hidden until officer decided
    officer_note: Optional[str] = None # required in own words for any not_met
    officer: str
    decided_at: datetime
    seconds_spent: float
