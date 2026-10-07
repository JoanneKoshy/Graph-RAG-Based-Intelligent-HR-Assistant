"""
Step 2 check - run real HR questions as SQL using the READ-ONLY user.
These question/SQL pairs are also the first examples for the Text-to-SQL agent later.

Run from the project root:  python -m src.db.check_db
"""
import psycopg

from src import config

QUESTIONS = {
    "How many active employees are in each department?": """
        SELECT d.name AS department, COUNT(*) AS active_employees
        FROM employees e JOIN departments d ON d.dept_id = e.dept_id
        WHERE e.status = 'Active'
        GROUP BY d.name ORDER BY active_employees DESC""",

    "Who are the top 5 rated employees in the 2025-H2 cycle?": """
        SELECT o.employee_name, o.designation, o.department, pr.rating
        FROM performance_reviews pr JOIN v_employee_overview o ON o.emp_id = pr.emp_id
        WHERE pr.review_period = '2025-H2'
        ORDER BY pr.rating DESC, o.employee_name LIMIT 5""",

    "Which employees know Python at proficiency 4 or above?": """
        SELECT e.first_name || ' ' || e.last_name AS employee, e.designation, es.proficiency
        FROM employee_skills es
        JOIN skills s ON s.skill_id = es.skill_id
        JOIN employees e ON e.emp_id = es.emp_id
        WHERE s.name = 'Python' AND es.proficiency >= 4
        ORDER BY es.proficiency DESC, employee""",

    "Which employees had attendance below 85% in the last 3 months?": """
        SELECT o.employee_name, o.department,
               ROUND(100.0 * SUM(a.days_present) / SUM(a.working_days), 1) AS attendance_pct
        FROM attendance a JOIN v_employee_overview o ON o.emp_id = a.emp_id
        WHERE a.month >= '2026-07' AND o.status = 'Active'
        GROUP BY o.employee_name, o.department
        HAVING 100.0 * SUM(a.days_present) / SUM(a.working_days) < 85
        ORDER BY attendance_pct LIMIT 10""",
}


def show(cur, title, query):
    print(f"\nQ: {title}")
    rows = cur.execute(query).fetchall()
    cols = [c.name for c in cur.description]
    widths = [max(len(str(c)), *(len(str(r[i])) for r in rows)) if rows else len(c) for i, c in enumerate(cols)]
    print("  " + " | ".join(str(c).ljust(w) for c, w in zip(cols, widths)))
    print("  " + "-+-".join("-" * w for w in widths))
    for r in rows:
        print("  " + " | ".join(str(v).ljust(w) for v, w in zip(r, widths)))


if __name__ == "__main__":
    with psycopg.connect(config.pg_conninfo(readonly=True)) as conn:
        cur = conn.cursor()
        for q, s in QUESTIONS.items():
            show(cur, q, s)

        print("\nSafety test: read-only user tries to DELETE ...")
        try:
            cur.execute("DELETE FROM employees")
            print("  WARNING: delete was allowed!")
        except psycopg.errors.InsufficientPrivilege:
            print("  Blocked as expected (permission denied). The LLM cannot damage the data.")
