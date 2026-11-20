import os
import re
import sys
import json
import psycopg2
from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 1. Setup Environment
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "qwen3-embedding")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILE_PATH = os.getenv("PDF_PATH") or os.path.join("data", "garudapuran.pdf")
if not os.path.isabs(FILE_PATH):
    FILE_PATH = os.path.join(BASE_DIR, FILE_PATH)

# Cleaning & Metadata Patterns
HEADER_STR = re.compile(r"The Essence of the Sacred Garuda Purana", re.IGNORECASE)
PAGE_NUM_PATTERN = re.compile(r"^\s*\d+\s*$", re.MULTILINE)
CHAPTER_PATTERN = re.compile(r"^(\d+)\.\s+([A-Z\s]{5,})")
SHLOK_PATTERN = re.compile(r"(Shlok\s+\d+[-–]?\d*)")


def process_pdf_to_chunks():
    print(f"--- Reading PDF: {FILE_PATH} ---")
    loader = PyPDFLoader(FILE_PATH)
    raw_docs = loader.load()

    current_chapter = "Front Matter"
    current_shlok = "Intro/Summary"
    processed_docs = []
    skipped = 0

    print("--- Cleaning & Extracting Citations ---")
    for doc in raw_docs:
        # Clean Content
        content = HEADER_STR.sub("", doc.page_content)
        content = PAGE_NUM_PATTERN.sub("", content)
        doc.page_content = re.sub(r"\n\s*\n", "\n\n", content).strip()

        # Skip scanned/image-only pages (the 5 "Garuda Purana part *.pdf" files
        # contain no extractable text and would only add empty chunks).
        if not doc.page_content:
            skipped += 1
            continue

        # Track Chapter and Shlok context
        for line in doc.page_content.split("\n"):
            chap_match = CHAPTER_PATTERN.match(line.strip())
            if chap_match:
                current_chapter = (
                    f"Chapter {chap_match.group(1)}: {chap_match.group(2).strip()}"
                )
            shlok_match = SHLOK_PATTERN.search(line.strip())
            if shlok_match:
                current_shlok = shlok_match.group(1)

        doc.metadata.update(
            {"chapter_title": current_chapter, "shlok_reference": current_shlok}
        )
        processed_docs.append(doc)

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    chunks = splitter.split_documents(processed_docs)
    print(f"--- {len(raw_docs)} pages read, {skipped} empty pages skipped -> {len(chunks)} chunks ---")
    return chunks


def dry_run_report(chunks):
    """Prints what would be ingested without touching Ollama or the database."""
    from collections import Counter

    chapters = Counter((c.metadata.get("chapter_title") or "?") for c in chunks)
    shloks = Counter((c.metadata.get("shlok_reference") or "?") for c in chunks)
    print(f"\n--- DRY RUN ---")
    print(f"Total chunks: {len(chunks)}")
    print(f"Distinct chapters: {len(chapters)}")
    print(f"Distinct shlok references: {len(shloks)}")
    print(f"Avg chunk length: {sum(len(c.page_content) for c in chunks) // max(len(chunks), 1)} chars")
    print("\nChapters found:")
    for title, count in chapters.most_common():
        print(f"  {count:4d} chunks | {title}")
    print("\nFirst chunk preview:")
    print(chunks[0].page_content[:400])
    print(f"\nMetadata: {chunks[0].metadata}")
    print("\nNo embeddings generated, nothing written to the database.")


def main():
    dry_run = "--dry-run" in sys.argv[1:]

    if not os.path.exists(FILE_PATH):
        raise SystemExit(f"PDF not found: {FILE_PATH}")

    # 2. Get Chunks
    chunks = process_pdf_to_chunks()

    if dry_run:
        dry_run_report(chunks)
        return

    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is not set. Copy .env.example to .env first.")

    # 3. Initialize Ollama
    print(f"--- Initializing embeddings ({EMBEDDING_MODEL}) ---")
    embeddings_model = OllamaEmbeddings(model=EMBEDDING_MODEL)

    conn = None
    cursor = None

    # 4. Connect and Store via psycopg2
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        print("Connection to Supabase (psycopg2): SUCCESS")

        print(f"--- Processing {len(chunks)} chunks ---")
        for i, chunk in enumerate(chunks):
            # Generate Embedding locally
            vector = embeddings_model.embed_query(chunk.page_content)

            # Prepare SQL
            # table structure: content (TEXT), metadata (JSONB), embedding (VECTOR)
            query = """
                INSERT INTO garudPuranDocuments (content, metadata, embedding)
                VALUES (%s, %s, %s);
            """

            # Execute
            cursor.execute(
                query, (chunk.page_content, json.dumps(chunk.metadata), vector)
            )

            if (i + 1) % 10 == 0:
                print(f"Stored {i + 1} chunks...")

        conn.commit()
        print("--- Transaction Committed Successfully ---")

    except Exception as e:
        print(f"Database Error: {e}")
        if conn:
            conn.rollback()
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
