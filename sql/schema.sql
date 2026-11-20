-- ============================================================================
--  Garuda Purana RAG bot - database schema
--  Target: Supabase / PostgreSQL 15+ with the pgvector extension enabled.
--
--  This file mirrors the object definitions that the Python code expects and
--  that exist in the reference Supabase project (introspected with
--  pg_get_functiondef / pg_indexes). It is idempotent, so it is safe to re-run.
--
--  You only need it when building a database from scratch (new Supabase
--  project). If the table already holds your chunks, skip this file entirely.
--
--  Run with:      psql "$DATABASE_URL" -f sql/schema.sql
--  or paste the whole file into the Supabase SQL editor.
--
--  NOTE ON IDENTIFIER CASE
--  The Python code refers to the table as  garudPuranDocuments  WITHOUT quotes
--  (app.py, vectorization_job/*.py). PostgreSQL folds unquoted identifiers to
--  lower case, so the physical name is  garudpurandocuments.  Do not quote the
--  name in SQL, or the application will not find the table.
-- ============================================================================

create extension if not exists vector;

-- ----------------------------------------------------------------------------
-- 1. Vector store: one row per text chunk written by
--    vectorization_job/vectorize_load_vectors.py
--
--    `fts` is a generated column, so the keyword index stays in sync
--    automatically - the ingestion script never has to write it.
-- ----------------------------------------------------------------------------
create table if not exists garudPuranDocuments (
    id         bigserial primary key,
    content    text,                                                  -- chunk text
    metadata   jsonb,                                                 -- chapter_title, shlok_reference, source, page...
    embedding  vector(4096),                                          -- qwen3-embedding output dimension
    fts        tsvector generated always as (to_tsvector('english', content)) stored
);

-- Keyword leg of the hybrid search (the GIN index the function uses).
create index if not exists garud_puran_fts_idx
    on garudPuranDocuments using gin (fts);

-- Citation lookups and parent-document expansion (chapter + shlok).
create index if not exists idx_shlok_ref
    on garudPuranDocuments ((metadata->>'shlok_reference'));
create index if not exists idx_chapter_title
    on garudPuranDocuments ((metadata->>'chapter_title'));
create index if not exists idx_metadata_chapter_shlok
    on garudPuranDocuments ((metadata->>'chapter_title'), (metadata->>'shlok_reference'));

-- NOTE: no ANN (ivfflat/hnsw) index is created on purpose.
-- pgvector supports ANN indexes for at most 2,000 dimensions on `vector`
-- (4,000 on `halfvec`), and qwen3-embedding returns 4,096, so the semantic leg
-- is an exact (sequential) cosine scan. That is fast enough for ~1-10k chunks.
-- To get ANN speed later, store a reduced dimension (e.g. vector(1536)) or a
-- halfvec(4000) column and rebuild the index.


-- ----------------------------------------------------------------------------
-- 2. Hybrid retrieval function used by app.py and the validation script
--
--    THIS IS THE EXACT DEFINITION FROM THE LIVE DATABASE - do not change the
--    argument types. app.py calls it with only 4 arguments
--        hybrid_search_garud(%s::vector, %s::text, 0.2::float, 3::int)
--    so the last two parameters must keep their DEFAULTs, and `query_embedding`
--    must stay declared as plain `vector` (writing `vector(4096)` here would
--    create a second, overloaded function and the 4-arg call would become
--    ambiguous).
--
--    similarity = 0.5 * cosine similarity + 0.5 * ts_rank_cd(keyword)
--    The threshold is applied to the SEMANTIC score only.
-- ----------------------------------------------------------------------------
create or replace function hybrid_search_garud(
    query_embedding   vector,
    query_text        text,
    match_threshold   double precision,
    match_count       integer,
    full_text_weight  double precision default 0.5,
    vector_weight     double precision default 0.5
)
returns table (
    id         bigint,
    content    text,
    metadata   jsonb,
    similarity double precision
)
language plpgsql
as $function$
BEGIN

  RETURN QUERY

  SELECT
    garudPuranDocuments.id,
    garudPuranDocuments.content,
    garudPuranDocuments.metadata,
    (
      (vector_weight * (1 - (garudPuranDocuments.embedding <=> query_embedding))) +
      (full_text_weight * ts_rank_cd(garudPuranDocuments.fts, websearch_to_tsquery('english', query_text)))
    ) AS similarity

  FROM garudPuranDocuments

  WHERE (1 - (garudPuranDocuments.embedding <=> query_embedding)) > match_threshold

  ORDER BY similarity DESC

  LIMIT match_count;

END;

$function$;


-- ----------------------------------------------------------------------------
-- 3. Sanity checks
-- ----------------------------------------------------------------------------
-- select count(*) from garudPuranDocuments;
-- select proname, pg_get_function_identity_arguments(oid)
--   from pg_proc where proname = 'hybrid_search_garud';
