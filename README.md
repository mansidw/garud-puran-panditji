# 🕉️ Garuda Purana RAG Bot

An empathetic, AI-powered scholar specialized in the Garuda Purana, designed to provide citation-verified scriptural insights through a high-precision Retrieval-Augmented Generation (RAG) pipeline.

This project focuses on the theological preservation of ancient text, ensuring that AI responses are not just accurate in meaning, but also anchored to specific chapters and shlokas for academic and spiritual validity.

## 📖 Project Overview
Unlike generic RAG implementations, this system is engineered to handle the structured nature of religious scriptures. It transforms a raw PDF of the Garuda Purana into a "citation-friendly" vector corpus, allowing for a conversational interface that functions as a digital Vedic scholar.

The bot is designed to handle sensitive inquiries regarding life, death, and the afterlife with a tone that is both respectful and strictly grounded in the provided text.

## 🚦 Implementation Status

Audited on 20 Nov 2026 against the code in this repository.

| Component | Status | Where / Notes |
| --- | --- | --- |
| PDF text extraction + sanitization | ✅ Done | `vectorization_job/vectorize_load_vectors.py`, `extra/pdfLoader.py`. Verified: 65 pages → 227 chunks, 0 empty pages |
| Chapter / Shlok metadata bifurcation | ⚠️ Partial | Regex works for 16 chapters + 52 shlok refs, but chapter titles that wrap onto a second line are cut short (e.g. `Chapter 15: PROGRESS TOWARDS THE`) |
| Extracted-text encoding | ⚠️ Partial | The source PDF's typographic quotes come out as `ô ... ö` / `û` in a few chunks, so the LLM occasionally echoes them. Cosmetic only; see [Troubleshooting](#-troubleshooting) |
| Embedding generation (`qwen3-embedding`, 4096-d) | ✅ Done | Sequential, one embedding per chunk (slow but reliable) |
| Vector upload to Supabase | ✅ Done | `INSERT` via psycopg2. **Index already populated: 227 chunks** |
| Database schema (table + `hybrid_search_garud()`) | ✅ Verified | `sql/schema.sql` was missing from the repo; it is now an exact, idempotent copy of the live objects (table with generated `fts tsvector`, 4 indexes, retrieval function) |
| Hybrid retrieval (semantic + full-text) | ✅ Done | `0.5 × cosine + 0.5 × ts_rank_cd` (weights are function defaults), min semantic 0.2, top 3 |
| Parent-document context expansion | ✅ Done | `get_expanded_context()` in `app.py` |
| Guardrails / empathetic system prompt | ✅ Done | `prompts.py` |
| Flask chat API | ✅ Done | `GET /api/chatbot` |
| Health / readiness endpoint | ✅ Added | `GET /health` (checks DB + Ollama + indexed chunk count) |
| Pre-flight + end-to-end test scripts | ✅ Added | `scripts/setup_check.py`, `scripts/smoke_test.py` |
| Dependency manifest | ✅ Added | `requirements.txt` (previously the only copy of the dependency set was the local `env/` folder) |
| Front-end / chat UI | ❌ Not implemented | HTTP JSON API only |
| Conversation memory (multi-turn) | ❌ Not implemented | Every request is stateless/single-turn |
| Auth, CORS, rate limiting, streaming | ❌ Not implemented | — |
| Automated unit tests / CI | ❌ Not implemented | Only manual smoke scripts; no `pytest` suite, no GitHub Actions |
| OCR for the scanned books | ❌ Not implemented | `data/Garuda Purana part 1-5.pdf` are image-only scans (0 extractable characters), so they are currently unusable by this pipeline |
| Containerization / deployment | ❌ Not implemented | No `Dockerfile`, no hosting config |

### Corpus currently used

Only `data/garudapuran.pdf` is ingested — *"The Essence of the Sacred Garuda Purana"*, Dr. V.V.B. Rama Rao, TTD 2015 (65 pages, ~174k characters of extractable text). The five `Garuda Purana part *.pdf` files are pure scans and would need an OCR step (e.g. Tesseract) before they could be added.

### Live verification (21 Nov 2026)

| Check | Result |
| --- | --- |
| `python scripts/setup_check.py` | 9/9 passed — DB reachable, `garudpurandocuments` holds **227 chunks**, `hybrid_search_garud` + pgvector present, Ollama up with both models pulled |
| `GET /health` | `200` → `{"database": "up", "chunks": 227, "ollama": "up", ...}` |
| `GET /api/chatbot` (no question) | `400` |
| `scripts/smoke_test.py` (3 questions) | **14/14 checks → 0 failed**; all three answers `200` with citations — e.g. *“When does a person become an ant in the next life?”* → `Chapter 5: MARKS ON SINNERS \| Shlok 48-57`; *“What material are the pinds … made of?”* → `Chapter 12: ELEVENTH \| Shlok 57-72` |
| Answer latency | 64–88 s per answer on a 16 GB laptop with an **integrated Intel Arc GPU**; the first request after a cold start can take several minutes because Ollama has to load a model and only one fits in memory at a time |

## 📦 Repository Structure

```
app.py                                  # Flask API: hybrid search -> context expansion -> LLM answer
prompts.py                              # System prompt (persona, zero-inference, canned refusal)
requirements.txt                        # Python dependencies
.env.example                            # Template for the required environment variables
sql/schema.sql                          # pgvector table, indexes and hybrid_search_garud()
scripts/setup_check.py                  # Pre-flight: .env, DB, table, function, Ollama, models
scripts/smoke_test.py                   # End-to-end test against a running API
vectorization_job/vectorize_load_vectors.py   # PDF -> clean chunks -> embeddings -> Supabase (--dry-run supported)
vectorization_job/validation_script.py        # Retrieval-only debugger (no LLM call)
extra/                                  # Early scratch scripts kept for reference (not used by the API)
data/                                   # Source PDFs (one text PDF + five image-only scans)
```

## 🛠️ Key Engineering Features

### 1. Sectional Metadata Bifurcation
   The ingestion pipeline performs deep structural analysis of the text. It uses regex-based pattern matching to identify chapter transitions and shloka ranges. This metadata is "baked" into every text chunk, ensuring that the bot can provide precise "proof-giving" citations (Chapter, Shlok, and Page) for every claim it makes.

### 2. Automated Content Sanitization
   To ensure high embedding quality, the system dynamically strips repetitive running headers ("The Essence of the Sacred Garuda Purana") and standalone page numbers. This prevents "vector noise" and ensures the LLM focuses only on the actual theological discourse.

### 3. Hybrid Retrieval Engine
   The search layer utilizes a dual-engine approach within Supabase (pgvector):

   * **Semantic Search:** Uses local Qwen3 Embeddings to understand the conceptual meaning of a user's question.
   * **Full-Text Search:** Implements a Postgres GIN index for keyword-based ranking, ensuring that specific proper names and ritualistic terms (e.g., "Sudeva" or "Bhabruvahana") are never missed.

### 4. Parent-Document Context Expansion
   To prevent loss of context caused by arbitrary text splitting, the system employs an expansion logic. When a specific chunk is retrieved, the bot automatically fetches all neighboring chunks belonging to that same Shlok number. This provides the synthesis model with the full narrative flow rather than a fragmented snippet.

### 5. Empathetic Synthesis & Guardrails
   The final response layer is governed by a strict system prompt that enforces:

   * **Zero-Inference:** No usage of outside training data; responses are 100% grounded in the retrieved context.
   * **Theological Persona:** A wise, empathetic, and scholarly tone suited for scriptural discussion.
   * **Polite Guardrails:** Canned responses for out-of-scope queries or missing information to prevent hallucinations.

## 🏗️ Tech Stack
* **Language:** Python
* **Framework:** Flask (with threaded connection pooling)
* **Database:** Supabase (PostgreSQL + pgvector)
* **Orchestration:** LangChain
* **Embeddings:** Ollama (qwen3-embedding)
* **Inference:** Ollama (llama3 / qwen2.5)
* **Database Driver:** psycopg2 for direct SQL and JSONB manipulation

## 🎯 Use Case
This repository serves as a blueprint for building high-accuracy RAG systems for complex, structured documents where citations, context integrity, and empathetic tone are non-negotiable requirements.

---

# 🏃 How to Run

## ✅ Prerequisites

| Requirement | Version used | Notes |
| --- | --- | --- |
| Python | 3.11 | `python --version` |
| [Ollama](https://ollama.com) | 0.17.x | Must be running locally (`ollama serve` or the desktop app) |
| Embedding model | `qwen3-embedding` (4,096 dims) | `ollama pull qwen3-embedding` |
| Chat model | `gemma3` (default), `llama3`/`qwen3` work too | `ollama pull gemma3` |
| PostgreSQL | Supabase project with `vector` + `pg_trgm` extensions | Free tier is enough |

## ⚙️ Setup (5 minutes)

**1. Create and activate the virtual environment**

```powershell
# Windows (PowerShell)
python -m venv env
.\env\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# macOS / Linux
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

> If `psycopg2` fails to build on Windows, install `psycopg2-binary==2.9.11` instead.

**2. Configure the environment**

```powershell
Copy-Item .env.example .env
notepad .env        # set DATABASE_URL (Supabase -> Project Settings -> Database)
```

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `DATABASE_URL` | ✅ | — | Postgres/Supabase connection string |
| `OLLAMA_EMBEDDING_MODEL` | ❌ | `qwen3-embedding` | Must match `vector(N)` in `sql/schema.sql` |
| `OLLAMA_CHAT_MODEL` | ❌ | `gemma3` | Synthesis model |
| `OLLAMA_NUM_CTX` | ❌ | `4096` | Context window for the chat model (Ollama's default of 2048 is too small for the expanded context) |
| `MAX_CONTEXT_CHARS` | ❌ | `12000` | Cap on the retrieved context sent to the LLM (≈4 chars/token) |
| `OLLAMA_CHAT_RETRIES` | ❌ | `1` | Retries after a crashed Ollama call (the next call reloads the model) |
| `OLLAMA_TIMEOUT` | ❌ | `180` | Seconds before an LLM call is abandoned (the ollama module's default client waits forever) |
| `PDF_PATH` | ❌ | `data/garudapuran.pdf` | Source PDF for ingestion |

**3. Create the database objects** (table, indexes, `hybrid_search_garud()`)

> ⏭️ **Already have data?** If your database still holds the ingested chunks (step 4 will show `227 chunks`), **skip this step and step 5** — the table, indexes and function already exist, so there is nothing to create and no reason to re-embed anything. Just go to step 4 and start the API.

```powershell
psql $env:DATABASE_URL -f sql/schema.sql
```

…or paste the whole of [`sql/schema.sql`](sql/schema.sql) into the Supabase **SQL Editor** and run it.
The script is an idempotent copy of the live objects (`create table if not exists`, `create index if not exists`, `create or replace function`), so re-running it is a no-op — it will not touch existing rows.

**4. Verify everything before starting the server**

```powershell
python scripts\setup_check.py
```

Real output on a healthy machine:

```
--- Garuda Purana RAG bot: setup check ---
[PASS] .env DATABASE_URL -> found
[PASS] Database connection -> connected
[PASS] Table garudpurandocuments -> 227 chunks
[PASS] Function hybrid_search_garud -> query_embedding vector, query_text text, match_threshold double precision, match_count integer, full_text_weight double precision, vector_weight double precision
[PASS] Column embedding -> vector column
[PASS] pgvector extension -> vector
[PASS] Ollama service -> 6 model(s) available
[PASS] Model qwen3-embedding -> pulled
[PASS] Model gemma3 -> pulled

--- Summary ---
9/9 checks passed
Everything looks good. Start the API with: python app.py
```

## 📚 Build (or rebuild) the vector index

> ℹ️ **You normally do not need this section.** The reference database already contains all **227 chunks** (verified — see `scripts/setup_check.py`). Only run these commands on a brand-new/empty database, or after changing the PDF, the cleaner or the chunking logic. Re-ingesting into a non-empty table appends duplicates.

Always dry-run first — it parses, cleans and chunks the PDF **without** calling Ollama or the database:

```powershell
python vectorization_job\vectorize_load_vectors.py --dry-run
```

```
--- Reading PDF: ...\data\garudapuran.pdf ---
--- Cleaning & Extracting Citations ---
--- 65 pages read, 0 empty pages skipped -> 227 chunks ---

--- DRY RUN ---
Total chunks: 227
Distinct chapters: 16
Distinct shlok references: 52
Avg chunk length: 823 chars

Chapters found:
    29 chunks | Chapter 1: THE EIGHTEEN PURANAS
    25 chunks | Chapter 16: THE ETERNAL LIBERATION
    ...
No embeddings generated, nothing written to the database.
```

Then embed and upload (needs Ollama running and `DATABASE_URL` set; ~227 embedding calls, a few minutes on CPU):

```powershell
python vectorization_job\vectorize_load_vectors.py
```

To re-ingest from scratch (otherwise rows are appended and you get duplicates):

```sql
truncate table garudPuranDocuments restart identity;
```

## ▶️ Run the API

```powershell
python app.py
```

* Listens on **http://127.0.0.1:5000**
* `debug=True` enables the auto-reloader — use it for development only. For anything shareable:

```powershell
flask --app app run --host 0.0.0.0 --port 8000        # or: waitress-serve --port=8000 app:app
```


# 🧪 How to Test

Four levels, cheapest first. All are optional for a demo, but they localize a failure in seconds.

### 1. Health probe — "is anything up?"

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health | ConvertTo-Json
```

```bash
curl -s http://127.0.0.1:5000/health | jq
```

`HTTP 200` when both the database and Ollama are ready, `503` when something is missing:

```json
{
  "service": "ok",
  "database": "up",
  "chunks": 227,
  "ollama": "up",
  "embedding_model": "qwen3-embedding",
  "chat_model": "gemma3",
  "models_pulled": ["qwen3:8b", "qwen3-embedding:latest", "gemma3:latest", "..."]
}
```

Because the connection pool is created lazily, the server now boots even when the database is
down — `/health` reports `"database": "down: could not translate host name ..."` instead of the
process crashing on import.

### 2. Retrieval only — "does the RAG pipeline find the right shlokas?" (no LLM, seconds)

```powershell
python vectorization_job\validation_script.py "Can the girls perform shraddha?"
python vectorization_job\validation_script.py "Who is Sudeva and how did Bhabruvahana help him?"
```

Prints the hybrid-search hits plus the expanded parent-document text, so chunking and metadata
quality can be checked before blaming the model:

```
--- Expanded Context Results for: Can the girls perform shraddha? ---
[Result 1] Source: Chapter 8: PIOUS OBLIGATIONS | Shlok 12-15
Full Context Length: 1842 characters
Snippet: ...
```


### 3. End-to-end smoke test — "does the whole chain work?"

With `python app.py` already running in another terminal:

```powershell
python scripts\smoke_test.py
python scripts\smoke_test.py "When does a person become an ant in the next life?"
```

It checks the following and exits non-zero on any failure:

| Check | Expected |
| --- | --- |
| `GET /health` reachable | 200 or 503 |
| database + indexed chunks | `"up"`, chunks > 0 |
| Ollama + required models | `"up"` |
| `GET /api/chatbot` without `question` | 400 |
| `GET /api/chatbot?question=...` | 200, non-empty `data`, non-empty `sources` |

Override the target with environment variables: `BOT_BASE_URL` (default `http://127.0.0.1:5000`)
and `BOT_TIMEOUT` (default 300 s — local LLMs are slow; on a CPU-only or integrated-GPU
machine a single answer can take several minutes, so raise it with `BOT_TIMEOUT=900`).

### 4. Manual API call

```powershell
Invoke-RestMethod "http://127.0.0.1:5000/api/chatbot?question=What%20happens%20to%20the%20soul%20after%20death%3F" | ConvertTo-Json -Depth 5
```

```bash
curl -G "http://127.0.0.1:5000/api/chatbot" --data-urlencode "question=What happens to the soul after death?"
```

```json
{
  "data": "According to the teachings, the soul initially takes a thumb-sized form (Source: Chapter 1, Shlok 30-33).",
  "sources": [
    {"citation": "Chapter 1: THE EIGHTEEN PURANAS | Shlok 30-33", "similarity": 0.81}
  ]
}
```

### What "passing" looks like

* The answer cites a **chapter and shlok** and uses nothing but the retrieved context.
* Out-of-scope questions (`"how do I sort a list in Python?"`) return the canned refusal from `prompts.py` instead of an invented answer.
* `sources` is non-empty — an empty list means retrieval found nothing (usually an empty table or a failed ingest).


## 📡 API Reference

| Endpoint | Method | Params | Responses |
| --- | --- | --- | --- |
| `/health` | GET | — | `200` all dependencies up · `503` DB and/or Ollama down (body says which) |
| `/api/chatbot` | GET | `question` (required) | `200 {data, sources[]}` · `400 {"error": "Question is required"}` · `500 {"error": "Internal server error"}` |

## 🩺 Troubleshooting

| Symptom | Cause / Fix |
| --- | --- |
| `could not translate host name "db.<ref>.supabase.co" to address: Name or service not known` | Either a transient DNS failure or a paused/deleted project. Check with `Resolve-DnsName db.<ref>.supabase.co`: no answer at all → the project is paused/deleted (restore it in the Supabase dashboard, or rebuild: new `DATABASE_URL` → `sql/schema.sql` → re-ingest); an `AAAA` record but no `A` record → the direct host is **IPv6-only**, see the next row. |
| `relation "garudpurandocuments" does not exist` | `sql/schema.sql` was not executed. The table is created **unquoted**, so Postgres stores it in lower case — the Python code refers to it unquoted too. Do not create it as `"garudPuranDocuments"`. |
| `function hybrid_search_garud(vector, text, double precision, integer) does not exist` | Same: run `sql/schema.sql`. The live function takes 6 parameters (the last two, the blend weights, have defaults `0.5`), and `query_embedding` must be declared as plain `vector` — declaring `vector(4096)` creates a second overload and makes the 4-argument call ambiguous. |
| `password authentication failed` | Wrong password in `DATABASE_URL`, or characters needing URL-encoding (`@` → `%40`, `#` → `%23`). |
| `model "gemma3" not found` | `ollama pull gemma3`, or point `OLLAMA_CHAT_MODEL` at an installed model (`qwen3:8b`, `llama3`). |
| `connection refused` on port 11434 | Ollama is not running — start `ollama serve` / the desktop app. |
| Direct Supabase connection fails (IPv6-only network) | `db.<ref>.supabase.co` publishes only an `AAAA` (IPv6) record, so IPv4-only networks fail to reach it. Use the **session pooler** string instead (host `aws-0-<region>.pooler.supabase.com`, port `5432`). |
| Answers echo `ô ... ö` or `û` instead of quotes | Mojibake in the PDF text layer (typographic quotes decoded with the wrong table) — cosmetic, the LLM just copies it. Fix the mapping in `clean_text()` for future ingests; to patch rows already stored: `update garudPuranDocuments set content = replace(replace(replace(content,'ô','"'),'ö','"'),'û','''') where content ~ '[ôöû]';` (re-embed afterwards if you want vectors and text to stay in sync). |
| First answer takes 30–90 s | Cold model load. `ollama ps` shows what is resident; the second call is much faster. |
| `500` + `wsarecv: An existing connection was forcibly closed by the remote host`, or `input length exceeds the context length` | The Ollama model runner died mid-generation: the prompt did not fit the context window (Ollama defaults to **2048** tokens, while the expanded context is ~11k chars ≈ 3k tokens) or the GPU ran out of memory. `app.py` now sends `OLLAMA_NUM_CTX=4096`, trims context to `MAX_CONTEXT_CHARS=12000` and retries once. If it persists, lower `MAX_CONTEXT_CHARS` / `OLLAMA_NUM_CTX`, or free VRAM with `ollama stop qwen3-embedding`. |
| Answers are very slow, or the runner keeps dying on a laptop GPU | `qwen3-embedding` (≈5.6 GB) and `gemma3` (≈4.3 GB) are both cached by Ollama; on an integrated GPU that shares system RAM they compete for the same memory and every request pays a model swap. Force one model at a time with `setx OLLAMA_MAX_LOADED_MODELS 1` (then restart Ollama), or use a smaller chat model such as `OLLAMA_CHAT_MODEL=gemma3:1b`. |
| Duplicate / repeating citations | The index was ingested twice — `truncate table garudPuranDocuments restart identity;` and re-run the ingestion. |
| `500` with `API Error: ...` in the console | The generic body hides details on purpose; read the Flask console, or run `/health` to see which dependency is down. |
| `too many clients already` / pool exhausted | Raise `maxconn` in `get_db_pool()` or lower the concurrency hitting the threaded server. |


## 🗺️ Not Implemented / Roadmap

1. **Chat UI** — only a JSON API exists; a small HTML/JS chat page with source chips is the obvious next step.
2. **Conversation memory** — follow-ups ("and what about daughters?") are not contextualized; needs a session store or message history.
3. **Automated tests & CI** — turn `scripts/smoke_test.py` into `pytest` tests (mock `ollama.chat` for synthesis) and run them on push.
4. **Better chapter-title parsing** — multi-line titles are truncated (`Chapter 15: PROGRESS TOWARDS THE`); the regex should continue onto the following line.
5. **Page-level citations** — `page` / `page_label` are already stored per chunk but are not surfaced in the answer citations.
6. **OCR** — the five scanned volumes in `data/` need Tesseract/PaddleOCR before they can be ingested.
7. **Faster retrieval** — pgvector cannot ANN-index 4,096 dimensions; store `halfvec(4000)` or a reduced 1,536-d vector to add an HNSW index as the corpus grows.
8. **Ops** — batch the embeddings during ingest (currently one Ollama call per chunk), add `gunicorn`/`waitress` config, rate limiting, auth and a `Dockerfile`.

