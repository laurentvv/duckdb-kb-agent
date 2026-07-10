<div align="center">
      <h1>🦆 DuckDB KB Agent</h1>
      <p><b>Agentic Knowledge Base & Document Management System</b></p>
      <p>
        <img src="https://img.shields.io/badge/Python-3.14-blue?logo=python&logoColor=white" alt="Python 3.14" />
        <img src="https://img.shields.io/badge/Package_Manager-uv-purple" alt="uv" />
        <img src="https://img.shields.io/badge/Database-DuckDB-yellow?logo=duckdb" alt="DuckDB" />
        <img src="https://img.shields.io/badge/Architecture-Agentic-success" alt="Agentic Architecture" />
      </p>
    </div>

    ## 💡 About
    **DuckDB KB Agent** is a paradigm shift from traditional Markdown-based wikis. Instead of human-maintained documentation, this system is designed to be **operated entirely by an AI Coding Agent** (e.g.,
  Antigravity, Cline).

    The agent uses specialized Python skills to ingest raw documents (PDF, Word, Excel), extracts metadata and summaries using LLMs (Local or API), and stores everything in a **DuckDB database**. It answers
  user queries instantly using DuckDB's native **Full-Text Search (FTS)**, completely bypassing the need for complex and costly Vector Databases (RAG).

    ### ✨ Key Features
    - **Zero Hallucination**: The Agent queries the SQL database and bases its answers purely on the raw FTS extracts.
    - **RAG Alternative**: No embeddings, no vector DBs. Uses BM25 Full-Text Search for ultra-fast, exact-match document retrieval.
    - **Agent-First Architecture**: Features a strict `AGENTS.md` manifesto instructing the AI on how to interact with the database using isolated Python scripts (`skills/`).
    - **Modern Stack**: Built with Python 3.14, `uv`, Pydantic (Structured Output), and PyMuPDF.
