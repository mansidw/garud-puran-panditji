import os
import psycopg2
import json
from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")


def get_full_shlok_context(cursor, shlok_ref, chapter_title):
    """Fetches all chunks belonging to a specific Shlok to provide full context."""
    # We filter by both Chapter and Shlok to avoid matching 'Shlok 1-5' from different chapters
    cursor.execute(
        """
        SELECT content 
        FROM garudPuranDocuments
        WHERE metadata->>'shlok_reference' = %s 
          AND metadata->>'chapter_title' = %s
        ORDER BY id ASC; 
    """,
        (shlok_ref, chapter_title),
    )

    parts = cursor.fetchall()
    return " ".join([p[0] for p in parts])


def verify_expanded_retrieval(user_question):
    embeddings_model = OllamaEmbeddings(model="qwen3-embedding")
    query_vector = embeddings_model.embed_query(user_question)

    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # 1. Hybrid Search for the most relevant starting point
        cursor.execute(
            """
            SELECT content, metadata, similarity 
            FROM hybrid_search_garud(%s::vector, %s::text, 0.2::float, 3::int);
        """,
            (query_vector, user_question),
        )

        results = cursor.fetchall()

        print(f"\n--- Expanded Context Results for: {user_question} ---")

        expanded_contexts = []
        for i, row in enumerate(results):
            metadata = row[1]
            shlok_ref = metadata.get("shlok_reference")
            chapter = metadata.get("chapter_title")

            # 2. Context Expansion Step
            full_text = get_full_shlok_context(cursor, shlok_ref, chapter)

            expanded_contexts.append(
                {"citation": f"{chapter}, {shlok_ref}", "full_text": full_text}
            )

            print(f"\n[Result {i+1}] Source: {chapter} | {shlok_ref}")
            print(f"Full Context Length: {len(full_text)} characters")
            print(f"Snippet: {full_text[:300]}...")

        return expanded_contexts

    except Exception as e:
        print(f"Error during expanded retrieval: {e}")
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


# Test the expanded logic
# verify_expanded_retrieval(
#     "What are the duties of a son when a parent is on their death bed?"
# )
# Test with a keyword-heavy question
# verify_expanded_retrieval("Who is Sudeva and how did Bhabruvahana help him?")
# verify_expanded_retrieval("When does a person become an ant in next life?")
# verify_expanded_retrieval(
#     "The pinds that are created for shraddha rituals are made up of what material?"
# )
verify_expanded_retrieval("Can the girls perform shraddha?")
