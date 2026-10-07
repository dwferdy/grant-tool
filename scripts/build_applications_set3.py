"""Test set 3: A16-A25. AI rules and the limits of the offline keyword reviewer.

Every case passes all code rules, so any failure points at one AI rule.
- A16-A21 paraphrase: the exclusion is broken in words the keyword lists don't contain.
  Claude should catch it; the offline reviewer is expected to MISS it (recorded as "offline" in expected.json).
- A22-A23 false alarm: an innocent budget line contains a listed keyword ("camera", "campaign").
  Claude should pass it; the offline reviewer is expected to wrongly flag it.
- A24 control: explicit wording, both reviewers should agree.
- A25 unclear NT link: online event, applicant outside the NT, both should ask to clarify.
Run from the project root: .venv/bin/python scripts/build_applications_set3.py
"""
import json
FAKE = "All organisations, people and ABNs are fictional."
OPEN = "Open to all international students studying in the Northern Territory. Entry is free."

def nfp(name, abn, nt=True):
    return {"name": name, "type": "nfp_incorporated", "abn": abn, "nt_based": nt, "contact_role": "Secretary"}
def proj(title, desc, start, end, who=OPEN, benefit="Social connection and wellbeing for international students.", loc="Darwin NT"):
    return {"title": title, "description": desc, "location": loc, "start_date": start, "end_date": end,
            "who_can_attend": who, "wellbeing_benefit": benefit}
def b(*lines): return [{"item": i, "category": c, "amount": a} for i, c, a in lines]
def app(id, purpose, applicant, project, budget):
    return {"id": id, "test_purpose": purpose + " " + FAKE, "pair_id": None, "applicant": applicant, "project": project,
            "budget": budget, "total_requested": sum(x["amount"] for x in budget)}

apps = [
 # ── paraphrase: offline should miss, Claude should catch ──
 app("A16", "R22 alcohol, paraphrased: 'tasting paddles' at a brewery. No listed keyword (beer/wine/alcohol) appears.",
  nfp("Top End Heritage Walks Association Inc.", "61 234 567 001"),
  proj("Darwin After Dark: Heritage Walk and Brewery Tour",
       "A Friday evening guided walk through Darwin's wartime heritage sites, finishing with a behind-the-scenes tour of a local craft brewery where each student receives a tasting paddle of the brewery's range.",
       "2024-09-13", "2024-09-13",
       who="Open to all international students aged 18 and over studying in the Northern Territory."),
  b(("Heritage guide (evening walk)", "facilitator_fees", 1500), ("Riverside function room hire", "venue_hire", 2000),
    ("Brewery tour with tasting paddles for 30 students", "catering", 1500), ("Bus between walk and brewery", "travel", 1500),
    ("Posters and social media promotion", "marketing", 500))),

 app("A17", "R17 portable assets, paraphrased: speakers and a projector bought and kept. No listed keyword (laptop/phone/tablet/camera) appears.",
  nfp("Nightcliff Student Movie Club Inc.", "61 234 567 002"),
  proj("Movies Under the Stars",
       "Four outdoor movie nights at Nightcliff foreshore showing films from students' home countries, each introduced by a student from that country. The club will buy two Bluetooth speakers and a portable projector and keep them for future club events.",
       "2024-08-03", "2024-08-24"),
  b(("Two portable Bluetooth speakers (kept by the club)", "materials", 900), ("Portable projector and screen (kept by the club)", "materials", 1100),
    ("Foreshore site booking (4 nights)", "venue_hire", 2000), ("Popcorn and soft drinks", "catering", 1200),
    ("Film screening licences", "other", 1000), ("Flyers and social media promotion", "marketing", 800))),

 app("A18", "R21 fundraising, paraphrased: entry money goes to a flood relief appeal. No listed keyword (fundraising/charity/donation) appears.",
  nfp("Palmerston International Friends Inc.", "61 234 567 003"),
  proj("Global Talent Nights",
       "Three talent nights where international students perform music, dance and comedy from their cultures. Each night has a gold-coin entry, and all money collected at the door goes to the Top End flood relief appeal.",
       "2024-11-08", "2024-11-22", loc="Palmerston NT"),
  b(("Community hall hire (3 nights)", "venue_hire", 2400), ("Sound and lighting hire", "equipment_hire", 1800),
    ("MC and stage manager", "facilitator_fees", 1500), ("Light supper", "catering", 1400), ("Posters and social media promotion", "marketing", 400))),

 app("A19", "R18 profit, paraphrased: a business keeps ticket income left after costs. No listed keyword (profit/surplus/'tickets will be sold') appears.",
  {"name": "Harbourline Events Pty Ltd", "type": "registered_business", "abn": "61 234 567 004", "nt_based": True, "contact_role": "Director"},
  proj("Sunset Harbour Social",
       "A sunset harbour cruise where international students can meet each other and local volunteers. Tickets cost $35 per student, and any ticket income left over once the costs are covered goes to Harbourline Events.",
       "2025-03-15", "2025-03-15",
       who="Open to all international students in the Northern Territory who buy a ticket."),
  b(("Boat charter (3 hours)", "venue_hire", 3500), ("Finger food", "catering", 1500), ("Event host", "facilitator_fees", 1200),
    ("Bus to the wharf and back", "travel", 1000), ("Online promotion", "marketing", 800))),

 app("A20", "R25 political, paraphrased: students hand a petition to their local member of parliament. No listed keyword (political/election/campaign/rally) appears.",
  nfp("Darwin International Student Voice Inc.", "61 234 567 005"),
  proj("Student Voices at Parliament House",
       "A one-day visit to Parliament House in Darwin. Students will learn how laws are made, then meet our local member of parliament to hand over a petition asking for longer work-hour limits on student visas.",
       "2025-02-20", "2025-02-20"),
  b(("Bus hire", "travel", 1500), ("Workshop facilitator: how parliament works", "facilitator_fees", 1800),
    ("Lunch", "catering", 1200), ("Petition printing and folders", "materials", 500), ("Meeting room hire", "venue_hire", 1000))),

 app("A21", "R20 membership fees, paraphrased: 'subscriptions' to a professional body. No listed keyword (membership) appears.",
  {"name": "Arafura Institute of Technology", "type": "education_provider", "abn": "61 234 567 006", "nt_based": True, "contact_role": "Careers Officer"},
  proj("Engineering Futures Night",
       "An evening where international engineering students meet local engineers, followed by a one-year student subscription to a national engineering professional body for each participant.",
       "2024-10-10", "2024-10-10",
       who="Open to all international students in the NT studying engineering at any education provider."),
  b(("Annual student subscriptions to a national engineering professional body (12 students)", "other", 1800),
    ("Guest speakers (3 local engineers)", "facilitator_fees", 1500), ("Lecture theatre hire", "venue_hire", 1200),
    ("Light supper", "catering", 1000), ("Promotion", "marketing", 500))),

 # ── false alarm: offline should wrongly flag, Claude should pass ──
 app("A22", "False alarm for R17: hiring a photographer who brings their own camera is a service, not buying a portable asset. Everything should be met.",
  nfp("Casuarina Cultural Exchange Inc.", "61 234 567 007"),
  proj("Lunar New Year Community Lunch",
       "A Lunar New Year lunch where international students share dishes and traditions with the wider community. A photographer will capture the day so students can share photos with family overseas.",
       "2025-01-29", "2025-01-29", loc="Casuarina, Darwin NT"),
  b(("Event photographer (brings own camera), 3 hours", "facilitator_fees", 600), ("Community hall hire", "venue_hire", 1500),
    ("Shared lunch for 100 people", "catering", 1200), ("Lion dance performance", "facilitator_fees", 1200),
    ("Decorations", "materials", 500))),

 app("A23", "False alarm for R25: a 'social media campaign' is marketing, not a political campaign. Everything should be met.",
  nfp("Top End Running Club Inc.", "61 234 567 008"),
  proj("Welcome Fun Run",
       "A 5 km fun run along the Darwin waterfront to welcome new international students, followed by a breakfast where they can meet local running groups.",
       "2025-03-01", "2025-03-01"),
  b(("Social media campaign to promote the event", "marketing", 600), ("Course permits and barriers", "equipment_hire", 1400),
    ("Breakfast after the run", "catering", 1500), ("First aid team", "facilitator_fees", 1000), ("Finisher medals", "materials", 1500))),

 # ── control: both reviewers should agree ──
 app("A24", "Control for R24: an explicit 'grant writing' budget line. Both reviewers should flag it.",
  nfp("Darwin Multifaith Youth Network Inc.", "61 234 567 009"),
  proj("Harmony Week Picnic",
       "A Harmony Week picnic in the Darwin Botanic Gardens with games, music and food from students' home countries.",
       "2025-03-22", "2025-03-22"),
  b(("Grant writing support for this application", "other", 800), ("Picnic area booking", "venue_hire", 1000),
    ("Games and equipment hire", "equipment_hire", 1200), ("Picnic food", "catering", 1500), ("Musicians", "facilitator_fees", 1500))),

 # ── clarify: unclear link to the NT ──
 app("A25", "R04 unclear: an online event run by an applicant outside the NT, open to students across Australia. Ask to clarify (not reject).",
  nfp("Southern Cross Student Connect Inc.", "61 234 567 010", nt=False),
  proj("Study Buddy Online Meetups",
       "Weekly online meetups where international students practise conversational English and share study tips in small breakout rooms.",
       "2024-08-01", "2024-11-28",
       who="All international students in Australia can join for free.",
       loc="Online (video calls)"),
  b(("Video platform subscription", "other", 600), ("Conversation hosts (17 sessions)", "facilitator_fees", 2500),
    ("Online promotion", "marketing", 900), ("Printable study guides", "materials", 1000))),
]

for a in apps:
    json.dump(a, open(f"data/applications/{a['id']}.json", "w"), indent=2)
print(len(apps), "written")
