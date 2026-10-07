"""
Step 1 - Synthetic HR dataset generator for the HR Graph RAG project.

Creates:
  data/raw/*.csv              -> structured data (loaded into SQL in Step 2)
  data/docs/policies/*.md     -> HR policy documents
  data/docs/reviews/*.txt     -> performance review write-ups (one per employee)
  data/docs/resumes/*.txt     -> candidate resumes
  data/docs/projects/*.txt    -> project reports
  data/ground_truth/*.csv     -> facts that exist ONLY inside documents
                                 (used later to evaluate Graph RAG vs plain RAG)

Run from the project root:  python src/data_gen/generate_data.py
"""

import csv
import random
from datetime import date, timedelta
from pathlib import Path

from faker import Faker

# ------------------------------------------------------------------ config
SEED = 42
NUM_EMPLOYEES = 200
NUM_PROJECTS = 30
NUM_CANDIDATES = 50
ATTENDANCE_MONTHS = 12
PAYROLL_MONTHS = 6
TODAY = date(2026, 9, 30)

random.seed(SEED)
fake = Faker("en_IN")
Faker.seed(SEED)

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
DOCS = ROOT / "data" / "docs"
TRUTH = ROOT / "data" / "ground_truth"
for p in [RAW, TRUTH, DOCS / "policies", DOCS / "reviews", DOCS / "resumes", DOCS / "projects"]:
    p.mkdir(parents=True, exist_ok=True)

# ------------------------------------------------------------------ reference data
DEPARTMENTS = [
    ("Engineering", "Kochi"),
    ("Data Science", "Bengaluru"),
    ("Quality Assurance", "Kochi"),
    ("Human Resources", "Kochi"),
    ("Finance", "Mumbai"),
    ("Sales", "Mumbai"),
    ("Marketing", "Bengaluru"),
    ("Customer Support", "Chennai"),
]

SKILLS = {
    "Programming": ["Python", "Java", "JavaScript", "TypeScript", "C++", "Go", "SQL"],
    "Web": ["React", "Angular", "Node.js", "Django", "FastAPI", "Spring Boot"],
    "Data": ["Machine Learning", "Deep Learning", "NLP", "Data Analysis", "Power BI", "Tableau", "Spark"],
    "Cloud & DevOps": ["AWS", "Azure", "Docker", "Kubernetes", "CI/CD"],
    "Testing": ["Selenium", "Manual Testing", "Test Automation", "Performance Testing"],
    "Business": ["Recruitment", "Payroll Processing", "Employee Relations", "Accounting",
                 "Financial Analysis", "Negotiation", "CRM", "SEO", "Content Writing",
                 "Digital Marketing", "Customer Service", "Ticketing Systems"],
}
SKILL_LIST = [(s, cat) for cat, items in SKILLS.items() for s in items]

DEPT_SKILLS = {
    "Engineering": SKILLS["Programming"] + SKILLS["Web"] + SKILLS["Cloud & DevOps"],
    "Data Science": ["Python", "SQL"] + SKILLS["Data"] + ["AWS", "Docker"],
    "Quality Assurance": SKILLS["Testing"] + ["Python", "Java", "SQL", "CI/CD"],
    "Human Resources": ["Recruitment", "Payroll Processing", "Employee Relations", "Data Analysis"],
    "Finance": ["Accounting", "Financial Analysis", "Payroll Processing", "Power BI", "SQL"],
    "Sales": ["Negotiation", "CRM", "Customer Service", "Data Analysis"],
    "Marketing": ["SEO", "Content Writing", "Digital Marketing", "Data Analysis", "Tableau"],
    "Customer Support": ["Customer Service", "Ticketing Systems", "CRM", "SQL"],
}

DESIGNATIONS = {
    "Engineering": ["Software Engineer", "Senior Software Engineer", "Tech Lead"],
    "Data Science": ["Data Analyst", "Data Scientist", "Senior Data Scientist"],
    "Quality Assurance": ["QA Engineer", "Senior QA Engineer", "QA Lead"],
    "Human Resources": ["HR Executive", "Senior HR Executive", "HR Business Partner"],
    "Finance": ["Accountant", "Financial Analyst", "Senior Financial Analyst"],
    "Sales": ["Sales Executive", "Account Manager", "Senior Account Manager"],
    "Marketing": ["Marketing Executive", "Content Strategist", "Marketing Lead"],
    "Customer Support": ["Support Associate", "Support Specialist", "Support Lead"],
}
MANAGER_TITLE = {d: f"{d} Manager" for d, _ in DEPARTMENTS}
BASE_SALARY = {0: (35000, 60000), 1: (60000, 100000), 2: (100000, 160000)}  # monthly, by level
SOFT_SKILLS = ["communication", "leadership", "teamwork", "problem solving",
               "time management", "client handling", "mentoring", "adaptability"]

PROJECT_WORDS = ["Phoenix", "Atlas", "Orion", "Nova", "Helix", "Zenith", "Falcon", "Aurora",
                 "Titan", "Vega", "Nimbus", "Quantum", "Apex", "Cobalt", "Echo"]
PROJECT_KINDS = ["Portal", "Analytics Platform", "Mobile App", "Migration", "Automation Suite",
                 "Dashboard", "Chatbot", "Payment Gateway", "CRM Revamp", "Data Lake"]
CLIENTS = ["Internal", "Acme Retail", "Kerala Health Board", "BlueWave Logistics",
           "Sunrise Bank", "EduSpark", "GreenGrid Energy", "MetroMart"]


def write_csv(name, header, rows):
    with open(RAW / name, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"  {name:28s} {len(rows):>6} rows")


def rand_date(start, end):
    return start + timedelta(days=random.randint(0, (end - start).days))


def month_list(n):
    out, y, m = [], TODAY.year, TODAY.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))


# ------------------------------------------------------------------ departments
departments = [{"dept_id": i + 1, "name": n, "location": loc} for i, (n, loc) in enumerate(DEPARTMENTS)]
dept_by_name = {d["name"]: d for d in departments}

skills = [{"skill_id": i + 1, "name": n, "category": c} for i, (n, c) in enumerate(SKILL_LIST)]
skill_id = {s["name"]: s["skill_id"] for s in skills}

# ------------------------------------------------------------------ employees
employees = []
used_emails = set()


def make_person():
    gender = random.choice(["Male", "Female"])
    first = fake.first_name_male() if gender == "Male" else fake.first_name_female()
    last = fake.last_name()
    email = f"{first}.{last}".lower().replace(" ", "")
    while email in used_emails:
        email += str(random.randint(1, 9))
    used_emails.add(email)
    return gender, first, last, email + "@nexora.com"


emp_id = 1000
# one manager per department first
for d in departments:
    emp_id += 1
    g, f, l, e = make_person()
    exp = random.randint(10, 18)
    employees.append(dict(emp_id=emp_id, first_name=f, last_name=l, email=e, gender=g,
                          date_of_birth=rand_date(date(1978, 1, 1), date(1988, 12, 31)),
                          hire_date=rand_date(date(2012, 1, 1), date(2019, 12, 31)),
                          dept_id=d["dept_id"], designation=MANAGER_TITLE[d["name"]], level=3,
                          manager_id="", location=d["location"],
                          employment_type="Full-time", status="Active", experience_years=exp))
    d["head_emp_id"] = emp_id

managers = {d["dept_id"]: d["head_emp_id"] for d in departments}
dept_weights = [30, 18, 12, 8, 8, 10, 7, 7]
while len(employees) < NUM_EMPLOYEES:
    emp_id += 1
    d = random.choices(departments, weights=dept_weights)[0]
    level = random.choices([0, 1, 2], weights=[50, 35, 15])[0]
    exp = {0: random.randint(0, 3), 1: random.randint(3, 7), 2: random.randint(7, 12)}[level]
    g, f, l, e = make_person()
    earliest = max(date(2015, 1, 1), TODAY - timedelta(days=365 * (exp + 1)))
    if random.random() < 0.85:   # most staff joined before the 2025 review cycles
        hire = rand_date(min(earliest, date(2025, 1, 1)), date(2025, 5, 31))
    else:
        hire = rand_date(date(2025, 6, 1), TODAY - timedelta(days=60))
    status = random.choices(["Active", "On Leave", "Resigned"], weights=[90, 4, 6])[0]
    employees.append(dict(emp_id=emp_id, first_name=f, last_name=l, email=e, gender=g,
                          date_of_birth=rand_date(date(1985, 1, 1), date(2003, 12, 31)),
                          hire_date=hire, dept_id=d["dept_id"],
                          designation=DESIGNATIONS[d["name"]][level], level=level,
                          manager_id=managers[d["dept_id"]], location=d["location"],
                          employment_type=random.choices(["Full-time", "Contract", "Intern"], weights=[85, 10, 5])[0],
                          status=status, experience_years=exp))

dept_name_of = {d["dept_id"]: d["name"] for d in departments}
emp_by_id = {e["emp_id"]: e for e in employees}
full = lambda e: f"{e['first_name']} {e['last_name']}"

# ------------------------------------------------------------------ employee skills
emp_skills = {}
rows = []
for e in employees:
    pool = DEPT_SKILLS[dept_name_of[e["dept_id"]]]
    chosen = random.sample(pool, k=min(len(pool), random.randint(3, 6)))
    emp_skills[e["emp_id"]] = chosen
    for s in chosen:
        prof = max(1, min(5, round(random.gauss(2 + e["level"] * 0.8, 1))))
        rows.append([e["emp_id"], skill_id[s], prof, max(1, min(e["experience_years"], random.randint(1, 8)))])
write_csv("departments.csv", ["dept_id", "name", "location", "head_emp_id"],
          [[d["dept_id"], d["name"], d["location"], d["head_emp_id"]] for d in departments])
write_csv("employees.csv", list(employees[0].keys()), [list(e.values()) for e in employees])
write_csv("skills.csv", ["skill_id", "name", "category"], [[s["skill_id"], s["name"], s["category"]] for s in skills])
write_csv("employee_skills.csv", ["emp_id", "skill_id", "proficiency", "years_used"], rows)

# ------------------------------------------------------------------ projects + assignments
projects, assignments = [], []
used_names = set()
tech_depts = ["Engineering", "Data Science", "Quality Assurance"]
for pid in range(1, NUM_PROJECTS + 1):
    while True:
        name = f"{random.choice(PROJECT_WORDS)} {random.choice(PROJECT_KINDS)}"
        if name not in used_names:
            used_names.add(name)
            break
    owner = dept_by_name[random.choices(tech_depts + ["Marketing", "Sales"], weights=[50, 25, 10, 8, 7])[0]]
    start = rand_date(date(2024, 1, 1), date(2026, 6, 30))
    status = random.choices(["Completed", "Ongoing", "On Hold"], weights=[45, 45, 10])[0]
    end = rand_date(start + timedelta(days=90), start + timedelta(days=400)) if status == "Completed" else ""
    if end and end > TODAY:
        end = TODAY - timedelta(days=random.randint(5, 60))
    owner_skills = DEPT_SKILLS[owner["name"]]
    tech = random.sample(owner_skills, k=min(4, len(owner_skills)))
    projects.append(dict(project_id=pid, name=name, client=random.choice(CLIENTS), dept_id=owner["dept_id"],
                         start_date=start, end_date=end, status=status, tech_stack=";".join(tech)))

    # team: mostly from owner dept, 1-2 from other tech depts
    active = [e for e in employees if e["status"] != "Resigned" and e["level"] < 3]
    core = [e for e in active if e["dept_id"] == owner["dept_id"]]
    others = [e for e in active if dept_name_of[e["dept_id"]] in tech_depts and e["dept_id"] != owner["dept_id"]]
    team = random.sample(core, k=min(len(core), random.randint(3, 6))) + random.sample(others, k=random.randint(1, 2))
    lead = max(team, key=lambda x: (x["level"], x["experience_years"]))
    for m in team:
        role = "Project Lead" if m is lead else random.choice(["Developer", "Contributor", "Analyst", "Tester", "Reviewer"])
        assignments.append([m["emp_id"], pid, role, random.choice([25, 50, 75, 100]), start, end])

write_csv("projects.csv", list(projects[0].keys()), [list(p.values()) for p in projects])
write_csv("project_assignments.csv", ["emp_id", "project_id", "role", "allocation_pct", "start_date", "end_date"], assignments)

team_of = {}
for a in assignments:
    team_of.setdefault(a[1], []).append((a[0], a[2]))
projects_of = {}
for a in assignments:
    projects_of.setdefault(a[0], []).append(a[1])

# ------------------------------------------------------------------ attendance (monthly summary)
rows = []
for e in employees:
    for mth in month_list(ATTENDANCE_MONTHS):
        if mth < e["hire_date"].strftime("%Y-%m"):
            continue
        wd = random.randint(20, 23)
        leaves = random.choices([0, 1, 2, 3, 5, 8], weights=[30, 30, 20, 10, 6, 4])[0]
        if e["status"] == "On Leave" and mth >= month_list(2)[0]:
            leaves = wd
        rows.append([e["emp_id"], mth, wd, wd - leaves, leaves, random.choices([0, 1, 2, 4, 7], weights=[45, 25, 15, 10, 5])[0]])
write_csv("attendance.csv", ["emp_id", "month", "working_days", "days_present", "leaves_taken", "late_arrivals"], rows)

# ------------------------------------------------------------------ payroll
rows = []
salary = {}
for e in employees:
    lo, hi = BASE_SALARY.get(e["level"], (170000, 250000))
    gross = round(random.randint(lo, hi), -2)
    salary[e["emp_id"]] = gross
    if e["status"] == "Resigned":
        continue
    basic = round(gross * 0.5)
    hra = round(gross * 0.2)
    allow = gross - basic - hra
    for mth in month_list(PAYROLL_MONTHS):
        ded = round(basic * 0.12) + 200 + random.choice([0, 0, 0, 1500])
        rows.append([e["emp_id"], mth, basic, hra, allow, ded, gross - ded])
write_csv("payroll.csv", ["emp_id", "month", "basic", "hra", "allowances", "deductions", "net_pay"], rows)

# ------------------------------------------------------------------ trainings
trainings = []
for i, s in enumerate(random.sample([x["name"] for x in skills], 18), start=1):
    trainings.append([i, f"{s} Fundamentals" if i % 2 else f"Advanced {s}", skill_id[s],
                      random.choice(["Coursera", "Udemy", "Internal L&D", "NPTEL", "AWS Training"]),
                      random.choice([8, 16, 24, 40])])
write_csv("trainings.csv", ["training_id", "name", "skill_id", "provider", "duration_hours"], trainings)
rows = []
for e in employees:
    for t in random.sample(trainings, k=random.choices([0, 1, 2, 3], weights=[30, 35, 25, 10])[0]):
        rows.append([e["emp_id"], t[0], rand_date(date(2024, 1, 1), TODAY), random.randint(55, 100)])
write_csv("employee_trainings.csv", ["emp_id", "training_id", "completion_date", "score"], rows)

# ------------------------------------------------------------------ performance reviews + review documents
CYCLES = ["2025-H1", "2025-H2"]
reviews, mentorships, review_soft = [], [], []
rating_of = {}
rid = 0
for e in employees:
    if e["level"] == 3:
        continue
    base = random.gauss(3.5, 0.7)
    for cyc in CYCLES:
        if e["hire_date"] > date(2025, 6 if cyc == "2025-H1" else 12, 1):
            continue
        rid += 1
        r = round(max(1, min(5, base + random.gauss(0, 0.3))), 1)
        rating_of[(e["emp_id"], cyc)] = r
        reviews.append([rid, e["emp_id"], e["manager_id"], cyc, r, max(30, min(100, int(r * 20 + random.randint(-10, 10))))])
write_csv("performance_reviews.csv", ["review_id", "emp_id", "reviewer_id", "review_period", "rating", "goals_met_pct"], reviews)

# Review narratives for the latest cycle. They contain facts that are NOT in SQL:
# soft skills, mentoring relationships, and named collaborators -> the graph must extract these.
for e in employees:
    r = rating_of.get((e["emp_id"], "2025-H2"))
    if r is None:
        continue
    mgr = emp_by_id[e["manager_id"]]
    name = full(e)
    soft = random.sample(SOFT_SKILLS, 2)
    for s in soft:
        review_soft.append([e["emp_id"], s])
    tone = "outstanding" if r >= 4.3 else "strong" if r >= 3.7 else "satisfactory" if r >= 3.0 else "below expectations"
    lines = ["PERFORMANCE REVIEW - 2025-H2",
             f"Employee: {name} (ID {e['emp_id']})",
             f"Designation: {e['designation']}, {dept_name_of[e['dept_id']]}",
             f"Reviewer: {full(mgr)}", "",
             f"Overall, {e['first_name']}'s performance this cycle was {tone}."]
    my_projects = projects_of.get(e["emp_id"], [])
    if my_projects:
        p = projects[my_projects[-1] - 1]
        mates = [emp_by_id[x] for x, _ in team_of[p["project_id"]] if x != e["emp_id"]]
        lines.append(f"{e['first_name']} contributed to the {p['name']} project for {p['client']}, "
                     f"working closely with {', '.join(full(m) for m in mates[:2])}.")
        top = emp_skills[e["emp_id"]][0]
        lines.append(f"Their work with {top} on this project was {'highly appreciated' if r >= 3.7 else 'adequate but needs more depth'}.")
    lines.append(f"Key strengths observed: {soft[0]} and {soft[1]}.")
    # mentoring: senior people mentor juniors in same dept (document-only fact)
    if e["level"] >= 1 and random.random() < 0.45:
        juniors = [x for x in employees if x["dept_id"] == e["dept_id"] and x["level"] < e["level"] and x["status"] == "Active"]
        if juniors:
            mentee = random.choice(juniors)
            mentorships.append([e["emp_id"], mentee["emp_id"]])
            lines.append(f"{e['first_name']} has been mentoring {full(mentee)}, who has shown clear improvement as a result.")
    if r < 3.0:
        lines.append("Areas for improvement: meeting deadlines and proactive communication. A performance improvement plan is recommended.")
    elif r < 3.7:
        lines.append("Areas for improvement: deeper technical ownership and documentation.")
    else:
        lines.append("Recommendation: consider for additional responsibilities"
                     + (" and promotion in the next cycle." if r >= 4.3 else "."))
    if random.random() < 0.15:
        lines.append(f"Note: {e['first_name']} has expressed interest in moving to the "
                     f"{random.choice([d['name'] for d in departments if d['dept_id'] != e['dept_id']])} team.")
    (DOCS / "reviews" / f"review_{e['emp_id']}_2025H2.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

with open(TRUTH / "mentorships.csv", "w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerows([["mentor_id", "mentee_id"]] + mentorships)
with open(TRUTH / "soft_skills.csv", "w", newline="", encoding="utf-8") as f:
    csv.writer(f).writerows([["emp_id", "soft_skill"]] + review_soft)

# ------------------------------------------------------------------ project report documents
for p in projects:
    team = team_of[p["project_id"]]
    lead = next(emp_by_id[x] for x, role in team if role == "Project Lead")
    risk = random.choice(["scope creep from late client requirements", "a shortage of senior reviewers",
                          "integration delays with a third-party API", "unstable test environments",
                          "data quality issues in the source systems"])
    outcome = {
        "Completed": f"The project was delivered on {p['end_date']} and the client feedback was "
                     f"{random.choice(['excellent', 'positive', 'mixed'])}.",
        "Ongoing": f"The project is currently about {random.randint(20, 85)}% complete.",
        "On Hold": "The project is currently on hold pending budget approval from the client.",
    }[p["status"]]
    lines = [f"PROJECT REPORT: {p['name']}",
             f"Client: {p['client']} | Owning department: {dept_name_of[p['dept_id']]} | Status: {p['status']}",
             f"Start date: {p['start_date']}", "",
             f"The {p['name']} project is led by {full(lead)}. "
             f"The technology stack includes {', '.join(p['tech_stack'].split(';'))}.",
             "Team members: " + "; ".join(f"{full(emp_by_id[x])} ({role})" for x, role in team) + ".",
             outcome,
             f"The main risk identified was {risk}."]
    star = emp_by_id[random.choice([x for x, _ in team])]
    lines.append(f"Special recognition goes to {full(star)} for going beyond their assigned role.")
    (DOCS / "projects" / f"project_{p['project_id']:03d}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

# ------------------------------------------------------------------ candidates + resumes
rows = []
open_roles = ["Software Engineer", "Data Scientist", "QA Engineer", "HR Executive", "Financial Analyst", "Marketing Executive"]
role_dept = {"Software Engineer": "Engineering", "Data Scientist": "Data Science", "QA Engineer": "Quality Assurance",
             "HR Executive": "Human Resources", "Financial Analyst": "Finance", "Marketing Executive": "Marketing"}
for cid in range(1, NUM_CANDIDATES + 1):
    g, f, l, _ = make_person()
    role = random.choice(open_roles)
    exp = random.randint(0, 9)
    cskills = random.sample(DEPT_SKILLS[role_dept[role]], k=min(len(DEPT_SKILLS[role_dept[role]]), random.randint(3, 5)))
    fname = f"resume_C{cid:03d}.txt"
    edu = random.choice(["B.Tech in Computer Science", "B.Tech in Electronics", "MCA", "MBA (HR)",
                         "B.Com", "M.Sc Data Science", "BBA"])
    college = random.choice(["MITS Kochi", "CUSAT", "NIT Calicut", "Anna University", "VIT Vellore", "Christ University"])
    prev = random.choice(["Infosys", "TCS", "UST Global", "IBS Software", "Wipro", "a Kochi-based startup", "Freshworks"])
    rows.append([cid, f"{f} {l}", f"{f}.{l}".lower() + "@mail.com", role, exp,
                 random.choice(["Applied", "Shortlisted", "Interviewed", "Rejected", "Offered"]), fname])
    resume = [f"{f} {l}".upper(), f"Applying for: {role}", f"Email: {f.lower()}.{l.lower()}@mail.com | {fake.city()}", "",
              "SUMMARY",
              f"{exp} years of experience" + (f", most recently at {prev}." if exp else ", fresher eager to learn."),
              "", "SKILLS", ", ".join(cskills), "", "EDUCATION", f"{edu}, {college}"]
    if exp:
        resume += ["", "EXPERIENCE",
                   f"- {prev}: {exp} years, focused on {cskills[0]} and {cskills[1]}."]
    resume += ["", "ACHIEVEMENTS", f"- {random.choice(['Won a state-level hackathon', 'Published a paper at a national conference', 'Certified in ' + cskills[-1], 'Led a team of 4 in a college project'])}."]
    (DOCS / "resumes" / fname).write_text("\n".join(resume) + "\n", encoding="utf-8")
write_csv("candidates.csv", ["candidate_id", "name", "email", "applied_role", "experience_years", "status", "resume_file"], rows)

# ------------------------------------------------------------------ policy documents (fixed text)
POLICIES = {
    "leave_policy.md": """# Leave Policy
Applies to all full-time employees of Nexora Technologies.

## Annual Leave
Employees are entitled to 18 days of paid annual leave per calendar year, credited at 1.5 days per month.
A maximum of 10 unused days can be carried forward to the next year.

## Sick Leave
Employees receive 10 days of paid sick leave per year. A medical certificate is required for sick leave longer than 2 consecutive days.

## Maternity and Paternity Leave
Female employees are entitled to 26 weeks of paid maternity leave as per the Maternity Benefit Act.
Male employees are entitled to 10 working days of paid paternity leave, to be used within 3 months of the child's birth.

## Leave Without Pay
Leave beyond the available balance is treated as leave without pay and requires approval from the department manager and HR.

## Contract Staff and Interns
Contract employees receive 1 day of paid leave per month. Interns receive 1 day per month and are not eligible for carry forward.
""",
    "work_from_home_policy.md": """# Work From Home Policy
Employees may work from home up to 2 days per week after completing their probation period of 3 months.
Work from home must be approved by the reporting manager at least one day in advance.
Employees on a performance improvement plan are not eligible for work from home until the plan is closed.
Customer Support staff follow a separate shift-based roster and require team lead approval for any remote day.
Employees must be reachable during core hours of 11 AM to 4 PM IST on remote days.
""",
    "performance_appraisal_policy.md": """# Performance Appraisal Policy
Performance is reviewed twice a year, in the H1 (January-June) and H2 (July-December) cycles.
Ratings are given on a scale of 1 to 5.

## Rating Bands
- 4.5 and above: Exceptional - eligible for a 15-20% increment and fast-track promotion.
- 3.5 to 4.4: Exceeds expectations - eligible for an 8-14% increment.
- 3.0 to 3.4: Meets expectations - eligible for a 4-7% increment.
- Below 3.0: Needs improvement - no increment; a Performance Improvement Plan (PIP) of 90 days is initiated.

## Promotion Eligibility
An employee is eligible for promotion if they have an average rating of 4.0 or above across the last two cycles
and have completed at least 18 months in their current designation.
""",
    "code_of_conduct.md": """# Code of Conduct
All employees must treat colleagues, clients and partners with respect and professionalism.
Harassment or discrimination of any kind will lead to disciplinary action up to termination.
Confidential company and client information must not be shared outside the organisation.
Conflicts of interest, including outside employment with a competitor, must be disclosed to HR.
Concerns can be raised confidentially with the HR Business Partner or through the ethics helpline.
""",
    "travel_reimbursement_policy.md": """# Travel and Reimbursement Policy
Business travel must be pre-approved by the department manager.
Employees up to Senior level may book economy air travel or AC 2-tier train travel.
Managers may book business class only for flights longer than 5 hours.
Daily allowance is INR 1500 for metro cities and INR 1000 for other cities.
Claims must be submitted with receipts within 30 days of returning from travel.
""",
    "attendance_policy.md": """# Attendance Policy
Standard working hours are 9:30 AM to 6:30 PM, Monday to Friday.
Arriving after 10:00 AM is marked as a late arrival.
More than 4 late arrivals in a month results in half a day of leave being deducted.
Employees whose attendance falls below 85% in a month will be contacted by HR for a discussion.
""",
}
for fname, text in POLICIES.items():
    (DOCS / "policies" / fname).write_text(text, encoding="utf-8")

print("\nDocuments written:")
for sub in ["policies", "reviews", "projects", "resumes"]:
    print(f"  docs/{sub:10s} {len(list((DOCS / sub).iterdir())):>4} files")
print(f"\nGround truth: {len(mentorships)} mentorships, {len(review_soft)} soft-skill facts")
print("Done.")
