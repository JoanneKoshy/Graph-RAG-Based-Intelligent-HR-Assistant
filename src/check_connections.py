"""
Quick check that Neon (PostgreSQL), Neo4j and Groq are all reachable with the keys in .env.
Run from the project root:  python -m src.check_connections
"""
import psycopg

from src import config


def check(name, fn):
    try:
        print(f"  OK    {name}: {fn()}")
        return True
    except Exception as e:
        print(f"  FAIL  {name}: {type(e).__name__}: {str(e)[:200]}")
        return False


def postgres():
    with psycopg.connect(config.pg_conninfo(readonly=True)) as conn:
        n = conn.execute("SELECT COUNT(*) FROM employees").fetchone()[0]
    return f"{n} employees in {config.PG_DB}"


def neo4j():
    from src.graph.neo4j_client import run, close
    n = run("MATCH (n) RETURN count(n) AS n")[0]["n"]
    close()
    return f"connected to {config.NEO4J_URI} ({n} nodes so far)"


def groq_llm():
    from src import llm
    schema = {"type": "object", "properties": {"answer": {"type": "string"}},
              "required": ["answer"], "additionalProperties": False}
    out = llm.chat_json("Reply in JSON.", "Say hello in 3 words.", schema, max_tokens=300)
    return f"{config.GROQ_MODEL} replied {out['answer']!r}"


if __name__ == "__main__":
    print("Checking connections ...")
    ok = [check("PostgreSQL (Neon)", postgres), check("Neo4j", neo4j), check("Groq", groq_llm)]
    print("\nAll good!" if all(ok) else "\nFix the FAIL lines above (usually a typo in .env).")
