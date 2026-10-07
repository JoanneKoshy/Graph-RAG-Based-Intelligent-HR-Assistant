"""
Step 2 - Create the PostgreSQL database, build the schema and load the CSVs.

Safe to re-run: it drops and recreates all tables each time.
Run from the project root:  python -m src.db.setup_db
"""
import psycopg
from psycopg import sql

from src import config

# Load order matters because of foreign keys
TABLES = ["departments", "employees", "skills", "employee_skills", "projects",
          "project_assignments", "attendance", "payroll", "trainings",
          "employee_trainings", "performance_reviews", "candidates"]


def create_database():
    # If the database already exists (e.g. Neon's default "neondb"), just use it
    try:
        with psycopg.connect(config.pg_conninfo()):
            print(f"Database '{config.PG_DB}' found")
            return
    except psycopg.OperationalError as e:
        if "does not exist" not in str(e):
            raise
    with psycopg.connect(config.pg_conninfo(db="postgres"), autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(config.PG_DB)))
        print(f"Created database '{config.PG_DB}'")


def load_schema_and_data():
    schema = (config.ROOT / "src" / "db" / "schema.sql").read_text(encoding="utf-8")
    with psycopg.connect(config.pg_conninfo()) as conn:
        conn.execute(schema)
        print("Schema created")

        with conn.cursor() as cur:
            for t in TABLES:
                path = config.DATA_RAW / f"{t}.csv"
                with open(path, encoding="utf-8") as f:
                    header = f.readline().strip()
                    cols = sql.SQL(", ").join(sql.Identifier(c) for c in header.split(","))
                    copy_sql = sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv)").format(sql.Identifier(t), cols)
                    with cur.copy(copy_sql) as copy:
                        copy.write(f.read())
                n = cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(t))).fetchone()[0]
                print(f"  loaded {t:22s} {n:>6} rows")

        # circular FK: departments.head_emp_id -> employees
        conn.execute("ALTER TABLE departments ADD CONSTRAINT fk_dept_head "
                     "FOREIGN KEY (head_emp_id) REFERENCES employees(emp_id)")
    print("Data loaded")


def create_readonly_user():
    """The LLM-generated SQL will run as this user, so it can never modify or delete data."""
    u, p, db = config.PG_READONLY_USER, config.PG_READONLY_PASSWORD, config.PG_DB
    with psycopg.connect(config.pg_conninfo(), autocommit=True) as conn:
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (u,)).fetchone():
            conn.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(sql.Identifier(u), sql.Literal(p)))
        else:
            conn.execute(sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {}").format(sql.Identifier(u), sql.Literal(p)))
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(db), sql.Identifier(u)))
        conn.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(u)))
        conn.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(u)))
        conn.execute(sql.SQL("ALTER ROLE {} SET statement_timeout = '10s'").format(sql.Identifier(u)))
    print(f"Read-only user '{u}' ready (SELECT only, 10s query timeout)")


if __name__ == "__main__":
    create_database()
    load_schema_and_data()
    create_readonly_user()
    print("\nStep 2 complete. Now run:  python -m src.db.check_db")
