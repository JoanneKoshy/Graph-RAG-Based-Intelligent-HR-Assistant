"""Central settings, read from the .env file in the project root."""
import os
from pathlib import Path

from dotenv import load_dotenv
from psycopg.conninfo import make_conninfo

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

DATA_RAW = ROOT / "data" / "raw"
DATA_DOCS = ROOT / "data" / "docs"
DATA_EXTRACTED = ROOT / "data" / "extracted"
DATA_TRUTH = ROOT / "data" / "ground_truth"

# ---------------------------------------------------------------- PostgreSQL (Neon)
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_SSLMODE = os.getenv("PG_SSLMODE", "prefer")   # Neon needs "require"
PG_DB = os.getenv("PG_DB", "hr_db")
PG_ADMIN_USER = os.getenv("PG_ADMIN_USER", "postgres")
PG_ADMIN_PASSWORD = os.getenv("PG_ADMIN_PASSWORD", "")
PG_READONLY_USER = os.getenv("PG_READONLY_USER", "hr_readonly")
PG_READONLY_PASSWORD = os.getenv("PG_READONLY_PASSWORD", "readonly123")

# ---------------------------------------------------------------- Neo4j (AuraDB)
NEO4J_URI = os.getenv("NEO4J_URI", "neo4j://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE") or None   # None = the instance's default database

# ---------------------------------------------------------------- Groq LLM
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")


def pg_conninfo(db=PG_DB, readonly=False):
    user, pwd = (PG_READONLY_USER, PG_READONLY_PASSWORD) if readonly else (PG_ADMIN_USER, PG_ADMIN_PASSWORD)
    # make_conninfo quotes values safely, so passwords with spaces or symbols work
    return make_conninfo(host=PG_HOST, port=PG_PORT, dbname=db, user=user, password=pwd,
                         sslmode=PG_SSLMODE)
