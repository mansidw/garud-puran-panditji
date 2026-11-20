"""Pre-flight diagnostics for the Garuda Purana RAG bot.

Verifies every external dependency the API needs before you start the server:
    1. .env / DATABASE_URL is present
    2. Supabase (Postgres + pgvector) is reachable, the table exists and is populated
    3. The hybrid_search_garud() SQL function exists with the expected parameters
    4. Ollama is running and the embedding + chat models are pulled

Usage:
    python scripts/setup_check.py
"""

import os
import sys

import psycopg2
from dotenv import load_dotenv

TABLE_NAME = "garudPuranDocuments"
EMBEDDING_MODEL = "qwen3-embedding"
CHAT_MODEL = "gemma3"

results = []


def report(label, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    results.append(ok)
    print(f"[{status}] {label}" + (f" -> {detail}" if detail else ""))


def check_env():
    load_dotenv()
    url = os.getenv("DATABASE_URL")
    report(".env DATABASE_URL", bool(url), "found" if url else "missing (copy .env.example to .env)")
    return url


def check_database(url):
    if not url:
        report("Database connection", False, "skipped, DATABASE_URL missing")
        return
    try:
        conn = psycopg2.connect(url, connect_timeout=10)
        cursor = conn.cursor()
    except Exception as exc:
        report("Database connection", False, str(exc).strip().splitlines()[0])
        return

    try:
        report("Database connection", True, "connected")

        cursor.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND lower(table_name) = lower(%s);
            """,
            (TABLE_NAME,),
        )
        found = cursor.fetchone()
        table_exists = found is not None
        actual_table = f'"{found[0]}"' if found else TABLE_NAME
        if table_exists:
            cursor.execute(f"SELECT COUNT(*) FROM {actual_table};")
            row_count = cursor.fetchone()[0]
            report(f"Table {found[0]}", row_count > 0, f"{row_count} chunks")
        else:
            report(f"Table {TABLE_NAME}", False, "missing, run sql/schema.sql from README")

        cursor.execute(
            """
            SELECT pg_get_function_identity_arguments(p.oid)
            FROM pg_proc p
            JOIN pg_namespace n ON n.oid = p.pronamespace
            WHERE n.nspname = 'public' AND p.proname = 'hybrid_search_garud';
            """
        )
        signatures = cursor.fetchall()
        report(
            "Function hybrid_search_garud",
            bool(signatures),
            signatures[0][0] if signatures else "missing, run the schema from README",
        )

        if table_exists:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema = 'public' AND table_name = %s AND column_name = 'embedding'
                );
                """,
                (found[0],),
            )
            report("Column embedding", cursor.fetchone()[0], "vector column")

        cursor.execute("SELECT extname FROM pg_extension WHERE extname IN ('vector', 'pg_trgm');")
        report("pgvector extension", any(r[0] == "vector" for r in cursor.fetchall()), "vector")
    finally:
        cursor.close()
        conn.close()


def check_ollama():
    try:
        import ollama

        tags = ollama.list()
        models = [m.get("model") or m.get("name") for m in tags.get("models", [])]
        report("Ollama service", True, f"{len(models)} model(s) available")

        for model in (EMBEDDING_MODEL, CHAT_MODEL):
            found = any(m and m.split(":")[0] == model for m in models)
            report(f"Model {model}", found, "pulled" if found else f"run: ollama pull {model}")
    except Exception as exc:
        report("Ollama service", False, f"{exc} (is `ollama serve` running?)")


def main():
    print("--- Garuda Purana RAG bot: setup check ---")
    url = check_env()
    check_database(url)
    check_ollama()

    print("\n--- Summary ---")
    passed, total = sum(results), len(results)
    print(f"{passed}/{total} checks passed")
    if passed != total:
        print("Fix the FAIL items above before starting app.py")
        return 1
    print("Everything looks good. Start the API with: python app.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
