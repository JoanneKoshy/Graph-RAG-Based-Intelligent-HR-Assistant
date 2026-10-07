"""
Step 7a - Make graph CONCEPTS searchable by meaning.

Step 4 showed that plain vector search over whole documents missed
"projects delayed by an external vendor's API": the risk sentence was diluted inside
a long project report. But the graph already holds that risk as its own node:
    (:Risk {name: "integration delays with a third-party API"})
Here we embed every concept node (skills, soft skills, outcomes, risks, departments,
clients, projects, companies, institutions) so a question can find the right graph
node by meaning, and the retriever then walks the graph from it.

Stored as (:Concept {text, embedding})-[:DESCRIBES]->(the real node), so the real
nodes stay clean. Re-run after load_extractions / build_vectors.
Run from the project root:  python -m src.graph.build_concept_index
"""
from src import embeddings
from src.graph.neo4j_client import run, close

CONCEPT_LABELS = ["Skill", "SoftSkill", "Outcome", "Risk", "Department", "Client",
                  "Project", "Company", "Institution"]
READABLE = {"SoftSkill": "Soft skill", "Outcome": "HR recommendation", "Risk": "Project risk",
            "Institution": "College / university", "Company": "Previous employer"}


def concept_text(r):
    label = READABLE.get(r["label"], r["label"])
    if r["label"] == "Project":
        return f"Project: {r['name']} (client {r['client']}, status {r['status']})"
    return f"{label}: {r['name']}"


def main():
    rows = run("""MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels) AND n.name IS NOT NULL
                  OPTIONAL MATCH (n)-[:FOR_CLIENT]->(c:Client)
                  RETURN elementId(n) AS id, labels(n)[0] AS label, n.name AS name,
                         n.status AS status, c.name AS client""", labels=CONCEPT_LABELS)
    for r in rows:
        r["text"] = concept_text(r)
    print(f"{len(rows)} concept nodes to embed")

    vectors = embeddings.embed_passages(r["text"] for r in rows)
    for r, v in zip(rows, vectors):
        r["embedding"] = v

    run("MATCH (c:Concept) DETACH DELETE c")
    for i in range(0, len(rows), 200):
        run("""UNWIND $rows AS r
               MATCH (n) WHERE elementId(n) = r.id
               CREATE (c:Concept {text: r.text, label: r.label, name: r.name})
               SET c.embedding = r.embedding
               CREATE (c)-[:DESCRIBES]->(n)""", rows=rows[i:i + 200])

    run("""CREATE VECTOR INDEX concept_embedding IF NOT EXISTS
           FOR (c:Concept) ON (c.embedding)
           OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}""")
    run("CALL db.awaitIndexes(300)")
    n = run("MATCH (c:Concept)-[:DESCRIBES]->() RETURN count(c) AS n")[0]["n"]
    print(f"{n} concepts stored with embeddings (index: concept_embedding)")
    close()
    print("Next:  python -m src.retrieval.graph_retriever")


if __name__ == "__main__":
    main()
