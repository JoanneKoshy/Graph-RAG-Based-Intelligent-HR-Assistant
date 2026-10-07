"""
Step 7b - Graph query agent (Text-to-Cypher).

Like the SQL agent, but for the knowledge graph. It answers relationship and multi-hop
questions precisely ("which Data Science employees rated above 4 mentor someone?").
  1. describes the graph automatically (node labels, properties, relationship patterns,
     and the real values of small node types such as outcomes, soft skills and risks)
  2. Groq writes ONE read-only Cypher query (hints from entity linking / concept search
     tell it the exact node names to use)
  3. guardrails: keyword check + the query runs in READ mode, so the database itself
     refuses any write
  4. self-repair: Neo4j errors are sent back to the LLM (max 2 repairs)

Try it from the project root:
  python -m src.agents.cypher_agent "who mentors people in the Data Science team?"
"""
import re
import sys

from neo4j.exceptions import Neo4jError

from src import llm
from src.graph.check_graph import DEMOS
from src.graph.neo4j_client import run, run_read

MAX_ROWS = 100
MAX_REPAIRS = 2
HIDDEN_LABELS = ["Document", "Chunk", "Concept"]          # handled by vector search, not by Cypher
HIDDEN_PROPS = {"embedding", "text", "extracted", "source_docs"}

SYSTEM_PROMPT = """You write Neo4j Cypher queries over the HR knowledge graph of Nexora Technologies.
Return ONE read-only query that answers the question, plus a one-line explanation.

RULES
- Use only the node labels, relationship types, directions and properties listed below.
- Return readable PROPERTIES (e.g. e.name AS employee, p.name AS project), never whole nodes or paths.
- Name matching: use the exact names given in the hints when available; otherwise match
  case-insensitively, e.g. WHERE toLower(n.name) CONTAINS toLower('python').
- Employee.latest_rating is the latest performance rating (1-5); Employee.attendance_pct is overall attendance %.
- COLLABORATED_WITH has no meaningful direction: match it as (a)-[:COLLABORATED_WITH]-(b).
- For "how is X connected to Y" questions use shortestPath over people/project relationships only
  (REPORTS_TO, WORKED_ON, COLLABORATED_WITH, MENTORS, WORKS_IN, HEADED_BY, LED, CONTRIBUTED_TO),
  never through hub nodes like Outcome, SoftSkill, Skill or Client.
- Use DISTINCT to avoid duplicate rows. Use ORDER BY for rankings. Add LIMIT only for top-N questions.
- Never write data: no CREATE, MERGE, SET, DELETE, REMOVE, CALL or LOAD.

GRAPH SCHEMA
{schema}

EXAMPLES
{examples}
"""

SCHEMA_JSON = {
    "type": "object",
    "properties": {"cypher": {"type": "string"}, "explanation": {"type": "string"}},
    "required": ["cypher", "explanation"],
    "additionalProperties": False,
}

FORBIDDEN = re.compile(r"\b(create|merge|set|delete|detach|remove|drop|load|foreach|call|apoc|dbms|"
                       r"grant|revoke|deny|alter|rename|start|stop|terminate)\b", re.I)


class UnsafeCypher(Exception):
    pass


_schema_text = None


def schema_text():
    global _schema_text
    if _schema_text:
        return _schema_text
    lines = ["NODES (label: properties)"]
    labels = [r["label"] for r in run("CALL db.labels() YIELD label RETURN label ORDER BY label")]
    for label in labels:
        if label in HIDDEN_LABELS:
            continue
        keys = run(f"MATCH (n:`{label}`) WITH n LIMIT 25 UNWIND keys(n) AS k RETURN DISTINCT k ORDER BY k")
        keys = [r["k"] for r in keys if r["k"] not in HIDDEN_PROPS]
        lines.append(f"  {label}: {', '.join(keys)}")

    lines.append("\nRELATIONSHIPS (pattern [count] {properties})")
    pats = run("""MATCH (a)-[r]->(b)
                  WHERE NONE(l IN labels(a) WHERE l IN $hidden) AND NONE(l IN labels(b) WHERE l IN $hidden)
                  WITH labels(a)[0] AS la, type(r) AS t, labels(b)[0] AS lb, keys(r) AS rk
                  WITH la, t, lb, count(*) AS n, collect(DISTINCT rk) AS ks
                  RETURN la AS a, t, lb AS b, n, reduce(acc = [], k IN ks | acc + [x IN k WHERE NOT x IN acc]) AS props
                  ORDER BY t""", hidden=HIDDEN_LABELS)
    for p in pats:
        props = [k for k in p["props"] if k not in HIDDEN_PROPS]
        lines.append(f"  (:{p['a']})-[:{p['t']}]->(:{p['b']}) [{p['n']}]" + (f" {{{', '.join(props)}}}" if props else ""))

    lines.append("\nKNOWN VALUES")
    for label in ["Outcome", "SoftSkill", "Risk", "Department", "Client", "Skill"]:
        names = [r["n"] for r in run(f"MATCH (x:{label}) RETURN x.name AS n ORDER BY n")]
        lines.append(f"  {label}.name: " + ", ".join(names))
    lines.append("  Project.status: Completed, Ongoing, On Hold")
    lines.append("  Employee.status: Active, On Leave, Resigned")
    _schema_text = "\n".join(lines)
    return _schema_text


def examples_text():
    picked = list(DEMOS.items())[:3]
    return "\n\n".join(f"Q: {q.split(' (')[0]}\nCypher: {' '.join(c.split())}" for q, c in picked)


def validate(cypher):
    q = re.sub(r"//[^\n]*", " ", cypher).strip().rstrip(";").strip()
    no_strings = re.sub(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", "''", q)
    if ";" in no_strings:
        raise UnsafeCypher("only one statement is allowed")
    if not re.search(r"\bRETURN\b", no_strings, re.I):
        raise UnsafeCypher("query must RETURN something")
    bad = FORBIDDEN.search(no_strings)
    if bad:
        raise UnsafeCypher(f"forbidden keyword: {bad.group(0).upper()}")
    if not re.search(r"\bLIMIT\s+\d+\s*$", no_strings, re.I):
        q += f" LIMIT {MAX_ROWS}"
    return q


def strip_hidden(v):
    if isinstance(v, dict):
        return {k: strip_hidden(x) for k, x in v.items() if k not in HIDDEN_PROPS}
    if isinstance(v, list):
        return [strip_hidden(x) for x in v]
    return v


def ask(question, hints=None):
    system = SYSTEM_PROMPT.format(schema=schema_text(), examples=examples_text())
    user = f"Question: {question}"
    if hints:
        user += "\nHints (exact graph values to use):\n" + "\n".join(f"- {h}" for h in hints)
    result = {"question": question, "cypher": None, "explanation": "", "rows": [], "row_count": 0,
              "attempts": 0, "error": None}
    feedback = ""
    for attempt in range(1, MAX_REPAIRS + 2):
        result["attempts"] = attempt
        out = llm.chat_json(system, user + feedback, SCHEMA_JSON, schema_name="cypher_query", max_tokens=2000)
        result["cypher"], result["explanation"] = out["cypher"].strip(), out["explanation"]
        try:
            rows = run_read(validate(result["cypher"]))
            rows = [strip_hidden(r) for r in rows][:MAX_ROWS]
            result.update(rows=rows, row_count=len(rows), error=None)
            return result
        except UnsafeCypher as e:
            result["error"] = f"Rejected by guardrail: {e}"
        except Neo4jError as e:
            result["error"] = (e.message or str(e)).strip().splitlines()[0][:300]
        feedback = (f"\n\nYour previous query failed.\nQuery: {result['cypher']}\nError: {result['error']}\n"
                    f"Write a corrected query.")
    return result


def show(r):
    print(f"\nQ: {r['question']}")
    print(f"Cypher ({r['attempts']} attempt{'s' if r['attempts'] > 1 else ''}):\n  {' '.join((r['cypher'] or '').split())}")
    print(f"Why: {r['explanation']}")
    if r["error"]:
        print(f"ERROR: {r['error']}")
        return
    print(f"{r['row_count']} row(s):")
    for row in r["rows"][:15]:
        print("  " + " | ".join(f"{k}={v}" for k, v in row.items()))
    if r["row_count"] > 15:
        print(f"  ... {r['row_count'] - 15} more")


if __name__ == "__main__":
    show(ask(" ".join(sys.argv[1:]) or "Who mentors people in the Data Science team, and what are the mentees' ratings?"))
