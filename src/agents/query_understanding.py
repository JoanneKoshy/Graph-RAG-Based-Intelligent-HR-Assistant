"""
Step 5 - Query Understanding LLM + Task Router (first two boxes of the block diagram).

analyze(question) does three things:
  1. UNDERSTAND: rewrites the question clearly and classifies its intent
  2. ROUTE:      decides which sources are needed -> SQL, Graph, Documents (any combination)
                 and, for documents, which document classes (the "Document Router")
  3. LINK:       finds the people / projects / skills mentioned and matches them to real
                 graph nodes using the full-text index (handles typos like "Nakul Lall")

Try it from the project root:
  python -m src.agents.query_understanding "who mentors widisha in data science?"
"""
import re
import sys
from difflib import SequenceMatcher

from src import llm

INTENTS = ["employee_lookup", "workforce_analytics", "performance_insight", "policy_question",
           "candidate_screening", "relationship_query", "out_of_scope"]
DOC_CLASSES = ["policy", "review", "project", "resume"]
ENTITY_TYPES = ["Person", "Department", "Project", "Skill", "SoftSkill", "Client", "Location", "Role", "Other"]

SYSTEM_PROMPT = """You are the query-understanding module of an HR assistant for Nexora Technologies.
Analyse the HR manager's question and decide which data sources are needed to answer it.

DATA SOURCES
1. SQL database (exact numbers and records):
   employees (name, designation, department, manager, location, hire date, status, experience),
   departments, skills with proficiency 1-5, projects and project assignments (role on project),
   monthly attendance (days present, leaves, late arrivals), monthly payroll (salary, deductions),
   trainings completed with scores, performance ratings per cycle (2025-H1, 2025-H2), job candidates and status.
   -> use for counts, averages, totals, rankings, filters on attributes, salaries, attendance, ratings, dates.
2. Knowledge GRAPH (relationships, and facts extracted from documents that are NOT in SQL):
   who MENTORS whom, who COLLABORATED_WITH whom, soft skills (leadership, communication...),
   who is RECOMMENDED_FOR promotion / additional responsibilities / performance improvement plan (PIP),
   who is INTERESTED_IN moving to another department, project risks, project tech stacks,
   candidates' skills from resumes, reporting lines, and multi-hop connections between people/projects/skills.
   -> use for relationship questions, "who worked with", mentoring, soft skills, recommendations, PIP,
      risks, skill matching between candidates and projects, and connections.
3. DOCUMENTS (full text, semantic search):
   policy = HR policies (leave, work from home, appraisal/increments/promotion rules, attendance, travel, conduct)
   review = performance review write-ups, project = project reports, resume = candidate resumes.
   -> use when the answer needs policy rules or the wording/details/summary of a review, report or resume.

RULES
- Choose the SMALLEST set of sources that can fully answer the question. Combine sources when the
  question needs facts of different kinds (e.g. a person's rating from SQL + a policy rule from documents).
- If documents are needed, list the relevant document classes; otherwise leave doc_classes empty.
- Policy-eligibility questions about a specific person (promotion, increment, work from home...) need
  DOCUMENTS for the rule AND SQL for that person's facts (ratings per cycle, time in role, attendance).
- entities: only real names and values (people, departments, projects, skills, clients, locations,
  job titles). Do not list verbs or concepts such as "mentored" or "promotion".
  Write them exactly as in the question (fix obvious spelling in rewritten_question only).
- time_period: a period mentioned in the question (e.g. "2025-H2", "last 3 months"), else "".
- Greetings or questions unrelated to HR data: intent out_of_scope and no sources.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "rewritten_question": {"type": "string"},
        "intent": {"type": "string", "enum": INTENTS},
        "needs_sql": {"type": "boolean"},
        "needs_graph": {"type": "boolean"},
        "needs_documents": {"type": "boolean"},
        "doc_classes": {"type": "array", "items": {"type": "string", "enum": DOC_CLASSES}},
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "type": {"type": "string", "enum": ENTITY_TYPES}},
                "required": ["text", "type"],
                "additionalProperties": False,
            },
        },
        "time_period": {"type": "string"},
        "reasoning": {"type": "string"},
    },
    "required": ["rewritten_question", "intent", "needs_sql", "needs_graph", "needs_documents",
                 "doc_classes", "entities", "time_period", "reasoning"],
    "additionalProperties": False,
}

# which graph labels an entity type can be linked to
LINKABLE = {"Person": ["Employee", "Candidate"], "Department": ["Department"], "Project": ["Project"],
            "Skill": ["Skill"], "SoftSkill": ["SoftSkill"], "Client": ["Client"]}
LUCENE_SPECIAL = re.compile(r'([+\-&|!(){}\[\]^"~*?:\\/])')


def route_of(a):
    parts = [name for name, flag in (("sql", a["needs_sql"]), ("graph", a["needs_graph"]),
                                     ("documents", a["needs_documents"])) if flag]
    return "+".join(parts) or "none"


def link_entity(text, typ):
    """Match an entity mention to a graph node with the full-text index (fuzzy, typo tolerant)."""
    from src.graph.neo4j_client import run
    labels = LINKABLE.get(typ)
    if not labels:
        return None
    words = [LUCENE_SPECIAL.sub(r"\\\1", w) for w in text.split() if len(w) > 1]
    if not words:
        return None
    query = " AND ".join(f"{w}~" if len(w) > 3 else w for w in words)
    rows = run("""CALL db.index.fulltext.queryNodes('entity_names', $q) YIELD node, score
                  WHERE any(l IN labels(node) WHERE l IN $labels)
                  RETURN labels(node)[0] AS label, node.name AS name,
                         coalesce(node.emp_id, node.candidate_id, node.project_id, node.dept_id) AS id
                  LIMIT 3""", q=query, labels=labels)
    for r in rows:   # accept only if the names are genuinely similar
        if SequenceMatcher(None, text.lower(), r["name"].lower()).ratio() >= 0.6 or \
                text.lower() in r["name"].lower():
            return r
    return None


def analyze(question, link=True):
    a = llm.chat_json(SYSTEM_PROMPT, f"Question: {question}", SCHEMA, schema_name="query_analysis", max_tokens=2000)
    if not a["needs_documents"]:
        a["doc_classes"] = []
    a["route"] = route_of(a)
    if link:
        for e in a["entities"]:
            e["match"] = link_entity(e["text"], e["type"])
    return a


def show(question, a):
    print(f"\nQ: {question}")
    print(f"  rewritten : {a['rewritten_question']}")
    print(f"  intent    : {a['intent']}")
    print(f"  route     : {a['route'].upper()}" + (f"   doc classes: {a['doc_classes']}" if a["doc_classes"] else ""))
    if a["time_period"]:
        print(f"  period    : {a['time_period']}")
    for e in a["entities"]:
        m = e.get("match")
        linked = f"-> {m['label']} '{m['name']}' (id {m['id']})" if m else "-> (not linked)"
        print(f"  entity    : {e['text']!r} [{e['type']}] {linked}")
    print(f"  why       : {a['reasoning']}")


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "Whch pythn developers in data sciance are mentored by someone recomended for promotion?"
    show(q, analyze(q))
