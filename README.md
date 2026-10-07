# Graph RAG-Based Intelligent HR Assistant

An AI assistant that answers HR questions in plain English by combining:
- a **PostgreSQL** database (employees, attendance, payroll, ratings) via Text-to-SQL,
- a **Neo4j knowledge graph** built from the database and from HR documents (LLM extraction),
- **semantic search** over HR policies, reviews, project reports and resumes.

Questions are routed to the right source(s), answered with citations, and checked for hallucinations.

CSD 415 Project - Team 11, Dept. of CSE, MITS Kochi (2023-2027 batch)
Joanne Alice Thomas, John Issac Meleth, Navneeth Byju - Guide: Neethu A S

## Pipeline
Question -> Query understanding + routing -> Text-to-SQL / Graph RAG retriever / document search
-> structured JSON context -> answer synthesis with citations -> grounding check

## Setup
    python -m venv venv
    .\venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env      # then fill in your own keys

## Run
    python -m src.check_connections        # Neon, Neo4j and Groq reachable?
    python -m src.pipeline --demo          # 5 sample questions
    python -m src.pipeline                 # interactive chat

## Build from scratch (only once, already done for the shared databases)
    python -m src.data_gen.generate_data
    python -m src.db.setup_db
    python -m src.graph.build_from_sql
    python -m src.graph.extract_from_docs
    python -m src.graph.load_extractions
    python -m src.graph.build_vectors
    python -m src.graph.build_concept_index

## Evaluation
    python -m src.graph.check_graph        # extraction precision / recall
    python -m src.agents.eval_router       # routing accuracy
    python -m src.agents.eval_sql          # Text-to-SQL execution accuracy
    python -m src.retrieval.eval_graph     # Graph RAG answer F1
