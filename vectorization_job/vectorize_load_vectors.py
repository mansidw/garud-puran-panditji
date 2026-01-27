import os
import re
import json
import psycopg2
from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

# 1. Setup Environment
load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
FILE_PATH = r"C://Users//Mansi//all//self//garud puran bot//data//garudapuran.pdf"

# Cleaning & Metadata Patterns
HEADER_STR = re.compile(r"The Essence of the Sacred Garuda Purana", re.IGNORECASE)
PAGE_NUM_PATTERN = re.compile(r"^\s*\d+\s*$", re.MULTILINE)
CHAPTER_PATTERN = re.compile(r"^(\d+)\.\s+([A-Z\s]{5,})")
SHLOK_PATTERN = re.compile(r"(Shlok\s+\d+[-–]?\d*)")


def process_pdf_to_chunks():
    print("--- Reading PDF ---")
    loader = PyPDFLoader(FILE_PATH)
    raw_docs = loader.load()

    current_chapter = "Front Matter"
    current_shlok = "Intro/Summary"
    processed_docs = []

    print("--- Cleaning & Extracting Citations ---")
    for doc in raw_docs:
        # Clean Content
        content = HEADER_STR.sub("", doc.page_content)
        content = PAGE_NUM_PATTERN.sub("", content)
        doc.page_content = re.sub(r"\n\s*\n", "\n\n", content).strip()

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
    return splitter.split_documents(processed_docs)


def main():
    # 2. Get Chunks
    chunks = process_pdf_to_chunks()

    # 3. Initialize Ollama
    print("--- Initializing Qwen3 Embeddings ---")
    embeddings_model = OllamaEmbeddings(model="qwen3-embedding")

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
