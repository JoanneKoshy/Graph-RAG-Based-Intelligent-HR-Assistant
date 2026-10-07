"""
Step 4 check - semantic search demo, plus a first taste of graph expansion.

Notice that the questions use DIFFERENT words from the documents
("fathers" vs "paternity", "struggling" vs "below expectations"); keyword search
would miss these, embedding search finds them by meaning.

Run from the project root:  python -m src.retrieval.search_demo
"""
from src.graph.neo4j_client import run, close
from src.retrieval.vector_search import search

QUESTIONS = [
    ("How many days off do new fathers get?", ["policy"]),
    ("Can I work remotely while on a performance improvement plan?", ["policy"]),
    ("Which employees are struggling and missing deadlines?", ["review"]),
    ("Projects delayed by problems with an external vendor's API", ["project"]),
    ("Applicants who have won a hackathon", ["resume"]),
]


def expand(hit):
    """Graph expansion: from the document's subject, pull 1-hop facts out of the graph."""
    if hit["about_label"] != "Employee":
        return None
    rows = run("""MATCH (d:Document {doc_id: $doc})-[:ABOUT]->(e:Employee)
                  OPTIONAL MATCH (e)-[:WORKS_IN]->(dep:Department)
                  OPTIONAL MATCH (e)-[:REPORTS_TO]->(m:Employee)
                  OPTIONAL MATCH (mentor:Employee)-[:MENTORS]->(e)
                  RETURN e.designation AS role, dep.name AS dept, m.name AS manager,
                         e.latest_rating AS rating, e.attendance_pct AS attendance,
                         collect(DISTINCT mentor.name) AS mentored_by""", doc=hit["doc_id"])
    return rows[0] if rows else None


def main():
    for question, types in QUESTIONS:
        print(f"\nQ: {question}   [document class: {', '.join(types)}]")
        for hit in search(question, k=3, doc_types=types):
            first_line = " ".join(hit["text"].split("\n")[1:3])[:110]
            print(f"  {hit['score']:.3f}  {hit['doc_id']:30s} {first_line}")
            facts = expand(hit)
            if facts:
                print(f"         graph -> {hit['about_name']}: {facts['role']}, {facts['dept']}, "
                      f"manager {facts['manager']}, rating {facts['rating']}, "
                      f"attendance {facts['attendance']}%"
                      + (f", mentored by {', '.join(facts['mentored_by'])}" if facts["mentored_by"] else ""))
    close()


if __name__ == "__main__":
    main()
