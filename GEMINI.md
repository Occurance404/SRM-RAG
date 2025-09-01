# University RAG Backend Plan (Text + Image-Context Aware)

> Goal: Build a clean, scalable backend pipeline that crawls a university website, extracts high-signal text **and** image URLs, associates each image with nearby textual context, and indexes everything for RAG. Frontend can be added later. Python-first.

---

## 1) High-Level Architecture

**Stages**

1. **Discovery & Fetching**: polite crawler (robots-aware) with sitemap seeds + in-page link expansion.
2. **Parse & Clean**: boilerplate removal, sectionization, heading-aware text extraction.
3. **Image Extraction + Context**: resolve lazy images; capture alt, caption, header lineage, and **surrounding text window** as context.
4. **Normalization & Dedup**: canonical URLs, tracking-parameter stripping, near-duplicate text & image dedup.
5. **Chunking**: heading-aware semantic chunking with overlap; attach image references to the most relevant chunk.
6. **Metadata Enrichment**: NER for people/departments; page-type heuristics; compute scores.
7. **Indexing**: store raw in object store (JSONL/Parquet); index in DB (Postgres + pgvector) and/or a vector DB; optional keyword index (BM25/Meilisearch).
8. **Retrieval Pipeline**: intent detection → hybrid retrieval (keyword + dense) → cross-encoder rerank → image selection → context assembly.
9. **Answering**: LLM prompt builder (citations + image URLs) with guardrails.
10. **Monitoring & QA**: coverage stats, broken links, drift detection, and regression suite.

**Storage**

* **Landing (raw)**: `/data/raw/date=YYYY-MM-DD/*.jsonl`
* **Processed**: `/data/processed/date=.../*.parquet`
* **DB**: Postgres (chunk table, image table, page table) + **pgvector** for embeddings.

---

## 2) Data Model (Schemas)

### 2.1 Page

```json
{
  "page_id": "uuid",
  "url": "https://...",
  "canonical_url": "https://...",
  "title": "Admissions – Graduate",
  "raw_html_sha1": "...",
  "clean_text": "...",          // after boilerplate removal
  "headings": [
    {"level": 1, "text": "...", "start": 234},
    {"level": 2, "text": "...", "start": 512}
  ],
  "metadata": {"lang": "en", "breadcrumbs": ["Academics", "CS"]},
  "fetched_at": "2025-08-22T12:00:00Z"
}
```

### 2.2 Image

```json
{
  "image_id": "uuid",
  "page_id": "uuid",
  "url": "https://.../faculty/jane-doe.jpg",
  "alt": "Prof. Jane Doe",
  "caption": "Jane Doe, Associate Professor of CS",
  "dom_path": "body/main/section[2]/figure[1]/img",
  "hash_hint": "sha1 of URL string",    // to dedup same asset used on many pages
  "context_snippet": "Jane Doe leads the ML lab...", // 512 chars around the image in DOM order
  "header_lineage": ["People", "Faculty", "Computer Science"],
  "is_primary": false,
  "quality_score": 0.82
}
```

### 2.3 Chunk (for RAG)

```json
{
  "chunk_id": "uuid",
  "page_id": "uuid",
  "url": "https://...",
  "title": "...",
  "text": "...",            // ~400–800 tokens
  "tokens": 620,
  "section_path": ["H1: Faculty", "H2: Jane Doe"],
  "images": ["image_id", ...], // images whose context overlaps this chunk
  "entities": {"person": ["Jane Doe"], "dept": ["CS"]},
  "embeddings": {"text": [ ... ]},
  "bm25": {"terms": {"admission": 3, ...}}, // optional
  "created_at": "..."
}
```

---

## 3) Crawling & Parsing

**Inputs**: start URL(s), optional allow/deny regex, max pages, delay.

**Tech**: `requests`/`httpx`, `BeautifulSoup` + `lxml`. For JS-heavy pages, use `playwright` (headless) and/or `sitemap.xml` seeding.

**Key Policies**

* Honor `robots.txt`; throttle requests; random jitter.
* Normalize URLs: lowercase host, strip fragments, drop tracking params (utm\_\*, gclid, fbclid), resolve relative paths.
* Only follow links from **main/article** container to avoid footer loops.
* Skip non-HTML (pdf/doc/zip) in the crawler; collect their URLs into a side list for optional PDF pass.

**Boilerplate Removal**

* Drop `header, footer, nav, aside, script, style, noscript, iframe, template`.
* Choose content container: prefer `<main>` → `<article>` → `<body>`.

**Heading-aware Text Extraction**

* Record heading hierarchy (H1–H6) and offsets.
* Preserve simple lists and tables as plain text blocks.

**Image Extraction**

* Resolve `img[src]`, `data-src`, `data-original`, `srcset` (pick largest), `<picture><source srcset>`, OG/Twitter meta.
* Filter logos/icons/sprites/very-small; keep faculty/profile/people directories.
* Capture **context window**: take up to \~512 characters before and after the image in DOM order; also capture nearest header lineage and any `<figcaption>`.

---

## 4) Normalization & Dedup

* **Canonical URL** support via `<link rel="canonical">`.
* **Text near-duplicate** detection: MinHash/SimHash on cleaned text to drop boilerplate-only pages.
* **Image dedup**: SHA1 of image URL; optional content-hash if downloading is later enabled.

---

## 5) Chunking Strategy

* **Goal**: retrieval-friendly chunks that keep local meaning and image associations.
* **Algo**:

  1. Split by heading boundaries; within sections, use semantic split (sentence/paragraph) to target \~400–800 tokens.
  2. Add **100–150 token overlap** between consecutive chunks within a section.
  3. Attach images to the chunk where their **context window majority** falls; if context overlaps multiple chunks, attach to both (with lower weight).

---

## 6) Metadata Enrichment

* **Entity Extraction (spaCy)**: person names, departments, locations.
* **Page Typing**: regex/heuristics on URL and headings (e.g., `/faculty/`, `/people/`, `/admissions/`).
* **Scoring**: `image.quality_score` (alt text present, caption present, file type, faculty-path boost; penalize logos/banners).

---

## 7) Indexing Layer

* **DB**: Postgres

  * `pages(page_id PK, url, canonical_url, title, clean_text, fetched_at, ...)`
  * `images(image_id PK, page_id FK, url, alt, caption, context_snippet, header_lineage, is_primary, quality_score)`
  * `chunks(chunk_id PK, page_id FK, url, section_path, text, tokens)`
  * `chunk_images(chunk_id FK, image_id FK)`
* **Vector**: `pgvector` column on `chunks(text_embedding)`. Optionally, separate index for **entity-boosted embeddings**.
* **Keyword**: Meilisearch or Postgres `tsvector` for BM25-like retrieval.

---

## 8) Retrieval Pipeline (Runtime)

1. **Query Understanding**

   * Classify: person lookup / program info / policy / generic.
   * NER on query (e.g., detect "Prof. Jane Doe").

2. **Candidate Generation (Hybrid)**

   * Dense: cosine on `text_embedding` (top 50).
   * Sparse: keyword index (top 200) → union → dedup.
   * Entity boost: if person detected, boost chunks with `entities.person` match; also boost images whose `alt/caption/context_snippet` contains the name.

3. **Rerank**

   * Cross-encoder (e.g., `cross-encoder/ms-marco-MiniLM-L-6-v2`) over top \~100 to pick top 5–10 chunks.

4. **Image Selection**

   * From winning chunks, select images with highest `(quality_score + name-match + same-section bonus)`.

5. **LLM Context Assembly**

   * Build prompt with:

     * Top chunks (dedup by page).
     * For person queries, include `primary_image_url` + up to 2 supporting images (URLs only), with the **context lines** that justify each image.
     * Citations: page URLs and section headings.

6. **Answer Generation**

   * Use system instructions to never hallucinate beyond provided context; include citations and **render image URLs**.

---

## 9) Implementation Plan (Python)

**Repo Structure**

```
rag_uni/
  crawler/
    __init__.py
    crawl.py           # requests/bs4 pipeline
    parse.py           # cleaning, headings, image extraction
    utils.py           # URL normalize, dedup helpers
  processing/
    chunker.py         # heading-aware chunking
    enrich.py          # spaCy NER, page typing, scoring
    dedup.py           # MinHash/SimHash for near-dupes
  storage/
    schema.sql         # Postgres DDL
    load.py            # write JSONL/Parquet + upsert into DB
  index/
    embed.py           # text embeddings (e.g., sentence-transformers)
    vector.py          # pgvector ops
    keyword.py         # Meilisearch/Postgres tsvector
  retrieval/
    search.py          # hybrid retrieval
    rerank.py          # cross-encoder
    assemble.py        # prompt/context builder
  api/
    server.py          # FastAPI endpoints
  config/
    settings.py        # env vars (DB_URL, rate limits, etc.)
  scripts/
    run_crawl.py
    build_indexes.py
    serve_api.py
```

**Key Libraries**

* `beautifulsoup4`, `lxml`, `requests`/`httpx`, `playwright` (optional)
* `spacy`, `rapidfuzz`, `datasketch` (MinHash) or `simhash`
* `pandas`, `pyarrow` (Parquet)
* `psycopg2-binary` or `asyncpg`, `pgvector`
* `sentence-transformers`, `torch` (embeddings), `rank-bm25` or Meilisearch
* `fastapi`, `uvicorn`

**FastAPI Endpoints**

* `POST /ingest/crawl` (kick off crawl with config)
* `POST /ingest/process` (chunk + enrich + index)
* `POST /query` (returns answer, citations, and image URLs)
* `GET /healthz`

---

## 10) Algorithms (Pseudocode)

### 10.1 Image + Context Extraction

```python
for img in container.find_all('img'):
    url = resolve_src_or_srcset(img)
    if is_logo_or_icon(url, img):
        continue
    alt = img.get('alt', '')
    caption = figcaption_text(img)
    header_lineage = nearest_headers(img)
    context_snippet = dom_text_window(img, window_chars=512)  # before+after
    save_image(page_id, url, alt, caption, header_lineage, context_snippet)
```

### 10.2 Chunk Attachments

```python
for chunk in chunks:
    for image in images_on_page:
        if overlap(image.context_span, chunk.text_span) > 0.5:
            link(image, chunk)
```

### 10.3 Retrieval (Person Query)

```python
entities = ner(query)
if entities.person:
    candidates = dense_search(query) ∪ sparse_search(query)
    candidates = boost_person_matches(candidates, entities.person)
    top = rerank(query, candidates)
    images = choose_images(top, entities.person)
    return assemble_answer(top, images)
```

---

## 11) Operational Concerns

* **Politeness**: rate limits, concurrency=2–4, backoff on 429/5xx.
* **Error handling**: retry with jitter; skip on persistent failure; log per-URL status.
* **Observability**: Prometheus-friendly counters (pages fetched, images kept, dupes removed).
* **Reproducibility**: capture crawl config; write manifests to `/data/manifest.json`.
* **Security**: only crawl allowed domains; sanitize outputs; no PII leakage beyond public pages.

---

## 12) Evaluation & QA

* **Coverage**: % of sitemap pages crawled; % with non-empty content; images-per-page distribution.
* **Quality**: manual spot-check on faculty profiles; precision\@10 for person queries.
* **Latency**: p50/p95 retrieval & answer times.
* **Regression**: snapshot a small set of pages; re-run pipeline after code changes and diff outputs.

---

## 13) Milestones

1. **M1 – Crawler MVP (Text + Images + Context)**

   * Crawl 1–2 departments, produce JSONL for pages, images, and chunks.
2. **M2 – Chunking + Enrichment**

   * Heading-aware chunks, attach images, NER for people/depts.
3. **M3 – Indexing**

   * Postgres schema + pgvector; load and verify retrieval.
4. **M4 – Retrieval + Rerank**

   * Hybrid search + cross-encoder; person query flow with images.
5. **M5 – API**

   * FastAPI `/query` endpoint returning answer + citations + image URLs.
6. **M6 – QA + Monitoring**

   * Add metrics, dashboards, and tests.

---

## 14) Next Actions (Concrete)

* [ ] Stand up Postgres + pgvector.
* [ ] Implement crawler with image-context capture (use provided template).
* [ ] Implement chunker and image–chunk linking.
* [ ] Add spaCy NER and page-typing heuristics.
* [ ] Build indexers (embeddings + BM25) and hybrid retrieval.
* [ ] Implement answer assembly with image selection for person queries.
* [ ] Expose `/query` via FastAPI.
* [ ] Add eval notebook + fixtures.
