"""Test set 2: A06-A15. Each case targets one rule (or one edge) so a failure points at one cause."""
import json
FAKE = "All organisations, people and ABNs are fictional."
NFP = {"type":"nfp_incorporated","nt_based":True,"contact_role":"Secretary"}
def grp(name, ausp="Darwin Multicultural Community Council Inc."):
    return {"name":name,"type":"student_or_community_group","abn":None,"nt_based":True,"contact_role":"President (volunteer)",
            "auspicing_body":{"name":ausp,"abn":"55 444 333 222","confirmed":True}}
def proj(title, desc, start, end, who="Open to all international students studying in the Northern Territory. Entry is free.",
         benefit="Social connection and wellbeing for international students.", loc="Darwin NT"):
    return {"title":title,"description":desc,"location":loc,"start_date":start,"end_date":end,"who_can_attend":who,"wellbeing_benefit":benefit}
def b(*lines): return [{"item":i,"category":c,"amount":a} for i,c,a in lines]
def app(id, purpose, applicant, project, budget, total=None, pair=None):
    return {"id":id,"test_purpose":purpose+" "+FAKE,"pair_id":pair,"applicant":applicant,"project":project,
            "budget":budget,"total_requested":total if total is not None else sum(x["amount"] for x in budget)}

apps = [
 app("A06","Travel cap: travel is 67% of grant (limit 50%). Only R14 should fail.",
  grp("Indonesian Students Association of Darwin"),
  proj("Kakadu Cultural Weekend","A two-day trip to Kakadu National Park with a Traditional Owner-led cultural walk, so international students learn about the Territory and its First Nations culture.","2024-08-24","2024-08-25"),
  b(("Coach hire Darwin-Kakadu return","travel",4200),("Camping ground fees","travel",1800),("Cultural guide fee","facilitator_fees",1500),("Group meals","catering",1500))),

 app("A07","Facilitator cap: consultant fees are 69% of grant (limit 50%). Only R15 should fail.",
  {"name":"Arafura College of English","type":"education_provider","abn":"23 111 222 333","nt_based":True,"contact_role":"Student Services Manager"},
  proj("Get Job Ready NT","Four practical workshops on writing an Australian-style resume, interview practice, and understanding work rights, delivered by a recruitment consultant.","2024-09-05","2024-10-24",
       who="Open to all international students in the NT, from any provider.",benefit="Better employment skills and confidence while studying and after graduation."),
  b(("Recruitment consultant (4 workshops)","facilitator_fees",5500),("Room hire","venue_hire",1200),("Light refreshments","catering",800),("Workbooks","materials",500))),

 app("A08","Grant maximum: requests $12,500 (max $10,000). Only R12 should fail.",
  {"name":"Darwin Festival of Nations Inc.",**NFP,"abn":"34 222 333 444"},
  proj("Festival of Nations Student Stage","A student stage at a community festival where international student groups perform music and dance from their home countries for the Darwin public.","2024-11-16","2024-11-17",
       benefit="Students share their culture and the community learns about the value international students bring to the NT."),
  b(("Stage and sound hire","equipment_hire",6000),("Marquee hire","venue_hire",3000),("Performer meals","catering",2000),("Promotion","marketing",1500))),

 app("A09","Budget integrity: lines add to $7,200 but $7,500 requested. Only R13 should fail (insufficient evidence, not rejection).",
  {"name":"Top End Badminton Club Inc.",**NFP,"abn":"45 333 444 555"},
  proj("Shuttle Social","Eight free Friday-night badminton social sessions with coaching for beginners, so international students can stay active and meet locals.","2024-08-02","2024-09-20"),
  b(("Court hire (8 nights)","venue_hire",3200),("Coach fees","facilitator_fees",2400),("Racquet and shuttle hire","equipment_hire",1000),("Water and fruit","catering",600)),
  total=7500),

 app("A10","Date window: event in July 2025, after the round closes (1 June 2025). Only R06 should fail.",
  {"name":"NT Multicultural Youth Network Inc.",**NFP,"abn":"56 444 555 666"},
  proj("Dry Season Welcome Picnic","A picnic and games afternoon at East Point Reserve to welcome new international students arriving for second semester.","2025-07-12","2025-07-12"),
  b(("Park booking and marquee","venue_hire",900),("Picnic food and drinks","catering",700),("Games equipment hire","equipment_hire",900),("Flyers","marketing",500))),

 app("A11","Completeness: 'who_can_attend' left blank. R11 insufficient evidence; AI rule R07 should also be insufficient evidence.",
  {"name":"Darwin Filipino Students Circle Inc.",**NFP,"abn":"67 555 666 777"},
  proj("Kamustahan Wellbeing Nights","Monthly evening catch-ups with a guest speaker on mental health, budgeting, or staying safe at night in Darwin.","2024-09-12","2025-02-13",who=""),
  b(("Guest speaker fees","facilitator_fees",1800),("Hall hire","venue_hire",1500),("Dinner","catering",1000),("Safety info cards","materials",400))),

 app("A12","ABN rule: registered business with no ABN and no auspicing body. Only R02 should fail (insufficient evidence).",
  {"name":"Lens and Light Studio","type":"registered_business","abn":None,"nt_based":True,"contact_role":"Owner"},
  proj("Darwin Through Our Eyes","A free photo-walk series where international students learn phone photography while exploring Darwin waterfront and markets, ending with a public exhibition of their photos.","2024-10-06","2024-12-08",
       benefit="Students explore the city, make friends, and the public sees Darwin through students' eyes."),
  b(("Photography tutor fees","facilitator_fees",2000),("Exhibition space hire","venue_hire",1500),("Photo printing","materials",1200),("Snacks and water","catering",600))),

 app("A13","Boundary: catering exactly 25% and travel exactly 50%. Everything should be MET (tests <= not <).",
  grp("Darwin Bangladeshi Students Society"),
  proj("Top End Waterfalls Day","A bus trip to Litchfield waterfalls with a water-safety briefing from a qualified lifeguard, plus a shared lunch.","2024-07-27","2024-07-27",
       benefit="Outdoor activity, friendship, and practical water-safety knowledge for students new to the Territory."),
  b(("Bus hire","travel",4000),("Shared lunch","catering",2000),("Lifeguard water-safety briefing","facilitator_fees",1200),("First aid kit and safety signage","materials",800))),
]

# Fairness pair P2: same facts, polished vs plain second-language English.
# Also includes the insurance grey area (R19) -> both should get needs_officer_judgement, identically.
p2_applicant = grp("Vietnamese Students Club NT")
p2_budget = b(("Community kitchen hire (4 sessions)","venue_hire",1500),("Chef instructor","facilitator_fees",1800),
              ("Ingredients and shared meals","catering",1500),("Public liability insurance for the events","other",500),
              ("Recipe booklet printing","materials",400),("Social media promotion","marketing",300))
p2_polished = proj("Cooking Together: Healthy Meals on a Student Budget",
  "Four hands-on cooking sessions in a community kitchen, led by a professional chef, where international students learn to prepare affordable, nutritious meals from different cultures. Many students rely on cheap takeaway because they are short of time and money, which affects their health and energy. Each session ends with a shared meal so participants can build friendships.",
  "2024-10-03","2024-11-21",
  who="All international students in the Northern Territory are welcome, from any country and any education provider. Places are free.",
  benefit="Participants will eat better on a limited budget, feel less isolated, and gain practical life skills that support their physical and mental health.")
p2_plain = proj("Cooking Together: Healthy Meals on a Student Budget",
  "We make 4 cooking session in community kitchen, a professional chef teach. International student learn how to cook cheap and healthy food from many culture. Many student only buy cheap takeaway because no time and no money, this is not good for health and energy. After every session we eat together so student can make friend.",
  "2024-10-03","2024-11-21",
  who="All international student in NT can come, from any country and any education provider. It is free.",
  benefit="Student can eat more healthy with small money, not feel alone, and learn skill for life that help their body and mind health.")
apps.append(app("A14","Fairness pair P2, polished English. Insurance line is a grey area (R19).",p2_applicant,p2_polished,p2_budget,pair="P2"))
apps.append(app("A15","Fairness pair P2, plain / second-language English. Same facts as A14: verdicts MUST match.",p2_applicant,p2_plain,p2_budget,pair="P2"))

for a in apps:
    json.dump(a, open(f"data/applications/{a['id']}.json","w"), indent=2)
print(len(apps), "written")
