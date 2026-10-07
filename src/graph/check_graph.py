"""
Step 3 check - inspect the knowledge graph, measure extraction quality, and run
multi-hop questions that plain SQL or plain vector RAG cannot answer easily.

Run from the project root:  python -m src.graph.check_graph
"""
import csv

from src import config
from src.graph.neo4j_client import run, close


def table(rows):
    if not rows:
        print("  (no results)")
        return
    cols = list(rows[0])
    w = [max(len(c), *(len(str(r[c])) for r in rows)) for c in cols]
    print("  " + " | ".join(c.ljust(x) for c, x in zip(cols, w)))
    print("  " + "-+-".join("-" * x for x in w))
    for r in rows:
        print("  " + " | ".join(str(r[c]).ljust(x) for c, x in zip(cols, w)))


def prf(found, truth):
    tp = len(found & truth)
    p = tp / len(found) if found else 0.0
    r = tp / len(truth) if truth else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return tp, p, r, f


def evaluate():
    print("\n=== Extraction quality vs ground truth (facts that exist ONLY in documents) ===")
    truth = {(int(r["mentor_id"]), int(r["mentee_id"]))
             for r in csv.DictReader(open(config.DATA_TRUTH / "mentorships.csv", encoding="utf-8"))}
    found = {(r["a"], r["b"]) for r in run(
        "MATCH (a:Employee)-[:MENTORS]->(b:Employee) RETURN a.emp_id AS a, b.emp_id AS b")}
    tp, p, r, f = prf(found, truth)
    print(f"  MENTORS         found {len(found):>3} | correct {tp:>3} / {len(truth)} | "
          f"precision {p:.2f}  recall {r:.2f}  F1 {f:.2f}")

    truth = {(int(x["emp_id"]), x["soft_skill"].lower())
             for x in csv.DictReader(open(config.DATA_TRUTH / "soft_skills.csv", encoding="utf-8"))}
    found = {(x["e"], x["s"]) for x in run(
        "MATCH (e:Employee)-[:HAS_SOFT_SKILL]->(s:SoftSkill) RETURN e.emp_id AS e, s.name AS s")}
    tp, p, r, f = prf(found, truth)
    print(f"  HAS_SOFT_SKILL  found {len(found):>3} | correct {tp:>3} / {len(truth)} | "
          f"precision {p:.2f}  recall {r:.2f}  F1 {f:.2f}")


DEMOS = {
    "Who mentors whom in Data Science, and how are the mentees rated? (doc fact + SQL fact)": """
        MATCH (m:Employee)-[:MENTORS]->(e:Employee)-[:WORKS_IN]->(:Department {name: 'Data Science'})
        RETURN m.name AS mentor, m.designation AS mentor_role, e.name AS mentee, e.latest_rating AS mentee_rating
        ORDER BY mentor LIMIT 10""",

    "Python developers who collaborated with someone recommended for promotion (3 hops)": """
        MATCH (e:Employee)-[:HAS_SKILL]->(:Skill {name: 'Python'}),
              (e)-[:COLLABORATED_WITH]-(c:Employee)-[:RECOMMENDED_FOR]->(:Outcome {name: 'Promotion'})
        RETURN DISTINCT e.name AS employee, e.designation AS role, c.name AS collaborator
        ORDER BY employee LIMIT 10""",

    "Candidate screening: which candidates share the most skills with an ongoing project's stack?": """
        MATCH (p:Project {status: 'Ongoing'})-[:USES]->(s:Skill)<-[:HAS_SKILL]-(c:Candidate)
        WITH p, c, collect(s.name) AS shared
        WHERE size(shared) >= 2
        RETURN p.name AS project, c.name AS candidate, c.applied_role AS applied_for, shared
        ORDER BY size(shared) DESC, project LIMIT 10""",

    "Explainable path: how is the top-rated employee connected to the Engineering head?": """
        MATCH (top:Employee) WHERE top.latest_rating IS NOT NULL
        WITH top ORDER BY top.latest_rating DESC, top.name LIMIT 1
        MATCH (:Department {name: 'Engineering'})-[:HEADED_BY]->(head:Employee)
        MATCH path = shortestPath((top)-[*..6]-(head))
        RETURN top.name AS from_employee, head.name AS to_head,
               [n IN nodes(path) | coalesce(n.name, n.title, n.doc_id)] AS path_nodes,
               [r IN relationships(path) | type(r)] AS path_edges""",
}


def main():
    print("=== Graph contents ===")
    table(run("MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY count DESC"))
    print()
    table(run("""MATCH ()-[x]->() WHERE type(x) <> 'HAS_CHUNK'
                 WITH type(x) AS relationship,
                      (coalesce(x.extracted, false) OR type(x) IN ['MENTIONS', 'ABOUT']) AS from_docs
                 RETURN relationship,
                        sum(CASE WHEN from_docs THEN 0 ELSE 1 END) AS from_sql,
                        sum(CASE WHEN from_docs THEN 1 ELSE 0 END) AS from_documents
                 ORDER BY relationship"""))

    evaluate()

    print("\n=== Multi-hop questions (Graph RAG retrieval preview) ===")
    for question, query in DEMOS.items():
        print(f"\nQ: {question}")
        table(run(query))
    close()


if __name__ == "__main__":
    main()
