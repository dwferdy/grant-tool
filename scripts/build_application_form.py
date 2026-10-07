"""Builds the fillable PDF application form (and a filled-in example) that applicants download, fill in and email.

Field names here are the contract with engine/intake.py (PDF_FIELDS / read_pdf_form): change both together.
Run from the project root: .venv/bin/python scripts/build_application_form.py
"""
from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

W, H = A4
M = 40                      # side margin
FW = W - 2 * M              # full field width
PURPLE, INK, MUTED, LINE, TINT = HexColor("#7F56D9"), HexColor("#101828"), HexColor("#667085"), HexColor("#D0D5DD"), HexColor("#F4EBFF")

TYPES = ["Choose one", "Not-for-profit organisation", "Student or community group", "Education provider", "Registered business"]
YES_NO = ["Choose", "Yes", "No"]
COSTS = ["Choose", "Venue hire", "Catering", "Travel", "Facilitator fees", "Equipment hire", "Materials", "Marketing", "Other"]
BUDGET_ROWS = 10

EXAMPLE = {
    "applicant_name": "Top End Pacific and Asian Community Association Inc.", "applicant_type": "Not-for-profit organisation",
    "abn": "12 345 678 901", "nt_based": "Yes", "contact_role": "Secretary",
    "project_title": "Top End Multicultural Futsal Cup",
    "description": "A one-day futsal tournament for international students. Teams are mixed, with no more than two players "
                   "from the same country in each team, so students meet people outside their usual circle. A local "
                   "employment service will run a stall about part-time work rights.",
    "location": "Marrara, Darwin NT", "start_date": "19/10/2024", "end_date": "19/10/2024",
    "who_can_attend": "All international students studying in the Northern Territory. Entry is free.",
    "wellbeing_benefit": "Physical activity, new friendships across nationalities, and practical information about working while studying.",
    "budget": [("Indoor court hire (8 hours)", "Venue hire", "2000"), ("Bibs, balls and goal hire", "Equipment hire", "1500"),
               ("Lunch and non-alcoholic drinks for 120 players", "Catering", "1800"), ("Qualified referees (4)", "Facilitator fees", "1500"),
               ("Posters and social media promotion", "Marketing", "700"), ("Participation medals", "Materials", "500")],
    "total_requested": "8000",
}


class Form:
    def __init__(self, path, values=None):
        self.c = canvas.Canvas(path, pagesize=A4)
        self.c.setTitle("Grant Application Form - International Student Wellbeing Grant")
        self.v = values or {}

    # ── drawing helpers ──
    def header(self, title, sub, tall=True):
        h = 92 if tall else 54
        self.c.setFillColor(PURPLE)
        self.c.rect(0, H - h, W, h, stroke=0, fill=1)
        self.c.setFillColor(white)
        self.c.setFont("Helvetica-Bold", 22 if tall else 15)
        self.c.drawString(M, H - (46 if tall else 32), title)
        if sub:
            self.c.setFont("Helvetica", 10.5)
            self.c.drawString(M, H - 68, sub)
        return H - h - 24

    def section(self, n, title, y):
        self.c.setFillColor(PURPLE)
        self.c.circle(M + 9, y + 4, 9, stroke=0, fill=1)
        self.c.setFillColor(white)
        self.c.setFont("Helvetica-Bold", 10)
        self.c.drawCentredString(M + 9, y + 0.5, str(n))
        self.c.setFillColor(INK)
        self.c.setFont("Helvetica-Bold", 13)
        self.c.drawString(M + 26, y, title)
        self.c.setStrokeColor(LINE)
        self.c.line(M, y - 9, W - M, y - 9)
        return y - 30

    def label(self, x, y, text, help_text=None):
        self.c.setFillColor(INK)
        self.c.setFont("Helvetica-Bold", 9.5)
        self.c.drawString(x, y, text)
        if help_text:
            self.c.setFillColor(MUTED)
            self.c.setFont("Helvetica", 8)
            self.c.drawString(x + self.c.stringWidth(text, "Helvetica-Bold", 9.5) + 6, y, help_text)

    def text(self, name, label, x, y, w, h=22, help_text=None, tooltip=None, multiline=False):
        """Label at y, box below it. Returns the y for the next row."""
        self.label(x, y, label, help_text)
        self.c.acroForm.textfield(
            name=name, tooltip=tooltip or label, x=x, y=y - 6 - h, width=w, height=h, fontName="Helvetica", fontSize=10,
            borderColor=LINE, fillColor=white, textColor=INK, borderWidth=1, forceBorder=True,
            fieldFlags="multiline" if multiline else "", value=self.v.get(name, ""))
        return y - h - 22

    def choice(self, name, label, x, y, w, options, help_text=None):
        self.label(x, y, label, help_text)
        self.c.acroForm.choice(
            name=name, tooltip=label, x=x, y=y - 28, width=w, height=22, fontName="Helvetica", fontSize=10,
            borderColor=LINE, fillColor=white, textColor=INK, borderWidth=1, forceBorder=True,
            options=options, value=self.v.get(name, options[0]), fieldFlags="combo")
        return y - 44

    def note(self, x, y, lines, size=9, color=MUTED, bold_first=False):
        for i, line in enumerate(lines):
            self.c.setFillColor(INK if bold_first and i == 0 else color)
            self.c.setFont("Helvetica-Bold" if bold_first and i == 0 else "Helvetica", size)
            self.c.drawString(x, y - i * (size + 4), line)

    def footer(self, page):
        self.c.setFillColor(MUTED)
        self.c.setFont("Helvetica", 8)
        self.c.drawString(M, 24, "International Student Wellbeing Grant - application form")
        self.c.drawRightString(W - M, 24, f"Page {page} of 2")

    # ── the form ──
    def build(self, example=False):
        c = self.c
        y = self.header("Grant Application Form", "International Student Wellbeing Grant  ·  Study NT"
                        + ("   ·   FILLED-IN EXAMPLE (names are made up)" if example else ""))
        # how to apply
        c.setFillColor(TINT)
        c.roundRect(M, y - 50, FW, 58, 8, stroke=0, fill=1)
        self.note(M + 14, y - 8, ["How to apply",
                                  "1. Type your answers in the boxes. Some boxes are lists: click them and pick an option.",
                                  "2. Save the form (File > Save).   3. Email it as an attachment. Subject: Grant application - your event name"],
                  size=9, bold_first=True)
        y -= 82

        y = self.section(1, "About you", y)
        y = self.text("applicant_name", "Organisation or group name", M, y, FW)
        self.choice("applicant_type", "Type of applicant", M, y, 250, TYPES)
        y = self.text("abn", "ABN", M + 265, y, FW - 265, help_text="11 digits. Student groups can leave this empty.")
        self.choice("nt_based", "Based in the NT?", M, y, 120, YES_NO)
        y = self.text("contact_role", "Your role", M + 265, y, FW - 265, help_text="Example: President, Secretary, Manager")
        self.text("auspicing_body", "Auspicing body", M, y, 380, help_text="Student or community groups only")
        y = self.choice("auspice_confirmed", "Agreed in writing?", M + 395, y, FW - 395, YES_NO)
        y -= 4

        y = self.section(2, "Your event", y)
        y = self.text("project_title", "Event name", M, y, FW)
        y = self.text("description", "What will happen, and why?", M, y, FW, h=92, multiline=True,
                      help_text="A few sentences in your own words.")
        self.text("location", "Where", M, y, 240, help_text="Example: Marrara, Darwin NT")
        self.text("start_date", "Start date", M + 255, y, 120, help_text="DD/MM/YYYY")
        y = self.text("end_date", "End date", M + 390, y, FW - 390, help_text="DD/MM/YYYY")
        y = self.text("who_can_attend", "Who can attend?", M, y, FW, h=40, multiline=True,
                      help_text="Example: All international students in the NT. Entry is free.")
        self.text("wellbeing_benefit", "How will it help students' wellbeing?", M, y, FW, h=52, multiline=True)
        self.footer(1)
        c.showPage()

        y = self.header("Grant Application Form", None, tall=False)
        y = self.section(3, "Budget", y)
        self.note(M, y + 4, ["One row per cost. Choose the type of cost from the list. Amounts in Australian dollars."])
        y -= 18
        cols = [(M, 300, "What is it?"), (M + 310, 120, "Type of cost"), (M + 440, FW - 440, "Amount ($)")]
        for x, _, title in cols:
            self.label(x, y, title)
        y -= 6
        budget = self.v.get("budget", [])
        for i in range(1, BUDGET_ROWS + 1):
            item, cost, amount = budget[i - 1] if i <= len(budget) else ("", "Choose", "")
            row_y = y - 24 * i
            c.acroForm.textfield(name=f"item_{i}", tooltip=f"Cost {i}: what is it?", x=cols[0][0], y=row_y, width=cols[0][1], height=20,
                                 fontName="Helvetica", fontSize=9.5, borderColor=LINE, fillColor=white, textColor=INK,
                                 borderWidth=1, forceBorder=True, value=item)
            c.acroForm.choice(name=f"cost_type_{i}", tooltip=f"Cost {i}: type of cost", x=cols[1][0], y=row_y, width=cols[1][1], height=20,
                              fontName="Helvetica", fontSize=9.5, borderColor=LINE, fillColor=white, textColor=INK, borderWidth=1,
                              forceBorder=True, options=COSTS, value=cost, fieldFlags="combo")
            c.acroForm.textfield(name=f"amount_{i}", tooltip=f"Cost {i}: amount in dollars", x=cols[2][0], y=row_y, width=cols[2][1],
                                 height=20, fontName="Helvetica", fontSize=9.5, borderColor=LINE, fillColor=white, textColor=INK,
                                 borderWidth=1, forceBorder=True, value=amount)
        y -= 24 * BUDGET_ROWS + 26
        self.label(M + 310, y - 14, "Total requested ($)")
        c.acroForm.textfield(name="total_requested", tooltip="Total requested in dollars", x=cols[2][0], y=y - 20, width=cols[2][1],
                             height=22, fontName="Helvetica-Bold", fontSize=10, borderColor=PURPLE, fillColor=white, textColor=INK,
                             borderWidth=1.5, forceBorder=True, value=self.v.get("total_requested", ""))
        self.note(M + 310, y - 36, ["Leave empty and we add up your costs."], size=8)
        y -= 70

        c.setFillColor(TINT)
        c.roundRect(M, y - 52, FW, 62, 8, stroke=0, fill=1)
        self.note(M + 14, y - 6, ["Budget limits",
                                  "Up to $10,000 in total.  Catering up to 25%.  Travel up to 50%.  Facilitator fees up to 50%.",
                                  "Not funded: alcohol, items you keep (like phones or laptops), wages or rent, fundraising, political events."],
                  size=9, bold_first=True)
        y -= 90

        y = self.section(4, "Send it", y)
        self.note(M, y + 4, ["1. Check every box on both pages.",
                             "2. Save the form (File > Save). Keep the file name, or add your group's name.",
                             "3. Email it as an ATTACHMENT, to the address you got this form from.",
                             "    Subject: Grant application - your event name"], size=10, color=INK)
        self.footer(2)
        c.save()


if __name__ == "__main__":
    Form("letters/application_form.pdf").build()
    Form("letters/application_form_example.pdf", EXAMPLE).build(example=True)
    print("written: letters/application_form.pdf, letters/application_form_example.pdf")
