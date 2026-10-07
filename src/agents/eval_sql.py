"""
Step 6 check - EXECUTION ACCURACY of the Text-to-SQL agent (the standard Text-to-SQL metric).

For each question we have a hand-written "gold" SQL query. Both queries are executed and
their RESULTS are compared (not the SQL text, since many different queries are correct):
  - same number of rows, and
  - every column of the gold result appears (same values, any order) somewhere in the
    agent's result. Extra columns from the agent are fine. Numbers match to 1 decimal place.

Also tests the guardrails with dangerous queries.

Run from the project root:  python -m src.agents.eval_sql
"""
from src import llm
from src.agents.sql_agent import ask, execute, validate, UnsafeSQL

GOLD = [
    ("How many active employees are in each department?",
     "SELECT d.name, COUNT(*) FROM employees e JOIN departments d USING (dept_id) WHERE e.status = 'Active' GROUP BY d.name"),
    ("What was the average net pay in each department in September 2026?",
     "SELECT d.name, AVG(p.net_pay) FROM payroll p JOIN employees e USING (emp_id) JOIN departments d USING (dept_id) "
     "WHERE p.month = '2026-09' GROUP BY d.name"),
    ("Which active employees had attendance below 85% in September 2026?",
     "SELECT e.first_name || ' ' || e.last_name FROM attendance a JOIN employees e USING (emp_id) "
     "WHERE a.month = '2026-09' AND e.status = 'Active' AND 100.0 * a.days_present / a.working_days < 85"),
    ("Who are the top 4 rated employees in the 2025-H2 review cycle?",
     "SELECT e.first_name || ' ' || e.last_name, pr.rating FROM performance_reviews pr JOIN employees e USING (emp_id) "
     "WHERE pr.review_period = '2025-H2' ORDER BY pr.rating DESC LIMIT 4"),
    ("How many candidates are shortlisted for each role?",
     "SELECT applied_role, COUNT(*) FROM candidates WHERE status = 'Shortlisted' GROUP BY applied_role"),
    ("Which trainings has Samar Gupta completed and what were the scores?",
     "SELECT t.name, et.score FROM employee_trainings et JOIN trainings t USING (training_id) "
     "JOIN employees e USING (emp_id) WHERE e.first_name = 'Samar' AND e.last_name = 'Gupta'"),
    ("What is Arya Zachariah's average performance rating?",
     "SELECT AVG(pr.rating) FROM performance_reviews pr JOIN employees e USING (emp_id) "
     "WHERE e.first_name = 'Arya' AND e.last_name = 'Zachariah'"),
    ("Which ongoing projects have more than 5 team members, and how many members do they have?",
     "SELECT p.name, COUNT(*) FROM projects p JOIN project_assignments pa USING (project_id) "
     "WHERE p.status = 'Ongoing' GROUP BY p.name HAVING COUNT(*) > 5"),
    ("How many people in Data Science were hired in 2025?",
     "SELECT COUNT(*) FROM employees e JOIN departments d USING (dept_id) "
     "WHERE d.name = 'Data Science' AND e.hire_date >= '2025-01-01' AND e.hire_date < '2026-01-01'"),
    ("How many employees report directly to the head of the Engineering department?",
     "SELECT COUNT(*) FROM employees e JOIN departments d ON d.head_emp_id = e.manager_id WHERE d.name = 'Engineering'"),
    ("Which employee took the most leaves in the last 3 months?",
     "SELECT e.first_name || ' ' || e.last_name, SUM(a.leaves_taken) FROM attendance a JOIN employees e USING (emp_id) "
     "WHERE a.month BETWEEN '2026-07' AND '2026-09' GROUP BY e.emp_id, e.first_name, e.last_name "
     "ORDER BY SUM(a.leaves_taken) DESC LIMIT 1"),
    ("What is the overall attendance percentage for each office location?",
     "SELECT e.location, 100.0 * SUM(a.days_present) / SUM(a.working_days) FROM attendance a "
     "JOIN employees e USING (emp_id) GROUP BY e.location"),
]

UNSAFE = [
    "DELETE FROM employees",
    "SELECT 1; DROP TABLE employees",
    "UPDATE payroll SET net_pay = 0",
    "WITH x AS (DELETE FROM employees RETURNING *) SELECT * FROM x",
]


def norm(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return str(v).strip().lower() if v is not None else None


def same_values(a, b):
    if len(a) != len(b):
        return False
    key = lambda x: (x is None, str(type(x)), x if x is not None else 0)
    for x, y in zip(sorted(a, key=key), sorted(b, key=key)):
        if isinstance(x, float) and isinstance(y, float):
            if abs(x - y) > 0.051:          # allows rounding to 1 decimal place, nothing more
                return False
        elif x != y:
            return False
    return True


def results_match(gold_cols, gold_rows, pred_cols, pred_rows):
    if len(gold_rows) != len(pred_rows):
        return False
    pred_columns = [[norm(r[c]) for r in pred_rows] for c in pred_cols]
    for c in gold_cols:
        g = [norm(r[c]) for r in gold_rows]
        if not any(same_values(g, p) for p in pred_columns):
            return False
    return True


def main():
    print("Guardrail test (these must all be rejected):")
    for q in UNSAFE:
        try:
            validate(q)
            print(f"  NOT BLOCKED!  {q}")
        except UnsafeSQL as e:
            print(f"  blocked: {q[:45]:45s} ({e})")

    print("\nExecution accuracy:")
    correct, repaired = 0, 0
    for i, (question, gold_sql) in enumerate(GOLD, 1):
        g_cols, g_rows, _ = execute(gold_sql)
        r = ask(question)
        ok = r["error"] is None and results_match(g_cols, g_rows, r["columns"], r["rows"])
        correct += ok
        repaired += r["attempts"] > 1 and r["error"] is None
        note = f" (repaired after {r['attempts'] - 1} error)" if r["attempts"] > 1 and r["error"] is None else ""
        print(f"  {i:>2}/{len(GOLD)} {'OK' if ok else 'XX'}  {question}{note}")
        if not ok:
            print(f"        agent SQL: {' '.join((r['sql'] or '').split())}")
            print(f"        agent got {r['row_count']} rows, gold has {len(g_rows)} rows"
                  + (f"; error: {r['error']}" if r["error"] else ""))
    print(f"\nExecution accuracy: {correct}/{len(GOLD)} = {100 * correct / len(GOLD):.0f}%"
          f"   (queries fixed by self-repair: {repaired})")
    print(f"({llm.usage['calls']} LLM calls, {llm.usage['tokens']:,} tokens)")


if __name__ == "__main__":
    main()
