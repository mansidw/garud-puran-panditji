from langchain_community.document_loaders import PyPDFLoader
import re
from langchain_text_splitters import RecursiveCharacterTextSplitter

file_path = "C:\\Users\\Mansi\\all\\self\\garud puran bot\\data\\garudapuran.pdf"
loader = PyPDFLoader(file_path)

# 1. Patterns for cleaning
# Matches the specific header text regardless of case
HEADER_STR = re.compile(r"The Essence of the Sacred Garuda Purana", re.IGNORECASE)
# Matches standalone numbers at the start of lines (often page numbers in this PDF)
PAGE_NUM_PATTERN = re.compile(r"^\s*\d+\s*$", re.MULTILINE)
# 1. Prepare Regex Patterns based on your PDF structure
CHAPTER_PATTERN = re.compile(
    r"^(\d+)\.\s+([A-Z\s]{5,})"
)  # Matches "1. THE EIGHTEEN PURANAS"
SHLOK_PATTERN = re.compile(r"(Shlok\s+\d+[-–]?\d*)")  # Matches "Shlok 1-5"


def process_and_clean_docs(docs):
    current_chapter = "Front Matter"
    current_shlok = "Intro/Summary"

    cleaned_docs = []

    for doc in docs:
        content = doc.page_content

        # --- CLEANING STEP ---
        # Remove the repetitive title header
        content = HEADER_STR.sub("", content)
        # Remove standalone page numbers
        content = PAGE_NUM_PATTERN.sub("", content)
        # Clean up excessive whitespace left behind
        content = re.sub(r"\n\s*\n", "\n\n", content).strip()

        # Update the document content
        doc.page_content = content

        # --- METADATA STEP ---
        lines = content.split("\n")
        for line in lines:
            line = line.strip()
            # Detect Chapter: e.g., "2. YAMA'S ABODE" [cite: 192]
            chap_match = CHAPTER_PATTERN.match(line)
            if chap_match:
                current_chapter = (
                    f"Chapter {chap_match.group(1)}: {chap_match.group(2).strip()}"
                )

            # Detect Shlok: e.g., "Shlok 8-12" [cite: 107]
            shlok_match = SHLOK_PATTERN.search(line)
            if shlok_match:
                current_shlok = shlok_match.group(1)

        doc.metadata["chapter_title"] = current_chapter
        doc.metadata["shlok_reference"] = current_shlok
        cleaned_docs.append(doc)

    return cleaned_docs


# Run the process
docs = loader.load()
enriched_docs = process_and_clean_docs(docs)

# 2. Split with Metadata Preservation
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800,
    chunk_overlap=100,
    separators=["\n\n", "\n", " ", ""],
    add_start_index=True,
)

# Every chunk created here will inherit the 'chapter_title' and 'shlok_reference'
final_chunks = text_splitter.split_documents(enriched_docs)

for i in final_chunks[
    len(final_chunks) - 5 : len(final_chunks)
]:  # Print first 5 chunks for verification
    print(i.page_content)
    print(i.metadata)
    print("-----")
