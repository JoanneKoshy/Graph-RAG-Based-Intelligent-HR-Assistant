"""
Step 3c - Load the LLM-extracted triples into Neo4j.

The important part here is ENTITY RESOLUTION: the LLM writes names as plain text
("Anu Nair", "Aurora CRM Revamp", "python"), and we must link them to the
existing graph nodes (Employee 1042, Project 7, Skill "Python").
Names that cannot be matched are reported instead of creating duplicate nodes.

Also creates a (:Document) node for every document (including policies) with its
full text, linked to everything it mentions. Step 4 adds embeddings to these.

Run from the project root:  python -m src.graph.load_extractions
"""
import json
import re
from collections import Counter, defaultdict
from difflib import get_close_matches

from src import config
from src.graph.extract_from_docs import RELATIONS, OUTCOMES, DOC_FOLDERS
from src.graph.neo4j_client import run, close


def norm(text):
    text = text.lower().strip().rstrip(".")
    text = re.sub(r"\s+", " ", text)
    return text


class Resolver:
    """Maps names written by the LLM onto existing graph nodes."""

    def __init__(self, employees, candidates, projects, skills, departments):
        # each argument: list of (name, key_value)
        self.idx = {
            "Employee": {norm(n): k for n, k in employees},
            "Candidate": {norm(n): k for n, k in candidates},
            "Project": {norm(n): k for n, k in projects},
            "Skill": {norm(n): n for n, _ in skills},
            "Department": {norm(n): k for n, k in departments},
            "Outcome": {norm(o): o for o in OUTCOMES},
        }
        self.unresolved = Counter()

    def _match(self, kind, name, cutoff):
        index = self.idx[kind]
        key = norm(name)
        if key in index:
            return index[key]
        close = get_close_matches(key, list(index), n=1, cutoff=cutoff)
        return index[close[0]] if close else None

    def resolve(self, typ, name):
        """Return (label, key_property, key_value) or None."""
        if typ == "Person":
            emp = self._match("Employee", name, 0.9)
            if emp is not None:
                return ("Employee", "emp_id", emp)
            cand = self._match("Candidate", name, 0.9)
            if cand is not None:
                return ("Candidate", "candidate_id", cand)
        elif typ == "Project":
            clean = re.sub(r"\bproject\b", "", name, flags=re.I)
            pid = self._match("Project", clean, 0.85)
            if pid is not None:
                return ("Project", "project_id", pid)
        elif typ == "Department":
            clean = re.sub(r"\b(team|department|dept)\b", "", name, flags=re.I)
            did = self._match("Department", clean, 0.8)
            if did is not None:
                return ("Department", "dept_id", did)
        elif typ == "Skill":
            existing = self._match("Skill", name, 0.9)
            return ("Skill", "name", existing or name.strip())
        elif typ == "SoftSkill":
            return ("SoftSkill", "name", norm(name))
        elif typ == "Outcome":
            return ("Outcome", "name", self._match("Outcome", name, 0.6) or name.strip())
        elif typ in ("Company", "Institution", "Risk"):
            return (typ, "name", name.strip().rstrip("."))
        self.unresolved[(typ, name)] += 1
        return None


def resolve_extractions(extractions, resolver):
    """Turn cached extractions into resolved edges + document mentions (pure Python, no database)."""
    edges, mentions = [], defaultdict(set)
    for ex in extractions:
        doc = ex["doc_id"]
        for t in ex["triples"]:
            src_type, tgt_type = RELATIONS[t["relation"]]
            a = resolver.resolve(src_type, t["source"])
            b = resolver.resolve(tgt_type, t["target"])
            if a is None or b is None or a == b:
                continue
            rel = t["relation"]
            if rel == "USED_SKILL" and a[0] == "Candidate":
                rel = "HAS_SKILL"            # candidates' resume skills
            edges.append({"rel": rel, "a": a, "b": b, "doc": doc})
            mentions[doc].update([a, b])
    return edges, mentions


def write_edges(edges):
    groups = defaultdict(list)
    for e in edges:
        (la, ka, va), (lb, kb, vb) = e["a"], e["b"]
        groups[(e["rel"], la, ka, lb, kb)].append({"src": va, "tgt": vb, "doc": e["doc"]})
    for (rel, la, ka, lb, kb), rows in groups.items():
        # labels / relation names come from our own fixed tables, never from LLM text
        run(f"""UNWIND $rows AS r
                MATCH (a:{la} {{{ka}: r.src}})
                MERGE (b:{lb} {{{kb}: r.tgt}})
                  ON CREATE SET b.extracted = true
                MERGE (a)-[x:{rel}]->(b)
                SET x.extracted = true,
                    x.source_docs = CASE WHEN r.doc IN coalesce(x.source_docs, [])
                                         THEN x.source_docs ELSE coalesce(x.source_docs, []) + r.doc END""",
            rows=rows)


def write_documents(mentions):
    rows = []
    for folder in list(DOC_FOLDERS.values()) + ["policies"]:
        for path in sorted((config.DATA_DOCS / folder).glob("*.*")):
            text = path.read_text(encoding="utf-8").strip()
            doc_type = {"reviews": "review", "projects": "project", "resumes": "resume"}.get(folder, "policy")
            rows.append({"doc_id": path.stem, "type": doc_type, "title": text.splitlines()[0].lstrip("# ").strip(),
                         "path": f"{folder}/{path.name}", "text": text})
    run("""UNWIND $rows AS r MERGE (d:Document {doc_id: r.doc_id})
           SET d.type = r.type, d.title = r.title, d.path = r.path, d.text = r.text""", rows=rows)

    # ABOUT: the main subject of each document
    run("""MATCH (d:Document {type: 'review'})
           WITH d, toInteger(split(d.doc_id, '_')[1]) AS emp
           MATCH (e:Employee {emp_id: emp}) MERGE (d)-[:ABOUT]->(e)""")
    run("""MATCH (d:Document {type: 'project'})
           WITH d, toInteger(split(d.doc_id, '_')[1]) AS pid
           MATCH (p:Project {project_id: pid}) MERGE (d)-[:ABOUT]->(p)""")
    run("""MATCH (d:Document {type: 'resume'}), (c:Candidate)
           WHERE c.resume_file = d.doc_id + '.txt' MERGE (d)-[:ABOUT]->(c)""")

    # MENTIONS: every entity the LLM found in the document
    groups = defaultdict(list)
    for doc, ents in mentions.items():
        for label, key, val in ents:
            groups[(label, key)].append({"doc": doc, "val": val})
    for (label, key), rows_ in groups.items():
        run(f"""UNWIND $rows AS r MATCH (d:Document {{doc_id: r.doc}}), (n:{label} {{{key}: r.val}})
                MERGE (d)-[:MENTIONS]->(n)""", rows=rows_)
    return len(rows)


def load_resolver():
    return Resolver(
        employees=[(r["name"], r["id"]) for r in run("MATCH (e:Employee) RETURN e.name AS name, e.emp_id AS id")],
        candidates=[(r["name"], r["id"]) for r in run("MATCH (c:Candidate) RETURN c.name AS name, c.candidate_id AS id")],
        projects=[(r["name"], r["id"]) for r in run("MATCH (p:Project) RETURN p.name AS name, p.project_id AS id")],
        skills=[(r["name"], r["name"]) for r in run("MATCH (s:Skill) RETURN s.name AS name")],
        departments=[(r["name"], r["id"]) for r in run("MATCH (d:Department) RETURN d.name AS name, d.dept_id AS id")],
    )


def read_extractions():
    files = sorted(config.DATA_EXTRACTED.glob("*.json"))
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def main():
    extractions = read_extractions()
    if not extractions:
        print("No extractions found. Run:  python -m src.graph.extract_from_docs")
        return
    print(f"{len(extractions)} extracted documents, {sum(len(e['triples']) for e in extractions)} triples")

    print("Removing previously loaded extracted facts ...")
    run("MATCH ()-[x]->() WHERE x.extracted = true DELETE x")
    run("MATCH (n) WHERE n.extracted = true DETACH DELETE n")
    run("MATCH (d:Document) DETACH DELETE d")

    resolver = load_resolver()
    edges, mentions = resolve_extractions(extractions, resolver)
    write_edges(edges)
    n_docs = write_documents(mentions)

    print(f"Loaded {len(edges)} extracted relationships and {n_docs} Document nodes")
    for rel, n in Counter(e["rel"] for e in edges).most_common():
        print(f"  [:{rel:18s}] {n:>4}")
    if resolver.unresolved:
        print(f"\n{sum(resolver.unresolved.values())} names could not be matched to the graph (skipped):")
        for (typ, name), n in resolver.unresolved.most_common(10):
            print(f"  {typ:10s} {name!r} x{n}")
    close()
    print("\nNext:  python -m src.graph.check_graph")


if __name__ == "__main__":
    main()
