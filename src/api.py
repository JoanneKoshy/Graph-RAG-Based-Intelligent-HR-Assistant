"""
Step 9 - REST API for the React frontend (FastAPI).

The React app (frontend/) calls these endpoints; this file calls the backend we built in Steps 2-8.
Everything here is READ-ONLY: SQL runs as the read-only database user, Cypher runs in READ mode.

Run from the project root:
  uvicorn src.api:app --reload --reload-dir src --port 8000
Check it works: open http://localhost:8000/api/health  (or http://localhost:8000/docs for all endpoints)
"""
import json
import re
import time

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src import llm, pipeline
from src.agents import sql_agent
from src.agents.query_understanding import LUCENE_SPECIAL
from src.graph.neo4j_client import run_read

app = FastAPI(title="Nexora HR Assistant API")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------- helpers
@app.exception_handler(Exception)
async def on_error(request, exc):
    """Send errors to the frontend as readable JSON instead of crashing."""
    status = 429 if isinstance(exc, llm.DailyLimitReached) else 500
    return JSONResponse(status_code=status, content={"detail": f"{type(exc).__name__}: {str(exc)[:300]}"})


_cache = {}


def cached(key, fn, ttl=600):
    hit = _cache.get(key)
    if hit and time.time() - hit[0] < ttl:
        return hit[1]
    value = fn()
    _cache[key] = (time.time(), value)
    return value


def plain(obj):
    """Make any result JSON-safe (Neo4j dates, Decimals ...)."""
    return json.loads(json.dumps(obj, default=str))


def sql(query, params=None):
    """Read-only SQL -> list of dicts."""
    with sql_agent._readonly_conn() as conn:
        cur = conn.execute(query, params)
        cols = [c.name for c in cur.description]
        return [{c: sql_agent.to_json(v) for c, v in zip(cols, r)} for r in cur.fetchall()]


def sql_one(query, params=None):
    rows = sql(query, params)
    return next(iter(rows[0].values())) if rows else None


def graph(query, **params):
    return plain(run_read(query, **params))


FACT_RE = re.compile(r"^(.+?) ([A-Z][A-Z_]+) (.+?)(?: \((.*)\))?$")


def facts_to_graph(facts):
    """'Arya Zachariah MENTORS Rahul Nair (since: 2024)' -> nodes + edges for the graph drawing."""
    nodes, edges = {}, []
    for f in facts:
        m = FACT_RE.match(f["fact"])
        if m:
            a, rel, b = m.group(1), m.group(2), m.group(3)
            for name in (a, b):
                nodes.setdefault(name, {"id": name, "name": name, "label": "Fact"})
            edges.append({"source": a, "target": b, "rel": rel, "extracted": f.get("source") == "doc"})
    return {"nodes": list(nodes.values()), "edges": edges}


NEIGHBOURS = """
MATCH (a) WHERE elementId(a) = $id
MATCH (a)-[r]-(b)
WHERE NOT b:Chunk AND NOT b:Document AND NOT b:Concept
RETURN elementId(a) AS a_id, labels(a)[0] AS a_label, coalesce(a.name, a.title, '') AS a_name,
       elementId(b) AS b_id, labels(b)[0] AS b_label, coalesce(b.name, b.title, '') AS b_name,
       type(r) AS rel, startNode(r) = a AS outgoing, coalesce(r.extracted, false) AS extracted
ORDER BY extracted DESC, rel
LIMIT $limit
"""


def neighbourhood(element_id, limit=60):
    rows = graph(NEIGHBOURS, id=element_id, limit=limit)
    nodes, edges, table = {}, [], []
    for r in rows:
        nodes[r["a_id"]] = {"id": r["a_id"], "name": r["a_name"], "label": r["a_label"]}
        nodes[r["b_id"]] = {"id": r["b_id"], "name": r["b_name"], "label": r["b_label"]}
        src, dst = (r["a_id"], r["b_id"]) if r["outgoing"] else (r["b_id"], r["a_id"])
        edges.append({"source": src, "target": dst, "rel": r["rel"], "extracted": r["extracted"]})
        table.append({"from": nodes[src]["name"], "relationship": r["rel"], "to": nodes[dst]["name"],
                      "source": "document" if r["extracted"] else "database"})
    return {"center": element_id, "nodes": list(nodes.values()), "edges": edges, "table": table}


# ---------------------------------------------------------------- chat
class AskBody(BaseModel):
    question: str


@app.get("/api/health")
def health():
    return {"ok": True}


@app.get("/api/demo-questions")
def demo_questions():
    return pipeline.DEMO


@app.post("/api/ask")
def ask(body: AskBody):
    r = pipeline.answer(body.question.strip(), verbose=True)
    g = r.get("context", {}).get("graph")
    r["fact_graph"] = facts_to_graph(g["related_facts"]) if g else None
    r["usage"] = dict(llm.usage)
    return plain(r)


# ---------------------------------------------------------------- dashboard (no LLM)
LATEST_CYCLE = "(SELECT max(review_period) FROM performance_reviews)"
LATEST_MONTH = "(SELECT max(month) FROM attendance)"


def _dashboard():
    return {
        "kpis": {
            "active_employees": sql_one("SELECT count(*) FROM employees WHERE status = 'Active'"),
            "departments": sql_one("SELECT count(*) FROM departments"),
            "ongoing_projects": sql_one("SELECT count(*) FROM projects WHERE status = 'Ongoing'"),
            "avg_rating": sql_one(f"SELECT round(avg(rating), 2) FROM performance_reviews "
                                  f"WHERE review_period = {LATEST_CYCLE}"),
            "open_candidates": sql_one("SELECT count(*) FROM candidates WHERE status NOT IN ('Rejected', 'Offered')"),
        },
        "headcount": sql("""SELECT d.name AS department, count(*) AS employees
                            FROM employees e JOIN departments d ON d.dept_id = e.dept_id
                            WHERE e.status = 'Active' GROUP BY d.name ORDER BY employees DESC"""),
        "ratings": sql(f"""SELECT d.name AS department, round(avg(pr.rating), 2) AS avg_rating
                           FROM performance_reviews pr
                           JOIN employees e ON e.emp_id = pr.emp_id JOIN departments d ON d.dept_id = e.dept_id
                           WHERE pr.review_period = {LATEST_CYCLE}
                           GROUP BY d.name ORDER BY avg_rating DESC"""),
        "payroll": sql("""SELECT month, round(sum(net_pay) / 100000.0, 1) AS payroll_lakh
                          FROM payroll GROUP BY month ORDER BY month"""),
        "attendance": sql("""SELECT month, round(100.0 * sum(days_present) / sum(working_days), 1) AS attendance_pct
                             FROM attendance GROUP BY month ORDER BY month"""),
        "candidates": sql("SELECT status, count(*) AS candidates FROM candidates GROUP BY status ORDER BY 2 DESC"),
        "projects": sql("SELECT status, count(*) AS projects FROM projects GROUP BY status ORDER BY 2 DESC"),
        "watch": sql(f"""
            WITH recent AS (
                SELECT emp_id, round(100.0 * sum(days_present) / sum(working_days), 1) AS attendance_3m
                FROM attendance
                WHERE month > to_char(to_date({LATEST_MONTH}, 'YYYY-MM') - interval '3 months', 'YYYY-MM')
                GROUP BY emp_id)
            SELECT o.emp_id, o.employee_name, o.department, o.designation, o.manager_name,
                   o.latest_rating, r.attendance_3m
            FROM v_employee_overview o LEFT JOIN recent r ON r.emp_id = o.emp_id
            WHERE o.status = 'Active' AND (o.latest_rating < 2.5 OR r.attendance_3m < 85)
            ORDER BY o.latest_rating NULLS LAST, r.attendance_3m"""),
    }


@app.get("/api/dashboard")
def dashboard():
    return cached("dashboard", _dashboard)


# ---------------------------------------------------------------- employees
GRAPH_INSIGHTS = """
MATCH (e:Employee {emp_id: $id})-[r]-(b)
WHERE r.extracted
RETURN type(r) AS relation, startNode(r) = e AS outgoing, coalesce(b.name, b.title, '') AS name
ORDER BY relation, name
"""

READABLE = {
    ("MENTORS", True): "Mentors", ("MENTORS", False): "Mentored by",
    ("COLLABORATED_WITH", True): "Collaborated with", ("COLLABORATED_WITH", False): "Collaborated with",
    ("LED", True): "Led project", ("CONTRIBUTED_TO", True): "Contributed to",
    ("RECOGNIZED_ON", True): "Recognised on", ("HAS_SOFT_SKILL", True): "Soft skills",
    ("USED_SKILL", True): "Used skills", ("RECOMMENDED_FOR", True): "Recommended for",
    ("INTERESTED_IN", True): "Interested in",
}


@app.get("/api/employees")
def employees():
    return cached("employees", lambda: sql("""SELECT emp_id, employee_name, department, designation, status
                                              FROM v_employee_overview ORDER BY employee_name"""))


@app.get("/api/employees/{emp_id}")
def employee(emp_id: int):
    p = {"id": emp_id}
    overview = sql("SELECT * FROM v_employee_overview WHERE emp_id = %(id)s", p)
    if not overview:
        return JSONResponse(status_code=404, content={"detail": f"No employee with id {emp_id}"})
    result = {
        "overview": overview[0],
        "reviews": sql("""SELECT review_period, rating, goals_met_pct FROM performance_reviews
                          WHERE emp_id = %(id)s ORDER BY review_period""", p),
        "skills": sql("""SELECT s.name AS skill, es.proficiency
                         FROM employee_skills es JOIN skills s ON s.skill_id = es.skill_id
                         WHERE es.emp_id = %(id)s ORDER BY es.proficiency DESC, s.name""", p),
        "projects": sql("""SELECT p.name AS project, pa.role, pa.allocation_pct, p.status
                           FROM project_assignments pa JOIN projects p ON p.project_id = pa.project_id
                           WHERE pa.emp_id = %(id)s ORDER BY pa.start_date DESC""", p),
        "insights": [], "graph": None, "graph_error": None,
    }
    try:
        grouped = {}
        for r in graph(GRAPH_INSIGHTS, id=emp_id):
            key = READABLE.get((r["relation"], r["outgoing"]), r["relation"].replace("_", " ").title())
            grouped.setdefault(key, set()).add(r["name"])
        result["insights"] = [{"label": k, "values": sorted(v)} for k, v in grouped.items()]
        node = graph("MATCH (e:Employee {emp_id: $id}) RETURN elementId(e) AS id", id=emp_id)
        if node:
            result["graph"] = neighbourhood(node[0]["id"], limit=50)
    except Exception as e:                    # database part still works if Neo4j is paused
        result["graph_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return result


# ---------------------------------------------------------------- knowledge graph explorer
SEARCH = """
CALL db.index.fulltext.queryNodes('entity_names', $q) YIELD node, score
WHERE NOT node:Chunk AND NOT node:Document AND NOT node:Concept
RETURN elementId(node) AS id, labels(node)[0] AS label, node.name AS name, round(score, 2) AS score
LIMIT 15
"""


@app.get("/api/graph/search")
def graph_search(q: str):
    words = [LUCENE_SPECIAL.sub(r"\\\1", w) for w in q.split() if len(w) > 1]
    if not words:
        return []
    return graph(SEARCH, q=" AND ".join(f"{w}~" if len(w) > 3 else w for w in words))


@app.get("/api/graph/neighbours")
def graph_neighbours(id: str, limit: int = Query(50, ge=5, le=150)):
    return neighbourhood(id, limit)


@app.get("/api/graph/stats")
def graph_stats():
    return cached("graph_stats", lambda: {
        "nodes": graph("""MATCH (n) WHERE NOT n:Chunk AND NOT n:Concept
                          RETURN labels(n)[0] AS type, count(*) AS nodes ORDER BY nodes DESC"""),
        "relationships": graph("""MATCH ()-[r]->()
                                  WHERE NOT type(r) IN ['HAS_CHUNK', 'MENTIONS', 'DESCRIBES']
                                  RETURN type(r) AS relationship, count(*) AS total,
                                         sum(CASE WHEN r.extracted THEN 1 ELSE 0 END) AS from_documents
                                  ORDER BY total DESC"""),
    })
