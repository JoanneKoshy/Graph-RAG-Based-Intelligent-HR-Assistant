"""
Step 6 - Database Agent (Text-to-SQL).

ask(question) ->
  1. builds a description of the database automatically (tables, columns, comments, foreign keys,
     and the real values of small categorical columns) so the LLM knows exactly what exists
  2. asks Groq to write ONE PostgreSQL SELECT query (with a few worked examples)
  3. checks the SQL is a single read-only SELECT (guardrail #1)
  4. runs it as the read-only database user in a read-only transaction (guardrails #2 and #3),
     with a row limit and the 10 s timeout set in Step 2
  5. if PostgreSQL returns an error, sends the error back to the LLM to repair the query (max 2 repairs)
Returns a JSON-friendly dict: the "Structured Representation" box of the block diagram.

Try it from the project root:
  python -m src.agents.sql_agent "average net pay per department in September 2026"
"""
import re
import sys
from datetime import date, datetime
from decimal import Decimal

import psycopg

from src import config, llm
from src.db.check_db import QUESTIONS as EXAMPLES

MAX_ROWS = 200
MAX_REPAIRS = 2

SYSTEM_PROMPT = """You write PostgreSQL queries for the HR database of Nexora Technologies.
Return ONE read-only query (SELECT or WITH ... SELECT) that answers the question, plus a one-line explanation.

RULES
- Use only the tables, views and columns listed in the schema below.
- When the result lists people, return their full name in ONE column named employee_name
  (first_name || ' ' || last_name, or employee_name from v_employee_overview).
- Match names and text values case-insensitively (ILIKE) unless the exact value is listed below.
- The dataset's current date is 2026-09-30. Months are text 'YYYY-MM'; the latest month is '2026-09'.
  "last month" = '2026-09', "last 3 months" = '2026-07' to '2026-09'. Review cycles are '2025-H1', '2025-H2'.
- Money is monthly INR. For "current salary" use the latest payroll month.
- Round averages and percentages to 1 decimal place.
- Only use LIMIT when the question asks for a top-N / a fixed number of results.
- Include the columns needed to understand the answer (e.g. name + the value asked for).
- Mentoring, collaboration, soft skills, promotion/PIP recommendations, career interests and project
  risks are NOT in this database. Never guess them from other columns (e.g. a manager is not a mentor).
  If the question is ONLY about such things, return an empty sql string and say so in the explanation.
  If it is partly about them, write a query for the parts that ARE in the database.

DATABASE SCHEMA
{schema}

EXAMPLES
{examples}
"""

SCHEMA_JSON = {
    "type": "object",
    "properties": {"sql": {"type": "string"}, "explanation": {"type": "string"}},
    "required": ["sql", "explanation"],
    "additionalProperties": False,
}

FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|grant|revoke|truncate|copy|call|do|"
                       r"merge|vacuum|reindex|comment|set|reset|lock|listen|notify|execute|prepare)\b", re.I)


class UnsafeSQL(Exception):
    pass


# ---------------------------------------------------------------- schema description (built once)
_schema_text = None


def _readonly_conn():
    conn = psycopg.connect(config.pg_conninfo(readonly=True))
    conn.read_only = True
    return conn


def schema_text():
    global _schema_text
    if _schema_text:
        return _schema_text
    with _readonly_conn() as conn:
        cols = conn.execute("""
            SELECT c.table_name, c.column_name, c.data_type,
                   col_description(format('%I.%I', c.table_schema, c.table_name)::regclass, c.ordinal_position),
                   obj_description(format('%I.%I', c.table_schema, c.table_name)::regclass, 'pg_class')
            FROM information_schema.columns c
            WHERE c.table_schema = 'public'
            ORDER BY c.table_name, c.ordinal_position""").fetchall()
        fks = conn.execute("""
            SELECT conrelid::regclass::text, pg_get_constraintdef(oid)
            FROM pg_constraint WHERE contype = 'f' AND connamespace = 'public'::regnamespace""").fetchall()
        values = {
            "departments.name": "SELECT string_agg(name, ', ' ORDER BY name) FROM departments",
            "employees.location": "SELECT string_agg(DISTINCT location, ', ') FROM employees",
            "employees.designation": "SELECT string_agg(DISTINCT designation, ', ') FROM employees",
            "skills.name": "SELECT string_agg(name, ', ' ORDER BY name) FROM skills",
            "projects.status": "SELECT string_agg(DISTINCT status, ', ') FROM projects",
            "candidates.applied_role": "SELECT string_agg(DISTINCT applied_role, ', ') FROM candidates",
            "candidates.status": "SELECT string_agg(DISTINCT status, ', ') FROM candidates",
            "attendance.month": "SELECT min(month) || ' to ' || max(month) FROM attendance",
            "payroll.month": "SELECT min(month) || ' to ' || max(month) FROM payroll",
        }
        values = {k: conn.execute(q).fetchone()[0] for k, q in values.items()}

    lines, current = [], None
    fk_by_table = {}
    for table, fk in fks:
        fk_by_table.setdefault(table, []).append(fk.replace("FOREIGN KEY ", ""))
    for table, col, typ, ccomment, tcomment in cols:
        if table != current:
            if current in fk_by_table:
                lines += [f"  FK {fk}" for fk in fk_by_table[current]]
            current = table
            lines.append(f"\nTABLE {table}" + (f"  -- {tcomment}" if tcomment else ""))
        lines.append(f"  {col} {typ}" + (f"  -- {ccomment}" if ccomment else ""))
    if current in fk_by_table:
        lines += [f"  FK {fk}" for fk in fk_by_table[current]]
    lines.append("\nKNOWN VALUES")
    lines += [f"  {k}: {v}" for k, v in values.items()]
    _schema_text = "\n".join(lines)
    return _schema_text


def examples_text():
    return "\n\n".join(f"Q: {q}\nSQL: {' '.join(s.split())}" for q, s in EXAMPLES.items())


# ---------------------------------------------------------------- guardrails + execution
def validate(sql):
    s = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    s = re.sub(r"--[^\n]*", " ", s).strip().rstrip(";").strip()
    if ";" in s:
        raise UnsafeSQL("only one statement is allowed")
    if not re.match(r"(?is)^(select|with)\b", s):
        raise UnsafeSQL("query must start with SELECT or WITH")
    no_strings = re.sub(r"'(?:[^']|'')*'", "''", s)        # ignore words inside string literals
    bad = FORBIDDEN.search(no_strings)
    if bad:
        raise UnsafeSQL(f"forbidden keyword: {bad.group(0).upper()}")
    return s


def to_json(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


def execute(sql):
    """Run a validated query read-only, capped at MAX_ROWS rows."""
    with _readonly_conn() as conn:
        cur = conn.execute(f"SELECT * FROM ({sql}) AS q LIMIT {MAX_ROWS + 1}")
        cols = [c.name for c in cur.description]
        rows = [{c: to_json(v) for c, v in zip(cols, r)} for r in cur.fetchall()]
    return cols, rows[:MAX_ROWS], len(rows) > MAX_ROWS


# ---------------------------------------------------------------- the agent
def ask(question, hints=None):
    """hints: optional facts from query understanding, e.g. ["'Arya Zacharia' is employee Arya Zachariah (emp_id 1107)"]"""
    system = SYSTEM_PROMPT.format(schema=schema_text(), examples=examples_text())
    user = f"Question: {question}"
    if hints:
        user += "\nResolved entities:\n" + "\n".join(f"- {h}" for h in hints)
    result = {"question": question, "sql": None, "explanation": "", "columns": [], "rows": [],
              "row_count": 0, "truncated": False, "attempts": 0, "error": None}
    feedback = ""
    for attempt in range(1, MAX_REPAIRS + 2):
        result["attempts"] = attempt
        out = llm.chat_json(system, user + feedback, SCHEMA_JSON, schema_name="sql_query", max_tokens=2000)
        result["sql"], result["explanation"] = out["sql"].strip(), out["explanation"]
        if not result["sql"]:
            result["error"] = "Not answerable from the SQL database: " + result["explanation"]
            return result
        try:
            sql = validate(result["sql"])
            cols, rows, truncated = execute(sql)
            result.update(columns=cols, rows=rows, row_count=len(rows), truncated=truncated, error=None)
            return result
        except UnsafeSQL as e:
            result["error"] = f"Rejected by guardrail: {e}"
        except psycopg.Error as e:
            result["error"] = str(e).strip().splitlines()[0]
        feedback = (f"\n\nYour previous query failed.\nQuery: {result['sql']}\nError: {result['error']}\n"
                    f"Write a corrected query.")
    return result


def show(r):
    print(f"\nQ: {r['question']}")
    print(f"SQL ({r['attempts']} attempt{'s' if r['attempts'] > 1 else ''}):\n  {' '.join((r['sql'] or '').split())}")
    print(f"Why: {r['explanation']}")
    if r["error"]:
        print(f"ERROR: {r['error']}")
        return
    print(f"{r['row_count']} row(s){' (truncated)' if r['truncated'] else ''}:")
    for row in r["rows"][:15]:
        print("  " + " | ".join(f"{k}={v}" for k, v in row.items()))
    if r["row_count"] > 15:
        print(f"  ... {r['row_count'] - 15} more")


if __name__ == "__main__":
    show(ask(" ".join(sys.argv[1:]) or "What was the average net pay per department in September 2026?"))
