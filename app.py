import os
import json
import psycopg2
from psycopg2 import pool
from flask import Flask, request, jsonify
from langchain_ollama import OllamaEmbeddings
import ollama
from dotenv import load_dotenv

# custom imports
from prompts import get_main_agent_prompt

load_dotenv()

app = Flask(__name__)

# --- 1. Threaded Connection Pool ---
# This prevents bottlenecks by reusing a fixed set of connections.
db_pool = psycopg2.pool.ThreadedConnectionPool(
    minconn=1, maxconn=20, dsn=os.getenv("DATABASE_URL")  # Adjust based on your CPU/RAM
)

# Initialize embeddings globally to avoid reloading for every request
embeddings_model = OllamaEmbeddings(model="qwen3-embedding")


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


@app.route("/api/chatbot")
def chatbot():
    user_question = request.args.get("question", "")
    if not user_question:
        return jsonify({"error": "Question is required"}), 400

    conn = None
    try:
        # Get a connection from the pool
        conn = db_pool.getconn()
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

        # 3. Synthesis with Local LLM
        # The prompt remains the same as our previous design
        system_prompt = get_main_agent_prompt()
        user_message = f"CONTEXT FROM SACRED TEXT:\n{context_text}\n\nUSER QUESTION: {user_question}"

        response = ollama.chat(
            model="gemma3",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
        )

        return jsonify({"data": response["message"]["content"]})

    except Exception as e:
        print(f"API Error: {e}")
        return jsonify({"error": "Internal server error"}), 500
    finally:
        # ALWAYS return the connection to the pool, even if an error occurs
        if conn:
            db_pool.putconn(conn)


if __name__ == "__main__":
    app.run(threaded=True, debug=True)  # Enables multi-threading in Flask
