🕉️ Garuda Purana RAG Bot
An empathetic, AI-powered scholar specialized in the Garuda Purana, designed to provide citation-verified scriptural insights through a high-precision Retrieval-Augmented Generation (RAG) pipeline.

This project focuses on the theological preservation of ancient text, ensuring that AI responses are not just accurate in meaning, but also anchored to specific chapters and shlokas for academic and spiritual validity.

📖 Project Overview
Unlike generic RAG implementations, this system is engineered to handle the structured nature of religious scriptures. It transforms a raw PDF of the Garuda Purana into a "citation-friendly" vector corpus, allowing for a conversational interface that functions as a digital Vedic scholar.

The bot is designed to handle sensitive inquiries regarding life, death, and the afterlife with a tone that is both respectful and strictly grounded in the provided text.

🛠️ Key Engineering Features

1. Sectional Metadata Bifurcation
   The ingestion pipeline performs deep structural analysis of the text. It uses regex-based pattern matching to identify chapter transitions and shloka ranges. This metadata is "baked" into every text chunk, ensuring that the bot can provide precise "proof-giving" citations (Chapter, Shlok, and Page) for every claim it makes.

2. Automated Content Sanitization
   To ensure high embedding quality, the system dynamically strips repetitive running headers ("The Essence of the Sacred Garuda Purana") and standalone page numbers. This prevents "vector noise" and ensures the LLM focuses only on the actual theological discourse.

3. Hybrid Retrieval Engine
   The search layer utilizes a dual-engine approach within Supabase (pgvector):

Semantic Search: Uses local Qwen3 Embeddings to understand the conceptual meaning of a user's question.

Full-Text Search: Implements a Postgres GIN index for keyword-based ranking, ensuring that specific proper names and ritualistic terms (e.g., "Sudeva" or "Bhabruvahana") are never missed.

4. Parent-Document Context Expansion
   To prevent loss of context caused by arbitrary text splitting, the system employs an expansion logic. When a specific chunk is retrieved, the bot automatically fetches all neighboring chunks belonging to that same Shlok number. This provides the synthesis model with the full narrative flow rather than a fragmented snippet.

5. Empathetic Synthesis & Guardrails
   The final response layer is governed by a strict system prompt that enforces:

Zero-Inference: No usage of outside training data; responses are 100% grounded in the retrieved context.

Theological Persona: A wise, empathetic, and scholarly tone suited for scriptural discussion.

Polite Guardrails: Canned responses for out-of-scope queries or missing information to prevent hallucinations.

🏗️ Tech Stack
Language: Python

Framework: Flask (with threaded connection pooling)

Database: Supabase (PostgreSQL + pgvector)

Orchestration: LangChain

Embeddings: Ollama (qwen3-embedding)

Inference: Ollama (llama3 / qwen2.5)

Database Driver: psycopg2 for direct SQL and JSONB manipulation

🎯 Use Case
This repository serves as a blueprint for building high-accuracy RAG systems for complex, structured documents where citations, context integrity, and empathetic tone are non-negotiable requirements.
