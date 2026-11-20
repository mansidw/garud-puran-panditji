import os
import json
import time
import psycopg2
from psycopg2 import pool
from flask import Flask, request, jsonify
from langchain_ollama import OllamaEmbeddings
import ollama
from dotenv import load_dotenv

# custom imports
from prompts import get_main_agent_prompt

load_dotenv()

# Models can be overridden from .env so the same code works with llama3/qwen2.5/gemma3
EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding")
CHAT_MODEL = os.getenv("OLLAMA_CHAT_MODEL", "gemma3")

# Ollama defaults to a 2048-token context. The expanded parent-document context
# plus the system prompt is bigger than that, and when the prompt does not fit
# the model runner can crash mid-generation (the client then sees
# "wsarecv: An existing connection was forcibly closed by the remote host").
# So: raise the context window and cap how much context we send.
CHAT_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "4096"))
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "12000"))
CHAT_RETRIES = int(os.getenv("OLLAMA_CHAT_RETRIES", "1"))
# The ollama module's default client has NO timeout, so a wedged model runner
# makes the request hang forever. A finite timeout turns that into a retry.
OLLAMA_TIMEOUT = float(os.getenv("OLLAMA_TIMEOUT", "180"))
ollama_client = ollama.Client(timeout=OLLAMA_TIMEOUT)
# How long Ollama keeps the embedding model in memory after a request, in
# seconds (0 = unload immediately). qwen3-embedding is ~5.6 GB and gemma3 ~4.3 GB;
# on a machine with 16 GB RAM both loaded at once starves the model runner.
EMBEDDING_KEEP_ALIVE = int(os.getenv("OLLAMA_EMBEDDING_KEEP_ALIVE", "300"))

app = Flask(__name__)

# --- 1. Threaded Connection Pool ---
# This prevents bottlenecks by reusing a fixed set of connections.
# The pool is created lazily so the API can still boot (and answer /health)
# when the database is unreachable, instead of crashing at import time.
db_pool = None


def get_db_pool():
    global db_pool
    if db_pool is None:
        dsn = os.getenv("DATABASE_URL")
        if not dsn:
            raise RuntimeError(
                "DATABASE_URL is not set. Copy .env.example to .env and fill it in."
            )
        db_pool = psycopg2.pool.ThreadedConnectionPool(minconn=1, maxconn=20, dsn=dsn)
    return db_pool


# Initialize embeddings globally to avoid reloading for every request
embeddings_model = OllamaEmbeddings(
    model=EMBEDDING_MODEL, keep_alive=EMBEDDING_KEEP_ALIVE
)


def get_expanded_context(cursor, results):
    """Efficiently fetches full context for all top matches in one go."""
    if not results:
        return ""

    # Collect unique (chapter, shlok) pairs to avoid redundant database hits
    unique_refs = list(
        {(r[2].get("chapter_title"), r[2].get("shlok_reference")) for r in results}
    )

    # Batch query using tuple comparison (standard in Postgres)
    query = """
        SELECT metadata->>'chapter_title', metadata->>'shlok_reference', content
        FROM garudPuranDocuments
        WHERE (metadata->>'chapter_title', metadata->>'shlok_reference') IN %s
        ORDER BY id ASC;
    """

    cursor.execute(query, (tuple(unique_refs),))
    all_parts = cursor.fetchall()

    # Reconstruct shlokas into a dictionary for easy access
    shloka_map = {}
    for chap, shlok, text in all_parts:
        key = f"{chap} | {shlok}"
        shloka_map[key] = shloka_map.get(key, "") + " " + text

    return "\n".join([f"--- {k} ---\n{v}" for k, v in shloka_map.items()])


def ask_llm(system_prompt, user_message):
    """Call the local chat model, retrying once if the runner dies.

    Ollama can drop the connection (HTTP 500, 'An existing connection was
    forcibly closed by the remote host') when the model runner crashes - e.g.
    when the prompt overflows its context window on a GPU that is short on
    memory. That failure is transient: the next call reloads the model.
    """
    last_error = None
    for attempt in range(CHAT_RETRIES + 1):
        try:
            return ollama_client.chat(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                options={"num_ctx": CHAT_NUM_CTX},
            )
        except Exception as e:
            last_error = e
            print(f"Ollama call failed (attempt {attempt + 1}/{CHAT_RETRIES + 1}): {e}")
            if attempt < CHAT_RETRIES:
                time.sleep(2)  # give the runner a moment to restart
    raise last_error


@app.route("/health")
def health():
    """Readiness probe: verifies the DB (pgvector table) and Ollama are reachable."""
    status = {
        "service": "ok",
        "database": "unknown",
        "chunks": None,
        "ollama": "unknown",
        "embedding_model": EMBEDDING_MODEL,
        "chat_model": CHAT_MODEL,
    }
    http_status = 200

    try:
        pool_ = get_db_pool()
        conn = pool_.getconn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM garudPuranDocuments;")
            status["chunks"] = cursor.fetchone()[0]
            cursor.close()
            status["database"] = "up"
        except Exception:
            pool_.putconn(conn, close=True)
            raise
        else:
            pool_.putconn(conn)
    except Exception as e:
        status["database"] = f"down: {str(e).strip().splitlines()[0]}"
        http_status = 503

    try:
        tags = ollama.list()
        pulled = [m.get("model") or m.get("name") for m in tags.get("models", [])]
        status["ollama"] = "up"
        status["models_pulled"] = pulled
        for model in (EMBEDDING_MODEL, CHAT_MODEL):
            if not any(m and m.split(":")[0] == model for m in pulled):
                status["ollama"] = f"up (missing model: {model})"
                http_status = 503
    except Exception as e:
        status["ollama"] = f"down: {str(e).strip().splitlines()[0]}"
        http_status = 503

    return jsonify(status), http_status


@app.route("/api/chatbot")
def chatbot():
    user_question = request.args.get("question", "").strip()
    if not user_question:
        return jsonify({"error": "Question is required"}), 400

    conn = None
    pool_ = None
    healthy = False
    try:
        # Get a connection from the pool
        pool_ = get_db_pool()
        conn = pool_.getconn()
        cursor = conn.cursor()

        # 1. Vectorize and Hybrid Search
        query_vector = embeddings_model.embed_query(user_question)
        cursor.execute(
            """
            SELECT id, content, metadata, similarity 
            FROM hybrid_search_garud(%s::vector, %s::text, 0.2::float, 3::int);
        """,
            (query_vector, user_question),
        )

        search_results = cursor.fetchall()

        # 2. Optimized Context Expansion
        context_text = get_expanded_context(cursor, search_results)

        # Cap the context so the prompt always fits the model's context window
        if len(context_text) > MAX_CONTEXT_CHARS:
            context_text = context_text[:MAX_CONTEXT_CHARS].rsplit("\n", 1)[0]
            print(f"Context trimmed to {len(context_text)} chars for the LLM")

        # 3. Synthesis with Local LLM
        # The prompt remains the same as our previous design
        system_prompt = get_main_agent_prompt()
        user_message = f"CONTEXT FROM SACRED TEXT:\n{context_text}\n\nUSER QUESTION: {user_question}"

        response = ask_llm(system_prompt, user_message)

        healthy = True
        return jsonify(
            {
                "data": response["message"]["content"],
                "sources": [
                    {
                        "citation": f"{r[2].get('chapter_title')} | {r[2].get('shlok_reference')}",
                        "similarity": round(float(r[3]), 4),
                    }
                    for r in search_results
                ],
            }
        )

    except Exception as e:
        print(f"API Error: {e}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        # ALWAYS return the connection to the pool, even if an error occurs.
        # Broken connections are closed instead of being recycled.
        if conn and pool_:
            pool_.putconn(conn, close=not healthy)


if __name__ == "__main__":
    app.run(threaded=True, debug=True)  # Enables multi-threading in Flask
