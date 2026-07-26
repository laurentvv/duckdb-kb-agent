# DocsGPT RAG & Local LLM Architecture Analysis

## 1. RAG Retrieval Mechanics
- **Dispatcher Pattern**: DocsGPT uses a `Dispatcher` (`application/retriever/dispatcher.py`) to manage retrieval across multiple `vectorstores`, allocating token budgets seamlessly to avoid context overflow. 
- **Query Rephrasing**: If conversation history is present, the user question is automatically passed to a secondary LLM call to rewrite it into a standalone search query.
- **Candidate Over-fetching & Filtering**: The retriever fetches an inflated candidate list (k=20-500) and then trims the list based on a strict token budget (default 50k tokens, using 90% as maximum threshold).
- **Context Injection Formatting**: Fetched chunks are formatted into XML-like structures before being injected into the prompt (`application/api/answer/services/prompt_renderer.py`):
  ```xml
  <document index="1">
    <source>filename</source>
    <content>... extracted text ...</content>
  </document>
  ```

## 2. Prompt Engineering Details
DocsGPT utilizes Jinja2 templates (found in `application/prompts/`) to dynamically construct system prompts.
- **Strict Anti-Hallucination**: (`chat_combine_strict.txt`)
  > "Answer only from the document context below, tool results, and the conversation. Do not fall back to your general knowledge. If they do not contain enough information, reply that you do not have the information needed to answer and name what is missing. Never invent information."
- **Citation Instructions**:
  > "Ground your answer strictly in these documents and cite their titles."
- **Fallback templating**:
  Using Jinja `{% if source.summaries %}` allows inserting clear instructions when RAG fails: `No document context was retrieved for this message. Rely on the conversation...`

## 3. Conversation History Management
- **Token-Aware Truncation**: Messages are dynamically truncated (`_truncate_history_to_fit` in `application/agents/base.py`) before every LLM call to ensure they strictly respect the context window limits.
- **History Compression**: `CompressionOrchestrator` triggers when limits are approached. It creates a compressed summary of older messages and explicitly injects it into the system prompt:
  > "This session is being continued from a previous conversation that has been compressed to fit within context limits. The conversation is summarized below: {summary}"
- **Agent Reasoning Continuity**: DeepSeek thinking paths (`reasoning_content`) are explicitly persisted across conversational turns.

## 4. Local LLM Interface
- **Base Interface**: Handled in `application/llm/base.py`, defining robust fallback providers, SSE streaming, and usage tracking.
- **llama.cpp Integration**: Implemented in `application/llm/llama_cpp.py` using a singleton pattern. It defaults to a static `n_ctx=2048` and `max_tokens=150`.
- **Custom Instruction Wrap**: For the local provider, it constructs prompts with:
  `### Instruction \n {user_question} \n ### Context \n {context} \n ### Answer \n`

## 5. Proposal for DuckDB Adaptation in `duckdb-kb-agent`
- **DuckDB Hybrid Search**: Adapt DocsGPT's `Dispatcher` concept to issue DuckDB SQL queries utilizing both Full-Text Search (BM25) and Vector Search (`array_cosine_similarity`) mapped through Reciprocal Rank Fusion (RRF).
- **XML Context Formatting**: Adopt DocsGPT's `<document>` and `<source>` XML tags. This clearly demarcates source bounds for Ollama/llama.cpp models and heavily improves citation accuracy.
- **Jinja-Based Prompting**: Implement a Jinja2 system in Python to branch prompt instructions (e.g., swapping to strict mode dynamically, or omitting context instructions completely if DuckDB returns 0 rows).
- **Summarization Fallback**: Implement the `CompressionOrchestrator` logic locally: if `duckdb-kb-agent` hits a context token limit while storing conversation context in DuckDB, trigger a background local LLM summarization of the history rather than a strict cut-off.

## 6. Document Ingestion & Chunking Strategies
DocsGPT implements robust ingestion mechanics inside `application/parser/`:
- **Docling Extraction**: Documents (PDF, DOCX) are routed to Docling by default (`document_reader.py`), ensuring tables and layout are perfectly preserved into clean Markdown before being chunked. 
- **4 Advanced Chunking Strategies**: 
  - *Recursive*: Hierarchical splits on `\n\n`, `\n`, `. `.
  - *Markdown*: Context-aware splits on Markdown headers (`^#{1,6}\s`).
  - *Semantic*: Groups adjacent sentences by computing embedding distance and splitting at the 95th percentile of cosine distance (detecting topic shifts).
  - *Parent-Child*: Slices documents into large parent windows (e.g., 1000 tokens), then embeds small children (e.g., 100 tokens). The small child is embedded for precise retrieval, but its metadata carries the large `parent_text` to feed the LLM.

## 7. GraphRAG & Background Processing
- **Celery Workers & Heartbeats**: Heavy ingestions are dispatched to Celery workers (`worker.py`). A background heartbeat thread constantly pings the DB to track progress and recover automatically if a process dies.
- **Asynchronous GraphRAG**: Post-embedding, a `_maybe_enqueue_graph_extraction` task is triggered to construct a GraphRAG knowledge graph in the background, allowing standard RAG to be available immediately while the graph builds asynchronously.
