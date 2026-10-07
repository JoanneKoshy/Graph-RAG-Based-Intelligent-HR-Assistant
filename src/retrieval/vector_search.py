"""
Semantic search over document chunks (the "Document Router + RAG System" boxes of the
block diagram). Used by the Graph RAG retriever in Step 7.

search(question, k, doc_types) finds the chunks whose MEANING is closest to the question,
optionally restricted to document classes: 'policy', 'review', 'project', 'resume'.
Each hit also returns the graph node the document is ABOUT (an employee, project or
candidate), which is the entry point for walking the graph.
"""
from src import embeddings
from src.graph.neo4j_client import run

DOC_TYPES = ["policy", "review", "project", "resume"]


def search(question, k=5, doc_types=None):
    vector = embeddings.embed_query(question)
    # when filtering by document class, ask the index for more hits, then keep the best k
    fetch = k * 10 if doc_types else k
    return run("""
        CALL db.index.vector.queryNodes('chunk_embedding', $fetch, $vector) YIELD node AS c, score
        MATCH (d:Document)-[:HAS_CHUNK]->(c)
        WHERE $types IS NULL OR d.type IN $types
        WITH c, d, score ORDER BY score DESC LIMIT $k
        OPTIONAL MATCH (d)-[:ABOUT]->(s)
        RETURN c.chunk_id AS chunk_id, d.doc_id AS doc_id, d.type AS doc_type, d.title AS title,
               round(score, 3) AS score, c.text AS text,
               labels(s)[0] AS about_label, s.name AS about_name""",
        fetch=fetch, vector=vector, types=doc_types, k=k)
