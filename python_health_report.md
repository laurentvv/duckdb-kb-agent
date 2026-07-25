# Python Health Report — duckdb-kb-agent

Generated on 2026-07-25 12:33 by python-health-audit.

## 1. Executive Summary
- Global grade: B
- Reason: Grade B assigned: 0 Ruff errors, 0 E/F hotspots (only D hotspots), and a high average MI.

## 2. Dead Code
### 2.1 Local — Ruff
No finding.

### 2.2 Global — Vulture
- `.agents\skills\skill-creator\eval-viewer\generate_review.py:382`: unused variable 'format' (100% confidence)
- `parsing.py:742`: unused variable 'min_merge' (100% confidence)

> ⚠️ Vulture produces false positives by construction (global static
> detection). Verify each entry before removal.

## 3. Complexity Hotspots (Radon)
- `kb.py:286` `hybrid_search_chunks` - D
- `kb.py:163` `hybrid_search` - D
- `parsing.py:115` `_extract_pdf` - D
- `parsing.py:446` `_extract_docx_python_docx` - D
- `parsing.py:738` `chunk_elements` - D

## 4. Code Duplication (Pylint)
`web/app.py` and `run.py` (lines 92-97 / 98-103)
```python
    try:
        response = client.chat.completions.create(
          model=OLLAMA_MODEL,
          messages=[
              {"role": "system", "content": system_prompt},
```

## 5. Recommended Action Plan
1. **Refactor parsing.py**: Extract sub-methods from `chunk_elements` and `_extract_pdf` (D hotspots) to reduce cyclomatic complexity.
2. **Refactor kb.py**: Simplify the search logic in `hybrid_search_chunks` and `hybrid_search` (D hotspots).
3. **Consolidate Ollama client**: Extract the recurrent Ollama API call from `web/app.py` and other scripts into a shared helper in `kb.py` to eliminate duplication.
