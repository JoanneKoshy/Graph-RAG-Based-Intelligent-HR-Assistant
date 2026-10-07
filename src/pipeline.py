"""
Step 8 - The complete HR assistant pipeline (the whole block diagram, end to end).

  question
    -> Query Understanding + Task Router          (Step 5)
    -> Database Agent: Text-to-SQL                (Step 6)   if the route needs SQL
    -> Graph RAG retriever                        (Step 7)   if the route needs the graph
    -> Document search by class                   (Step 4)   if the route needs documents
    -> Structured Representation (one JSON)       (this file)
    -> Response Synthesis LLM, with citations     (this file)
    -> Grounding check: are the numbers and names in the answer really in the retrieved data?

Run from the project root:
  python -m src.pipeline "is Arya Zachariah eligible for promotion under our policy?"
  python -m src.pipeline            (interactive: keep asking questions, type 'exit' to stop)
  python -m src.pipeline --demo     (5 sample questions, one per route type)
"""
import json
import re
import sys
import time

from src import llm
from src.agents import sql_agent
from src.agents.query_understanding import analyze
from src.retrieval import graph_retriever, vector_search

MAX_ROWS_TO_LLM = 40
MAX_FACTS_TO_LLM = 15
MAX_DOC_CHARS = 900

SYSTEM_PROMPT = """You are the HR assistant of Nexora Technologies, answering an HR manager.
Answer the question using ONLY the retrieved context (JSON) below. The context can contain:
- "sql": rows from the HR database (exact numbers)
- "graph": results of a knowledge-graph query plus related facts (relationships, mentoring,
  soft skills, recommendations, risks...). Facts marked source "doc" were extracted from documents.
- "documents": passages from HR policies, performance reviews, project reports and resumes

RULES
- Use only facts in the context. Never invent names, numbers or policy rules.
- If the context does not contain the answer, say clearly what is missing.
- When the question combines sources (e.g. a person's ratings + a policy rule), reason step by step
  in the answer: state the facts, state the rule, then give the conclusion.
- Cite sources inline: [SQL], [Graph], or [Doc: <doc_id>] right after the facts they support.
- Use short paragraphs or bullet lists. Give exact numbers as they appear in the data.
- If the data was truncated (more rows than shown), say so.
- If two sources disagree, trust the source that actually holds that kind of data (mentoring,
  soft skills, recommendations and risks come from the graph; numbers come from SQL) and ignore an
  "error" or "not answerable" source instead of describing it.
- Put follow-up questions ONLY in follow_up_questions (max 2), never inside the answer text.
"""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "sources_used": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "follow_up_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["answer", "sources_used", "confidence", "follow_up_questions"],
    "additionalProperties": False,
}

OUT_OF_SCOPE = ("I'm the Nexora HR assistant, so I can only answer questions about employees, "
                "departments, projects, attendance, payroll, performance, candidates and HR policies.")


def entity_hints(analysis):
    hints = []
    for e in analysis.get("entities", []):
        m = e.get("match")
        if m:
            extra = f" (id {m['id']})" if m.get("id") is not None else ""
            hints.append(f"'{e['text']}' refers to {m['label']} '{m['name']}'{extra}")
    return hints


def build_context(analysis, sql_res, graph_res, docs):
    """The 'Structured Representation (JSON)' box: everything retrieved, in one compact object."""
    ctx = {"question": analysis["rewritten_question"], "route": analysis["route"]}
    if sql_res:
        ctx["sql"] = {"query": sql_res["sql"], "error": sql_res["error"], "row_count": sql_res["row_count"],
                      "truncated": sql_res["row_count"] > MAX_ROWS_TO_LLM or sql_res["truncated"],
                      "rows": sql_res["rows"][:MAX_ROWS_TO_LLM]}
    if graph_res:
        cy = graph_res["cypher"]
        ctx["graph"] = {"query": cy["cypher"], "error": cy["error"], "row_count": cy["row_count"],
                        "truncated": cy["row_count"] > MAX_ROWS_TO_LLM,
                        "rows": cy["rows"][:MAX_ROWS_TO_LLM],
                        "related_facts": [{"fact": f["fact"], "source": f["source"]}
                                          for f in graph_res["facts"][:MAX_FACTS_TO_LLM]]}
    if docs:
        seen, out = set(), []
        for d in docs:
            if d["doc_id"] + d["text"][:40] in seen:
                continue
            seen.add(d["doc_id"] + d["text"][:40])
            out.append({"doc_id": d["doc_id"], "type": d.get("doc_type"), "text": d["text"][:MAX_DOC_CHARS]})
        ctx["documents"] = out
    return ctx


def grounding_check(answer, ctx):
    """Simple fact verification: every number and person-like name in the answer should appear in the context."""
    context_text = json.dumps(ctx, default=str).lower()
    clean = re.sub(r"\[(?:sql|graph|doc:[^\]]*)\]", " ", answer, flags=re.I)
    numbers = set(re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w])", clean))
    starters = {"so", "the", "in", "if", "for", "and", "but", "yes", "no", "this", "that", "their", "her", "his",
                "based", "both", "also", "however", "therefore", "overall", "according", "since", "as", "all"}
    names = {n for n in re.findall(r"\b[A-Z][a-z]+ [A-Z][a-z]+\b", clean) if n.split()[0].lower() not in starters}
    unsupported = [n for n in numbers if n not in context_text and n.rstrip("0").rstrip(".") not in context_text]
    unsupported += [n for n in names if n.lower() not in context_text]
    checked = len(numbers) + len(names)
    return {"checked": checked, "unsupported": sorted(unsupported),
            "grounded_pct": round(100 * (checked - len(unsupported)) / checked) if checked else 100}


def answer(question, verbose=True):
    t0 = time.time()
    timings, calls_before = {}, llm.usage["calls"]

    def step(name, fn):
        s = time.time()
        if verbose:
            print(f"  ... {name}", flush=True)
        out = fn()
        timings[name] = round(time.time() - s, 1)
        return out

    analysis = step("understanding + routing", lambda: analyze(question))
    if analysis["route"] == "none" or analysis["intent"] == "out_of_scope":
        return {"question": question, "analysis": analysis, "answer": OUT_OF_SCOPE, "sources_used": [],
                "confidence": "high", "follow_up_questions": [], "context": {}, "grounding": None,
                "timings": timings, "total_seconds": round(time.time() - t0, 1), "llm_calls": 1}

    q = analysis["rewritten_question"]
    hints = entity_hints(analysis)
    sql_res = step("SQL agent", lambda: sql_agent.ask(q, hints)) if analysis["needs_sql"] else None
    graph_res = step("graph retriever", lambda: graph_retriever.retrieve(question, analysis)) \
        if analysis["needs_graph"] else None
    docs = []
    if analysis["needs_documents"]:
        docs = step("document search", lambda: vector_search.search(q, k=4, doc_types=analysis["doc_classes"] or None))
    if graph_res:
        docs += graph_res["documents"]          # documents ABOUT the people/projects in the question

    ctx = build_context(analysis, sql_res, graph_res, docs)
    out = step("answer synthesis", lambda: llm.chat_json(
        SYSTEM_PROMPT, "CONTEXT:\n" + json.dumps(ctx, default=str, indent=1) + f"\n\nQUESTION: {question}",
        ANSWER_SCHEMA, schema_name="hr_answer", max_tokens=3000))

    return {"question": question, "analysis": analysis, **out, "context": ctx,
            "grounding": grounding_check(out["answer"], ctx), "timings": timings,
            "total_seconds": round(time.time() - t0, 1), "llm_calls": llm.usage["calls"] - calls_before}


def show(r):
    a = r["analysis"]
    print(f"\n{'=' * 90}\nQ: {r['question']}")
    print(f"Route: {a['route'].upper()}   intent: {a['intent']}"
          + (f"   doc classes: {a['doc_classes']}" if a.get("doc_classes") else ""))
    ctx = r["context"]
    if "sql" in ctx:
        print(f"SQL   : {' '.join((ctx['sql']['query'] or '').split())[:160]}  -> {ctx['sql']['row_count']} rows")
    if "graph" in ctx:
        print(f"Graph : {' '.join((ctx['graph']['query'] or '').split())[:160]}  -> {ctx['graph']['row_count']} rows, "
              f"{len(ctx['graph']['related_facts'])} related facts")
    if "documents" in ctx:
        print("Docs  : " + ", ".join(d["doc_id"] for d in ctx["documents"]))
    print(f"\nANSWER ({r['confidence']} confidence):\n{r['answer']}")
    if r["follow_up_questions"]:
        print("\nYou could also ask:\n" + "\n".join(f"  - {f}" for f in r["follow_up_questions"]))
    g = r["grounding"]
    if g:
        print(f"\nGrounding check: {g['grounded_pct']}% of {g['checked']} numbers/names found in the retrieved data"
              + (f"  (not found: {', '.join(g['unsupported'])})" if g["unsupported"] else ""))
    print(f"Time: {r['total_seconds']}s  {r['timings']}  LLM calls: {r['llm_calls']}")


DEMO = [
    "How many active employees does each department have?",                                   # SQL
    "Which projects are running into problems with an external vendor's API, and who leads them?",  # graph
    "How many days of paternity leave do employees get, and is it paid?",                     # documents
    "Is Arya Zachariah eligible for promotion under our appraisal policy?",                   # SQL + documents
    "Who mentors people in the Data Science team, and how are their mentees performing?",     # graph (+SQL)
]

if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["--demo"]:
        for q in DEMO:
            try:
                show(answer(q))
            except llm.DailyLimitReached as e:
                print(f"Groq daily limit reached: {e}")
                break
    elif args:
        show(answer(" ".join(args)))
    else:
        print("Nexora HR assistant. Ask a question (or type 'exit').")
        while True:
            try:
                q = input("\nYou: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if q.lower() in ("exit", "quit", ""):
                break
            try:
                show(answer(q))
            except llm.DailyLimitReached as e:
                print(f"Groq daily limit reached: {e}")
                break
            except Exception as e:          # keep the chat alive if one question fails
                print(f"Sorry, something went wrong answering that: {type(e).__name__}: {str(e)[:300]}")
