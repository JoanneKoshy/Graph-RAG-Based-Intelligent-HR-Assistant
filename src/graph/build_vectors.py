"""
Step 4 - Split every Document into chunks, embed them, and store the vectors in Neo4j.

  (:Document)-[:HAS_CHUNK]->(:Chunk {text, embedding})

Because the chunks live INSIDE the graph, a vector search hit can be expanded through
the graph (chunk -> document -> employee -> department / manager / skills ...).
That combination is what makes the system *hybrid* Graph RAG.

Also creates a full-text index on entity names, used later to find the people,
projects and skills mentioned in a question.

Safe to re-run. Re-run it whenever you re-run load_extractions.
Run from the project root:  python -m src.graph.build_vectors
"""
import re
import time

from src import embeddings
from src.graph.neo4j_client import run, close

MAX_CHARS = 1000      # bge-small reads up to ~512 tokens; 1000 characters is safely below that


def chunk_document(doc):
    """Return a list of chunk texts. Policies are split by '## ' sections; other documents
    are short, so they are usually one chunk. Every chunk starts with the document title so
    it still makes sense on its own."""
    title, text = doc["title"], doc["text"]
    if doc["type"] == "policy":
        parts = re.split(r"\n(?=## )", text)
        intro = parts[0]
        pieces = [intro] + [f"{title}\n{p}" for p in parts[1:]]
    else:
        pieces = [text]

    chunks = []
    for piece in pieces:
        if len(piece) <= MAX_CHARS:
            chunks.append(piece.strip())
            continue
        current = ""                       # pack paragraphs/lines up to MAX_CHARS
        for line in piece.split("\n"):
            if current and len(current) + len(line) + 1 > MAX_CHARS:
                chunks.append(current.strip())
                current = f"{title}\n"
            current += line + "\n"
        if current.strip() and current.strip() != title:
            chunks.append(current.strip())
    return [c for c in chunks if c]


def main():
    docs = run("MATCH (d:Document) RETURN d.doc_id AS doc_id, d.type AS type, d.title AS title, d.text AS text "
               "ORDER BY d.doc_id")
    if not docs:
        print("No Document nodes found. Run:  python -m src.graph.load_extractions")
        return

    rows = []
    for d in docs:
        for i, text in enumerate(chunk_document(d)):
            rows.append({"chunk_id": f"{d['doc_id']}#{i}", "doc_id": d["doc_id"], "idx": i, "text": text})
    print(f"{len(docs)} documents -> {len(rows)} chunks")

    print(f"Embedding with {embeddings.MODEL_NAME} (first run downloads the model, ~70 MB) ...")
    start = time.time()
    vectors = embeddings.embed_passages(r["text"] for r in rows)
    for r, v in zip(rows, vectors):
        r["embedding"] = v
    print(f"  done in {time.time() - start:.1f}s ({len(vectors[0])} dimensions)")

    print("Writing chunks to Neo4j ...")
    run("MATCH (c:Chunk) DETACH DELETE c")
    run("CREATE CONSTRAINT chunk_chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.chunk_id IS UNIQUE")
    for i in range(0, len(rows), 100):
        run("""UNWIND $rows AS r
               MATCH (d:Document {doc_id: r.doc_id})
               CREATE (c:Chunk {chunk_id: r.chunk_id, doc_id: r.doc_id, idx: r.idx, text: r.text})
               SET c.embedding = r.embedding
               CREATE (d)-[:HAS_CHUNK]->(c)""", rows=rows[i:i + 100])

    print("Creating indexes ...")
    run("""CREATE VECTOR INDEX chunk_embedding IF NOT EXISTS
           FOR (c:Chunk) ON (c.embedding)
           OPTIONS {indexConfig: {`vector.dimensions`: 384, `vector.similarity_function`: 'cosine'}}""")
    run("""CREATE FULLTEXT INDEX entity_names IF NOT EXISTS
           FOR (n:Employee|Candidate|Project|Skill|Department|Client|SoftSkill) ON EACH [n.name]""")
    run("CALL db.awaitIndexes(300)")

    n = run("MATCH (:Document)-[:HAS_CHUNK]->(c:Chunk) WHERE c.embedding IS NOT NULL RETURN count(c) AS n")[0]["n"]
    for r in run("SHOW INDEXES YIELD name, type, state WHERE name IN ['chunk_embedding', 'entity_names'] "
                 "RETURN name, type, state"):
        print(f"  {r['name']:16s} {r['type']:9s} {r['state']}")
    print(f"\n{n} chunks with embeddings stored in the graph.")
    close()
    print("Next:  python -m src.retrieval.search_demo")


if __name__ == "__main__":
    main()
