"""
Step 7 check - answer accuracy of the Graph RAG retriever on 10 relationship questions.

The correct answers were computed directly from the generated data files (NOT from the
graph), so this measures the whole pipeline: LLM extraction (Step 3) + entity linking
(Step 5) + concept search + Text-to-Cypher (Step 7).

Per question: precision / recall / F1 of the returned names against the true names.
Question 3 is the one plain vector search failed in Step 4.

Run from the project root:  python -m src.retrieval.eval_graph   (about 20-30 Groq calls)
"""
from src import llm
from src.retrieval.graph_retriever import retrieve

GOLD = {
    'Who mentors Widisha Dubey?': [
        'Ladli Apte',
    ],
    'Which employees are recommended for promotion?': [
        'Arjun Choudhary', 'Azaan Murthy', 'Chaaya Kaul', 'Chakradhar Rai', 'Eesha Barman', 'Fitan Raghavan',
        'Gaurika Zacharia', 'Henry Krish', 'Januja Sen', 'Kevin Wable', 'Krisha Pingle', 'Nakul Lal',
        'Nirja Sarin', 'Pooja Lalla', 'Radhika Handa', 'Radhika Mohanty', 'Reva Pant', 'Reyansh Gupta',
        'Ryan Yadav',
    ],
    "Which projects are at risk because of problems with an external vendor's API?": [
        'Nimbus Mobile App', 'Vega Dashboard', 'Vega Migration', 'Zenith Data Lake', 'Zenith Migration',
    ],
    'Which employees want to move to the Data Science team?': [
        'Bhavika Nigam', 'Kevin Wable', 'Sudiksha Pathak',
    ],
    'Who in the Engineering department has leadership as a key strength?': [
        'Anya Sharaf', 'Faras Magar', 'Fariq Sami', 'Hardik Saini', 'Henry Krish', 'Idika Biswas',
        'Januja Amble', 'Jyoti Balay', 'Karan Tella', 'Kritika Loke', 'Lopa Kanda', 'Radhika Mohanty',
        'Siddharth Goswami', 'Tamanna Nori', 'Vanya Dey', 'Zarna Anand',
    ],
    'Which Data Science employees with a latest rating above 4 are mentoring someone?': [
        'Fitan Raghavan',
    ],
    'Which employees have been put on a performance improvement plan?': [
        'Aditya Choudhury', 'Anamika Narayanan', 'Anjali Chopra', 'Arya Zachariah', 'Bimala Varkey',
        'Champak Chatterjee', 'Chasmum Parmer', 'Daksha Rai', 'Damyanti Misra', 'Diya Mital',
        'Ekalinga Lalla', 'Falak Sani', 'Gaurav Tripathi', 'Hardik Saini', 'Jagat Gaba', 'Janani Bhardwaj',
        'Karan Tella', 'Kiaan Oak', 'Krishna Kar', 'Liam Panchal', 'Lohit Kade', 'Luke Sampath',
        'Mason Shankar', 'Nakul Rattan', 'Ojas De', 'Omaja Bhalla', 'Onkar Mall', 'Rajata Gaba', 'Rudra Deep',
        'Saksham Dar', 'Samar Dubey', 'Siddharth Goswami', 'Tamanna Nori', 'Upasna Boase', 'Upkaar Dara',
        'Vasana Aggarwal', 'Vivaan Wadhwa', 'Warda Kala', 'Yatin Chand', 'Zehaan Issac', 'Zilmil Acharya',
    ],
    'Who led the projects for Sunrise Bank?': [
        'Harish Sharma',
    ],
    "Which candidates have at least 3 skills that match the Aurora Chatbot project's tech stack?": [
        'Imaran Sura', 'Kamya Mukherjee', 'Tanveer Nagy', 'Vedant Deol',
    ],
    'Who received special recognition on ongoing projects?': [
        'Advaith Karpe', 'Anya Aggarwal', 'Falak Sani', 'Garima Kale', 'Harish Muni', 'Harish Sharma',
        'Januja Amble', 'Jason Gade', 'Jyoti Bir', 'Kritika Loke', 'Luke Sampath', 'Meghana Dugar',
        'Nakul Bora', 'Warda Kala',
    ],
}


def answer_values(rows):
    """All string values in the result rows (names, possibly inside lists)."""
    out = set()
    for row in rows:
        for v in row.values():
            for x in (v if isinstance(v, list) else [v]):
                if isinstance(x, str):
                    out.add(x.strip().lower())
    return out


def score(gold, rows):
    gold = {g.lower() for g in gold}
    if not rows:
        return 0.0, 0.0, 0.0
    # precision is measured on the column that best matches the gold answers
    best_col, best_overlap = None, -1
    for col in rows[0].keys():
        vals = {str(r[col]).strip().lower() for r in rows if isinstance(r.get(col), str)}
        if len(vals & gold) > best_overlap:
            best_col, best_overlap = vals, len(vals & gold)
    found = answer_values(rows)
    recall = len(gold & found) / len(gold)
    precision = len(best_col & gold) / len(best_col) if best_col else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return precision, recall, f1


def main():
    total_f1, exact = 0.0, 0
    for i, (question, gold) in enumerate(GOLD.items(), 1):
        res = retrieve(question)
        cy = res["cypher"]
        p, r, f = score(gold, cy["rows"]) if not cy["error"] else (0.0, 0.0, 0.0)
        total_f1 += f
        exact += f == 1.0
        print(f"  {i:>2}/{len(GOLD)} F1 {f:.2f} (P {p:.2f} R {r:.2f})  {question}")
        if f < 1.0:
            print(f"        cypher: {' '.join((cy['cypher'] or '').split())[:230]}")
            print(f"        returned {cy['row_count']} rows, expected {len(gold)} names"
                  + (f"; error: {cy['error']}" if cy["error"] else ""))
            if res["concepts"]:
                print("        concepts: " + ", ".join(f"{c['label']} '{c['name']}'" for c in res["concepts"][:3]))
    print(f"\nGraph RAG answer accuracy: mean F1 {total_f1 / len(GOLD):.2f}, "
          f"exactly right {exact}/{len(GOLD)}")
    print(f"({llm.usage['calls']} LLM calls, {llm.usage['tokens']:,} tokens)")


if __name__ == "__main__":
    main()
