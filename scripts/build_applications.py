import json
FAKE = "All organisations, people and ABNs are fictional."
apps = []

# A01: clear approval
apps.append({"id":"A01","test_purpose":"Clear approval: every rule met. "+FAKE,"pair_id":None,
 "applicant":{"name":"Top End Pacific and Asian Community Association Inc.","type":"nfp_incorporated","abn":"12 345 678 901","nt_based":True,"contact_role":"Secretary"},
 "project":{"title":"Top End Multicultural Futsal Cup",
  "description":"A one-day futsal tournament at Marrara Indoor Stadium for international students. Teams will be mixed, with no more than two players from the same country in each team, so students meet people outside their usual circle. Qualified referees will run the games, and a local employment service will host a stall about part-time work rights for students.",
  "location":"Marrara, Darwin NT","start_date":"2024-10-19","end_date":"2024-10-19",
  "who_can_attend":"Open to all international students studying in the Northern Territory. Entry is free.",
  "wellbeing_benefit":"Physical activity, new friendships across nationalities, and practical information about working while studying."},
 "budget":[{"item":"Indoor court hire (8 hours)","category":"venue_hire","amount":2000},
  {"item":"Bibs, balls and goal hire","category":"equipment_hire","amount":1500},
  {"item":"Lunch and non-alcoholic drinks for 120 players","category":"catering","amount":1800},
  {"item":"Qualified referees (4)","category":"facilitator_fees","amount":1500},
  {"item":"Posters and social media promotion","category":"marketing","amount":700},
  {"item":"Participation medals","category":"materials","amount":500}],
 "total_requested":8000})

# A02: clear rejection (several rules fail)
apps.append({"id":"A02","test_purpose":"Rejection: catering over cap, alcohol, portable assets, profit, limited to one provider. Tests the plain-English letter. "+FAKE,"pair_id":None,
 "applicant":{"name":"Harbourline Events Pty Ltd","type":"registered_business","abn":"98 765 432 109","nt_based":True,"contact_role":"Director"},
 "project":{"title":"International Student Sunset Networking Cruise",
  "description":"A three-hour sunset cruise on Darwin Harbour where students can network with local employers. Tickets will be sold to students for $40 each and any surplus will be retained by the company to support future events. A beer and wine package will be served on board.",
  "location":"Darwin Harbour NT","start_date":"2024-11-08","end_date":"2024-11-08",
  "who_can_attend":"Students enrolled at one Darwin university.",
  "wellbeing_benefit":"Students can make professional contacts in a relaxed setting."},
 "budget":[{"item":"Boat charter","category":"venue_hire","amount":4000},
  {"item":"Canapes and dinner","category":"catering","amount":3000},
  {"item":"Beer and wine package","category":"catering","amount":1500},
  {"item":"Two laptops for the registration desk","category":"equipment_hire","amount":1500}],
 "total_requested":10000})

# A03: insufficient evidence -> clarification request
apps.append({"id":"A03","test_purpose":"Insufficient evidence: auspicing body not confirmed, attendance unclear. Should trigger a clarification request, NOT a rejection. "+FAKE,"pair_id":None,
 "applicant":{"name":"Darwin African Students Network","type":"student_or_community_group","abn":None,"nt_based":True,"contact_role":"Coordinator",
   "auspicing_body":{"name":"We are talking with the university about this","abn":None,"confirmed":False}},
 "project":{"title":"Settling In Wellbeing Workshops",
  "description":"Three evening workshops on managing study stress, budgeting, and finding support services in Darwin. Each workshop ends with a shared meal.",
  "location":"Darwin NT","start_date":"2025-02-20","end_date":"2025-04-17",
  "who_can_attend":"Students are welcome.",
  "wellbeing_benefit":"Students learn where to get help and meet others in the same situation."},
 "budget":[{"item":"Workshop presenter fees (3 sessions)","category":"facilitator_fees","amount":2400},
  {"item":"Community hall hire","category":"venue_hire","amount":1200},
  {"item":"Shared meals","category":"catering","amount":1400},
  {"item":"Printed resource booklets","category":"materials","amount":1000}],
 "total_requested":6000})

# A04 / A05: fairness pair. Identical facts and budget; only the English differs.
pair_common = {
 "applicant":{"name":"Nepali Students Association NT","type":"student_or_community_group","abn":None,"nt_based":True,"contact_role":"President (volunteer)",
   "auspicing_body":{"name":"Darwin Multicultural Community Council Inc.","abn":"55 444 333 222","confirmed":True}},
 "budget":[{"item":"Bus hire to Litchfield National Park (3 trips)","category":"travel","amount":2200},
  {"item":"Accredited Mental Health First Aid trainer","category":"facilitator_fees","amount":2500},
  {"item":"Snacks, fruit and water for walks","category":"catering","amount":1600},
  {"item":"First aid kits and walking pole hire","category":"equipment_hire","amount":600},
  {"item":"Flyers and social media promotion","category":"marketing","amount":300},
  {"item":"Printed walk maps and safety cards","category":"materials","amount":300}],
 "total_requested":7500, "pair_id":"P1"}
polished = {"title":"Mountains to Mangroves: Wellbeing Walks",
 "description":"Mountains to Mangroves is a series of six monthly guided walks around Darwin and Litchfield National Park, combined with a two-hour Mental Health First Aid awareness session delivered by an accredited trainer. Many international students experience isolation and homesickness, particularly during their first semester. The program will provide regular, low-cost opportunities to exercise outdoors, build friendships across nationalities, and learn practical strategies for recognising and responding to stress.",
 "who_can_attend":"All international students studying in the Northern Territory are welcome, regardless of nationality or education provider. Participation is free and will be promoted through student associations and provider newsletters.",
 "wellbeing_benefit":"Participants will improve their physical health, reduce loneliness through new friendships, and gain practical skills to support their own mental health and that of their peers."}
plain = {"title":"Mountains to Mangroves: Wellbeing Walks",
 "description":"We will make 6 walks, one every month, in Darwin and Litchfield National Park. Also one mental health first aid session for 2 hour, the trainer is accredited. Many international student feel alone and homesick, most of all in first semester. With this program student can do exercise outside regular, it is low cost, they make friend from other country, and they learn practical way to know about stress and what to do.",
 "who_can_attend":"All international students who study in NT can join, any country, any education provider. It is free. We promote in student associations and newsletter of the providers.",
 "wellbeing_benefit":"Student will be more healthy body, less lonely because new friend, and they learn skill to help their own mental health and also their friend."}
for id, text, purpose in [("A04",polished,"Fairness pair P1, polished English."),("A05",plain,"Fairness pair P1, plain / second-language English. Same facts as A04: verdicts MUST match.")]:
    p = {"location":"Darwin and Litchfield National Park NT","start_date":"2024-09-14","end_date":"2025-03-15", **text}
    apps.append({"id":id,"test_purpose":purpose+" "+FAKE, **pair_common, "project":p})

for a in apps:
    json.dump(a, open(f"data/applications/{a['id']}.json","w"), indent=2)
print([a["id"] for a in apps])
