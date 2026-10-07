"""
Step 5 check - measure how well the router picks data sources on 24 labelled HR questions.

Each question lists sources it MUST use, and sources that are OPTIONAL (acceptable either way,
e.g. "who has Python?" can be answered from SQL or from the graph).
A routing decision is correct if:  must  is a subset of  predicted  is a subset of  must + optional

Run from the project root:  python -m src.agents.eval_router
(about 24 Groq calls, takes a few minutes on the free tier)
"""
from src import llm
from src.agents.query_understanding import analyze

S, G, D = "sql", "graph", "documents"

# (question, must, optional). "must" can also be a LIST of alternatives: any one of them is accepted.
TEST_SET = [
    # ---- SQL: numbers, records, aggregates
    ("How many employees are in each department?", {S}, set()),
    ("What is the average net salary in the Finance department?", {S}, set()),
    ("Who had attendance below 85% in September 2026?", {S}, set()),
    ("List the top 5 performers in the 2025-H2 review cycle", {S}, {G}),
    ("How many candidates are shortlisted for the Data Scientist role?", {S}, {G}),
    ("Which trainings has Nakul Lal completed and what were his scores?", {S}, {G}),
    # ---- GRAPH: relationships and document-only facts
    ("Who mentors Widisha Dubey?", {G}, {D}),
    ("Which employees are recommended for promotion?", {G}, {D}),
    ("Who in Engineering has strong leadership skills?", {G}, {D, S}),
    ("Which projects have risks related to third-party API integration?", {G}, {D}),
    ("Who has worked closely with Reva Pant?", {G}, {S, D}),
    ("Which employees want to move to the Data Science team?", {G}, {D}),
    ("Find candidates whose skills match the tech stack of the Aurora Chatbot project", {G}, {S}),
    ("Which Data Science employees rated above 4 are mentoring someone?", {G}, {S}),
    # ---- DOCUMENTS: policy rules and narrative text
    ("How many days of paternity leave do employees get?", {D}, set()),
    ("Can someone on a performance improvement plan work from home?", {D}, set()),
    ("What are the rules for promotion eligibility?", {D}, set()),
    ("What is the daily travel allowance for metro cities?", {D}, set()),
    ("Summarise Arya Zachariah's latest performance review", {D}, {S, G}),
    # ---- COMBINATIONS
    ("Is Arya Zachariah eligible for promotion under our appraisal policy?", {S, D}, {G}),
    ("Which employees on a performance improvement plan also have attendance below 90%?", {G}, {S, D}),
    ("For employees recommended for promotion, what is their current salary and what increment does the policy allow?",
     {S, G, D}, set()),
    # manager / skills / projects exist in SQL *and* the graph, so either one (plus documents) is right
    ("Give me a profile of Nakul Lal: manager, skills, projects and what his review says", [{S, D}, {G, D}], {S, G}),
    # ---- out of scope
    ("Hi! What's the weather like today?", set(), set()),
]


def predicted_set(a):
    return {s for s, flag in ((S, a["needs_sql"]), (G, a["needs_graph"]), (D, a["needs_documents"])) if flag}


def main():
    correct, per_source = 0, {s: {"tp": 0, "fp": 0, "fn": 0} for s in (S, G, D)}
    rows = []
    for i, (q, must, optional) in enumerate(TEST_SET, 1):
        a = analyze(q, link=False)
        pred = predicted_set(a)
        alternatives = must if isinstance(must, list) else [must]
        ok = any(m <= pred <= (m | optional) for m in alternatives)
        must = next((m for m in alternatives if m <= pred), alternatives[0])
        correct += ok
        for s in (S, G, D):
            if s in pred and s in must | optional:
                per_source[s]["tp"] += 1
            elif s in pred:
                per_source[s]["fp"] += 1
            elif s in must:
                per_source[s]["fn"] += 1
        exp = "+".join(sorted(must)) or "none"
        if optional:
            exp += " (+" + "/".join(sorted(optional)) + " ok)"
        rows.append((i, "OK " if ok else "XX ", a["route"], exp, a["intent"], q))
        print(f"  {i:>2}/{len(TEST_SET)} {'OK' if ok else 'XX'}  {a['route']:<20s} {q[:70]}")

    print("\n=== Routing results ===")
    for i, mark, route, exp, intent, q in rows:
        if mark.strip() == "XX":
            print(f"  wrong #{i}: predicted {route}, expected {exp}\n            {q}")
    print(f"\nRouting accuracy: {correct}/{len(TEST_SET)} = {100 * correct / len(TEST_SET):.0f}%")
    for s, c in per_source.items():
        p = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 0
        r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 0
        print(f"  {s:<10s} precision {p:.2f}  recall {r:.2f}")
    print(f"({llm.usage['calls']} LLM calls, {llm.usage['tokens']:,} tokens)")


if __name__ == "__main__":
    main()
