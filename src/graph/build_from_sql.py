"""
Step 3a - Build the structured part of the knowledge graph from PostgreSQL.

Reads from Neon (read-only user) and writes nodes + relationships into Neo4j.
Safe to re-run: it clears the graph first.
Run from the project root:  python -m src.graph.build_from_sql
"""
import psycopg
from psycopg.rows import dict_row

from src import config
from src.graph.neo4j_client import run, clean_rows, close

CONSTRAINTS = [
    ("Employee", "emp_id"), ("Department", "dept_id"), ("Skill", "name"),
    ("Project", "project_id"), ("Client", "name"), ("Training", "training_id"),
    ("Candidate", "candidate_id"), ("Document", "doc_id"), ("SoftSkill", "name"),
    ("Outcome", "name"), ("Company", "name"), ("Institution", "name"), ("Risk", "name"),
]


def fetch(cur, query):
    return clean_rows(cur.execute(query).fetchall())


def main():
    print("Clearing existing graph ...")
    run("MATCH (n) DETACH DELETE n")
    for label, prop in CONSTRAINTS:
        run(f"CREATE CONSTRAINT {label.lower()}_{prop} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE")
    print(f"  {len(CONSTRAINTS)} uniqueness constraints ready")

    with psycopg.connect(config.pg_conninfo(readonly=True), row_factory=dict_row) as conn:
        cur = conn.cursor()

        # ------------------------------------------------------------ nodes
        rows = fetch(cur, "SELECT dept_id, name, location FROM departments")
        run("UNWIND $rows AS r MERGE (d:Department {dept_id: r.dept_id}) SET d.name = r.name, d.location = r.location", rows=rows)
        print(f"  Department  {len(rows)}")

        rows = fetch(cur, """
            SELECT o.emp_id, e.first_name, e.last_name, o.employee_name AS name, e.email, e.designation,
                   e.level, e.status, e.location, e.experience_years, e.hire_date, e.employment_type,
                   o.latest_rating, o.attendance_pct
            FROM employees e JOIN v_employee_overview o ON o.emp_id = e.emp_id""")
        run("""UNWIND $rows AS r MERGE (e:Employee {emp_id: r.emp_id})
               SET e += r""", rows=rows)
        print(f"  Employee    {len(rows)}")

        rows = fetch(cur, "SELECT name, category FROM skills")
        run("UNWIND $rows AS r MERGE (s:Skill {name: r.name}) SET s.category = r.category", rows=rows)
        print(f"  Skill       {len(rows)}")

        rows = fetch(cur, "SELECT project_id, name, client, dept_id, start_date, end_date, status, tech_stack FROM projects")
        run("""UNWIND $rows AS r
               MERGE (p:Project {project_id: r.project_id})
               SET p.name = r.name, p.status = r.status, p.start_date = r.start_date, p.end_date = r.end_date
               MERGE (c:Client {name: r.client})
               MERGE (p)-[:FOR_CLIENT]->(c)
               WITH p, r
               MATCH (d:Department {dept_id: r.dept_id})
               MERGE (p)-[:OWNED_BY]->(d)
               WITH p, r
               UNWIND split(r.tech_stack, ';') AS tech
               MATCH (s:Skill {name: tech})
               MERGE (p)-[:USES]->(s)""", rows=rows)
        print(f"  Project     {len(rows)}  (+ Client, OWNED_BY, USES)")

        rows = fetch(cur, """SELECT t.training_id, t.name, t.provider, t.duration_hours, s.name AS skill
                             FROM trainings t JOIN skills s ON s.skill_id = t.skill_id""")
        run("""UNWIND $rows AS r
               MERGE (t:Training {training_id: r.training_id})
               SET t.name = r.name, t.provider = r.provider, t.duration_hours = r.duration_hours
               WITH t, r MATCH (s:Skill {name: r.skill})
               MERGE (t)-[:TEACHES]->(s)""", rows=rows)
        print(f"  Training    {len(rows)}")

        rows = fetch(cur, "SELECT candidate_id, name, email, applied_role, experience_years, status, resume_file FROM candidates")
        run("UNWIND $rows AS r MERGE (c:Candidate {candidate_id: r.candidate_id}) SET c += r", rows=rows)
        print(f"  Candidate   {len(rows)}")

        # ------------------------------------------------------------ relationships
        rows = fetch(cur, "SELECT emp_id, dept_id, manager_id FROM employees")
        run("""UNWIND $rows AS r MATCH (e:Employee {emp_id: r.emp_id}), (d:Department {dept_id: r.dept_id})
               MERGE (e)-[:WORKS_IN]->(d)""", rows=rows)
        run("""UNWIND $rows AS r WITH r WHERE r.manager_id IS NOT NULL
               MATCH (e:Employee {emp_id: r.emp_id}), (m:Employee {emp_id: r.manager_id})
               MERGE (e)-[:REPORTS_TO]->(m)""", rows=rows)

        rows = fetch(cur, "SELECT dept_id, head_emp_id FROM departments")
        run("""UNWIND $rows AS r MATCH (d:Department {dept_id: r.dept_id}), (e:Employee {emp_id: r.head_emp_id})
               MERGE (d)-[:HEADED_BY]->(e)""", rows=rows)

        rows = fetch(cur, """SELECT es.emp_id, s.name AS skill, es.proficiency, es.years_used
                             FROM employee_skills es JOIN skills s ON s.skill_id = es.skill_id""")
        run("""UNWIND $rows AS r MATCH (e:Employee {emp_id: r.emp_id}), (s:Skill {name: r.skill})
               MERGE (e)-[h:HAS_SKILL]->(s) SET h.proficiency = r.proficiency, h.years_used = r.years_used""", rows=rows)

        rows = fetch(cur, "SELECT emp_id, project_id, role, allocation_pct FROM project_assignments")
        run("""UNWIND $rows AS r MATCH (e:Employee {emp_id: r.emp_id}), (p:Project {project_id: r.project_id})
               MERGE (e)-[w:WORKED_ON]->(p) SET w.role = r.role, w.allocation_pct = r.allocation_pct""", rows=rows)

        rows = fetch(cur, "SELECT emp_id, training_id, completion_date, score FROM employee_trainings")
        run("""UNWIND $rows AS r MATCH (e:Employee {emp_id: r.emp_id}), (t:Training {training_id: r.training_id})
               MERGE (e)-[c:COMPLETED]->(t) SET c.completion_date = r.completion_date, c.score = r.score""", rows=rows)

    # ------------------------------------------------------------ summary
    print("\nGraph after Step 3a:")
    for r in run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY n DESC"):
        print(f"  (:{r['label']:12s}) {r['n']:>5}")
    for r in run("MATCH ()-[x]->() RETURN type(x) AS type, count(*) AS n ORDER BY n DESC"):
        print(f"  [:{r['type']:12s}] {r['n']:>5}")
    close()
    print("\nNext:  python -m src.graph.extract_from_docs")


if __name__ == "__main__":
    main()
