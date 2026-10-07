"""
Step 3b - LLM extraction: turn unstructured HR documents into knowledge-graph triples.

For every review, project report and resume, the LLM returns triples like
    ("Anu Nair", "MENTORS", "Rahul Menon")
Results are cached in data/extracted/<doc_id>.json, so:
  - re-running only processes documents that are not done yet
  - if the Groq daily limit is hit, just run it again later and it continues

Run from the project root:  python -m src.graph.extract_from_docs
"""
import json
import time

import groq

from src import config, llm

# relation -> (source type, target type). The graph loader uses this table too.
RELATIONS = {
    "MENTORS":           ("Person", "Person"),
    "COLLABORATED_WITH": ("Person", "Person"),
    "LED":               ("Person", "Project"),
    "CONTRIBUTED_TO":    ("Person", "Project"),
    "RECOGNIZED_ON":     ("Person", "Project"),
    "HAS_SOFT_SKILL":    ("Person", "SoftSkill"),
    "USED_SKILL":        ("Person", "Skill"),
    "RECOMMENDED_FOR":   ("Person", "Outcome"),
    "INTERESTED_IN":     ("Person", "Department"),
    "WORKED_AT":         ("Person", "Company"),
    "STUDIED_AT":        ("Person", "Institution"),
    "PROJECT_USES":      ("Project", "Skill"),
    "HAS_RISK":          ("Project", "Risk"),
}
OUTCOMES = ["Promotion", "Additional Responsibilities", "Performance Improvement Plan"]

SYSTEM_PROMPT = f"""You extract facts from HR documents to build a knowledge graph.
For EACH document you receive, return its doc_id and a list of triples (source, relation, target).

Allowed relations (source type -> target type):
- MENTORS: Person -> Person (mentor -> mentee)
- COLLABORATED_WITH: Person -> Person (people who worked closely together)
- LED: Person -> Project
- CONTRIBUTED_TO: Person -> Project (team members of a project)
- RECOGNIZED_ON: Person -> Project (special recognition / praise on that project)
- HAS_SOFT_SKILL: Person -> SoftSkill (e.g. communication, leadership, teamwork, mentoring)
- USED_SKILL: Person -> Skill (technical or business skill, e.g. Python, React, Recruitment)
- RECOMMENDED_FOR: Person -> Outcome (one of: {", ".join(OUTCOMES)})
- INTERESTED_IN: Person -> Department (wants to move to that department)
- WORKED_AT: Person -> Company (previous employer, from resumes)
- STUDIED_AT: Person -> Institution (college / university, from resumes)
- PROJECT_USES: Project -> Skill (technology stack of a project)
- HAS_RISK: Project -> Risk (short risk description, e.g. "integration delays with a third-party API")

Rules:
- Always write people's FULL names exactly as in the document. If a person is referred to by first
  name only, use the full name given elsewhere in the same document.
- Write project names exactly as in the document, without the word "project".
- Soft skills in lowercase. Technical skills with their usual capitalisation.
- Only extract facts that are clearly stated. Do not guess. Do not repeat identical triples.
- A "below expectations" review with a performance improvement plan -> RECOMMENDED_FOR "Performance Improvement Plan".
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "documents": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "doc_id": {"type": "string"},
                    "triples": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source": {"type": "string"},
                                "relation": {"type": "string", "enum": list(RELATIONS)},
                                "target": {"type": "string"},
                            },
                            "required": ["source", "relation", "target"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["doc_id", "triples"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["documents"],
    "additionalProperties": False,
}

DOC_FOLDERS = {"review": "reviews", "project": "projects", "resume": "resumes"}
# documents per LLM call; project reports are longer, so fewer per call (Groq free tier: 8K tokens/min)
BATCH_SIZE = {"review": 6, "project": 3, "resume": 6}


def list_documents():
    docs = []
    for doc_type, folder in DOC_FOLDERS.items():
        for path in sorted((config.DATA_DOCS / folder).glob("*.txt")):
            docs.append({"doc_id": path.stem, "type": doc_type, "path": path,
                         "text": path.read_text(encoding="utf-8").strip()})
    return docs


def cache_path(doc_id):
    return config.DATA_EXTRACTED / f"{doc_id}.json"


def clean_triples(triples):
    seen, out = set(), []
    for t in triples:
        s, r, o = t["source"].strip(), t["relation"], t["target"].strip()
        if not s or not o or r not in RELATIONS:
            continue
        key = (s.lower(), r, o.lower())
        if key not in seen:
            seen.add(key)
            out.append({"source": s, "relation": r, "target": o})
    return out


def extract_batch(batch):
    user = "\n\n".join(f"### doc_id: {d['doc_id']}\n{d['text']}" for d in batch)
    try:
        result = llm.chat_json(SYSTEM_PROMPT, user, SCHEMA, schema_name="hr_triples", max_tokens=4500)
    except (llm.DailyLimitReached, groq.AuthenticationError, groq.PermissionDeniedError, groq.NotFoundError):
        raise                     # wrong key / model name / quota: stop instead of failing every document
    except Exception as e:
        if len(batch) == 1:
            print(f"    failed on {batch[0]['doc_id']}: {str(e)[:150]} (skipping, will retry next run)")
            return 0
        print("    batch failed, retrying documents one at a time ...")
        return sum(extract_batch([d]) for d in batch)
    by_id = {d["doc_id"]: d for d in result["documents"]}
    saved = 0
    for d in batch:
        if d["doc_id"] not in by_id:
            print(f"    (model skipped {d['doc_id']}, will retry next run)")
            continue
        triples = clean_triples(by_id[d["doc_id"]]["triples"])
        cache_path(d["doc_id"]).write_text(json.dumps(
            {"doc_id": d["doc_id"], "type": d["type"], "triples": triples}, indent=1), encoding="utf-8")
        saved += 1
    return saved


def main():
    config.DATA_EXTRACTED.mkdir(parents=True, exist_ok=True)
    docs = list_documents()
    todo = [d for d in docs if not cache_path(d["doc_id"]).exists()]
    print(f"{len(docs)} documents, {len(docs) - len(todo)} already extracted, {len(todo)} to do")

    # keep each batch to one document type so the model sees similar documents together
    batches = []
    for doc_type in DOC_FOLDERS:
        group = [d for d in todo if d["type"] == doc_type]
        size = BATCH_SIZE[doc_type]
        batches += [group[i:i + size] for i in range(0, len(group), size)]

    start = time.time()
    done = 0
    try:
        for i, batch in enumerate(batches, 1):
            print(f"  batch {i}/{len(batches)} ({batch[0]['type']}s: {batch[0]['doc_id']} ...)")
            done += extract_batch(batch)
    except llm.DailyLimitReached as e:
        print(f"\nStopped: {e}\nProgress is saved. Run this command again later to continue.")
    finally:
        mins = (time.time() - start) / 60
        print(f"\nExtracted {done} documents in {mins:.1f} min "
              f"({llm.usage['calls']} LLM calls, {llm.usage['tokens']:,} tokens)")

    remaining = sum(1 for d in docs if not cache_path(d["doc_id"]).exists())
    if remaining:
        print(f"{remaining} documents still to do -> run this command again")
    else:
        print("All documents extracted.\nNext:  python -m src.graph.load_extractions")


if __name__ == "__main__":
    main()
