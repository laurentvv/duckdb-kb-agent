# Python Health Report — DuckDB KB Agent

Generated on 2026-07-26 10:59 by python-health-audit.

## 1. Executive Summary
- Global grade: B
- Reason: Grade B assigned: Ruff has 0 findings and there are 0 E/F hotspots, but the presence of 17 C/D hotspots prevents an A.

## 2. Dead Code
### 2.1 Local — Ruff
No finding.

### 2.2 Global — Vulture
- `.agents\skills\skill-creator\eval-viewer\generate_review.py:382: unused variable 'format' (100% confidence)`
- `parsing.py:742: unused variable 'min_merge' (100% confidence)`

> ⚠️ Vulture produces false positives by construction (global static
> detection). Verify each entry before removal.

## 3. Complexity Hotspots (Radon)
- `batch_ingest.py`
    - `main` - C
- `kb.py`
    - `hybrid_search_chunks` - D
    - `hybrid_search` - D
- `parsing.py`
    - `_extract_pdf` - D
    - `_extract_docx_python_docx` - D
    - `chunk_elements` - D
    - `_group_words_into_lines` - C
    - `_extract_html` - C
    - `_extract_pdf_fitz` - C
    - `_extract_docx_mammoth` - C
    - `_extract_html_bs4` - C
- `bench\compare_bench.py`
    - `main` - C
- `bench\ingest_all.py`
    - `main` - C
    - `ingest_one` - C
- `bench\make_report.py`
    - `main` - C
- `bench\rechunk_all.py`
    - `main` - C
- `bench\run_bench_chunks.py`
    - `search_context` - C
- `skills\embed-docs\run.py`
    - `embed_pending_chunks` - C
- `skills\ingest-doc\run.py`
    - `main` - C
- `skills\migrate-db\run.py`
    - `add_chunks_table` - C
    - `main` - C
- `skills\reindex-vision\run.py`
    - `main` - C

## 4. Code Duplication (Pylint)
- `.agents\skills\skill-creator\scripts\run_eval.py` vs `.agents\skills\skill-creator\scripts\run_loop.py` (lines 269-278)
- `web\app.py` vs `skills\search-db\run.py` or similar `run.py` (lines 110-115)

## 5. Recommended Action Plan
1. Refactor `hybrid_search_chunks` and `hybrid_search` in `kb.py` to reduce D-level cyclomatic complexity by extracting query building logic into smaller helpers.
2. Refactor PDF and DOCX extraction methods in `parsing.py` to reduce their D-level complexity.
3. Remove the unused variable `min_merge` in `parsing.py`.
