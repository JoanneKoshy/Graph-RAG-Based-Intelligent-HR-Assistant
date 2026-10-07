"""
Step 7c - The Graph RAG retriever: combines four retrieval strategies into one context.

  1. ENTITY ANCHORS   - people / projects named in the question, linked to graph nodes (Step 5)
  2. CONCEPT SEARCH   - graph concepts found by MEANING ("external vendor's API" ->
                        Risk "integration delays with a third-party API")
  3. GRAPH QUERY      - Text-to-Cypher for precise multi-hop answers, guided by 1 + 2
  4. NEIGHBOURHOOD    - 1-hop facts around the anchors, re-ranked by similarity to the question
                        (only from specific nodes, never from hubs like "Promotion"), plus the
                        documents that are ABOUT the anchors (graph-guided document retrieval)

retrieve() returns everything as one JSON-friendly dict for the answer step (Step 8).

Try it from the project root:
  python -m src.retrieval.graph_retriever "which projects are delayed by an external vendor's API?"
"""
import math
import sys

from src import embeddings
from src.agents import cypher_agent
from src.agents.query_understanding import analyze
from src.graph.neo4j_client import run

ANCHOR_KEYS = {"Employee": "emp_id", "Candidate": "candidate_id", "Project": "project_id"}
SKIP_RELS = {"HAS_CHUNK", "MENTIONS", "DESCRIBES"}


def concept_search(question, k=5, min_score=0.80, margin=0.03):
    """Concepts similar in meaning to the question. This embedding model gives fairly high scores to
    most short texts, so we keep only clear matches: above min_score AND close to the best match."""
    vector = embeddings.embed_query(question)
    rows = run("""CALL db.index.vector.queryNodes('concept_embedding', $k, $vector) YIELD node AS c, score
                  MATCH (c)-[:DESCRIBES]->(n)
                  RETURN c.label AS label, n.name AS name, round(score, 3) AS score
                  ORDER BY score DESC""", k=k, vector=vector)
    if not rows:
        return []
    best = rows[0]["score"]
    return [r for r in rows if r["score"] >= max(min_score, best - margin)]


def anchors_from(analysis):
    anchors = []
    for e in analysis.get("entities", []):
        m = e.get("match")
        if m and m["label"] in ANCHOR_KEYS and m["id"] is not None:
            anchors.append({"label": m["label"], "key": ANCHOR_KEYS[m["label"]], "id": m["id"], "name": m["name"]})
    return anchors


def _cos(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1)


def neighbourhood(anchors, question, top=25):
    facts = []
    for a in anchors:
        rows = run(f"""MATCH (a:{a['label']} {{{a['key']}: $id}})-[r]-(b)
                       WHERE NOT b:Chunk AND NOT b:Concept AND NOT b:Document
                       RETURN coalesce(a.name, '') AS a, type(r) AS rel, startNode(r) = a AS outgoing,
                              coalesce(b.name, b.title, '') AS b, properties(r) AS props
                       LIMIT 200""", id=a["id"])
        for r in rows:
            if r["rel"] in SKIP_RELS:
                continue
            props = {k: v for k, v in r["props"].items() if k not in ("extracted", "source_docs")}
            extra = f" ({', '.join(f'{k}: {v}' for k, v in props.items())})" if props else ""
            src = "doc" if r["props"].get("extracted") else "sql"
            text = f"{r['a']} {r['rel']} {r['b']}" if r["outgoing"] else f"{r['b']} {r['rel']} {r['a']}"
            facts.append({"fact": text + extra, "source": src})
    if not facts:
        return []
    # re-rank: keep the facts most similar in meaning to the question
    q = embeddings.embed_query(question)
    vecs = embeddings.embed_passages(f["fact"] for f in facts)
    for f, v in zip(facts, vecs):
        f["score"] = round(_cos(q, v), 3)
    unique = {f["fact"]: f for f in facts}.values()
    return sorted(unique, key=lambda f: -f["score"])[:top]


def anchor_documents(anchors, limit=3):
    docs = []
    for a in anchors:
        docs += run(f"""MATCH (d:Document)-[:ABOUT]->(n:{a['label']} {{{a['key']}: $id}})
                        MATCH (d)-[:HAS_CHUNK]->(c:Chunk)
                        RETURN d.doc_id AS doc_id, d.type AS doc_type, c.text AS text
                        LIMIT $limit""", id=a["id"], limit=limit)
    return docs[:limit * 2]


def retrieve(question, analysis=None):
    analysis = analysis or analyze(question)
    q = analysis.get("rewritten_question") or question
    anchors = anchors_from(analysis)
    concepts = concept_search(q)

    hints = [f"{a['label']} '{a['name']}' ({a['key']} {a['id']})" for a in anchors]
    hints += [f"{e['match']['label']} '{e['match']['name']}'" for e in analysis.get("entities", [])
              if e.get("match") and e["match"]["label"] not in ANCHOR_KEYS]
    hints += [f"{c['label']} '{c['name']}' (may be relevant: similar in meaning to the question; "
              f"use it only if the question is about it)" for c in concepts]

    cypher = cypher_agent.ask(q, hints)
    return {
        "question": question,
        "anchors": anchors,
        "concepts": concepts,
        "cypher": cypher,
        "facts": neighbourhood(anchors, q),
        "documents": anchor_documents(anchors),
    }


def show(res):
    print(f"\nQ: {res['question']}")
    print("Anchors : " + (", ".join(f"{a['label']} {a['name']}" for a in res["anchors"]) or "-"))
    print("Concepts: " + (", ".join(f"{c['label']} '{c['name']}' ({c['score']})" for c in res["concepts"]) or "-"))
    cypher_agent.show(res["cypher"])
    if res["facts"]:
        print(f"Top neighbourhood facts ({len(res['facts'])}):")
        for f in res["facts"][:10]:
            print(f"  [{f['source']}] {f['fact']}   ({f['score']})")
    for d in res["documents"]:
        print(f"Document {d['doc_id']}: {' '.join(d['text'].split())[:150]}...")


if __name__ == "__main__":
    show(retrieve(" ".join(sys.argv[1:]) or "Which projects are delayed by problems with an external vendor's API?"))
