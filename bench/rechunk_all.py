"""Re-chunking des documents déjà ingérés (sans ré-extraire le texte).

Utilise le raw_text déjà présent dans document_content, re-parse via le bon
extractor (pour récupérer la structure), re-chunk avec les paramètres actuels,
et recalcule les embeddings des chunks.

Utile après un ajustement des paramètres de chunking : évite de re-parcourir
le système de fichiers et de re-lancer le résumé LLM.

Usage :
  uv run bench/rechunk_all.py
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import parsing  # noqa: E402
import kb  # noqa: E402


# get_chunk_id est centralisé dans kb.py pour garantir un hash cohérent.
get_chunk_id = kb.get_chunk_id


def main():
    con = kb.connect("knowledge.duckdb")
    try:
        # 1. Récupérer tous les docs avec leur file_path et raw_text.
        rows = con.execute(
            "SELECT d.id, d.file_path, c.raw_text FROM documents d "
            "JOIN document_content c ON d.id = c.document_id"
        ).fetchall()
        print(f"{len(rows)} documents à re-chunker.", flush=True)

        # 2. Vider la table chunks ( nécessite vss chargé = ok via kb.connect).
        try:
            con.execute("DROP INDEX IF EXISTS idx_chunks_embedding")
        except Exception:
            pass
        con.execute("DELETE FROM chunks")
        print("Table chunks vidée.", flush=True)

        total_chunks = 0
        t0 = time.time()
        for i, (doc_id, file_path, raw_text) in enumerate(rows, 1):
            try:
                # Re-parser pour récupérer la structure (page/section/type).
                # On utilise le file_path pour le bon extractor ; si le fichier
                # n'est plus accessible, on chunk le raw_text directement.
                try:
                    elements = parsing.extract_elements(file_path)
                    pass  # unused text assignment removed
                except Exception:
                    # Fallback : chunker le raw_text brut (pas de structure).
                    elements = [parsing.Element(line.strip(), "NarrativeText")
                                for line in raw_text.splitlines() if line.strip()]
                    pass  # unused text assignment removed

                chunks = parsing.chunk_elements(elements)
                # Embeddings des chunks.
                chunk_rows = []
                for ch in chunks:
                    vec = kb.embed(kb.truncate(ch.text)) if ch.text.strip() else None
                    chunk_rows.append((get_chunk_id(doc_id, ch.chunk_index), doc_id,
                                       ch.chunk_index, ch.text, ch.element_type,
                                       ch.page_number, ch.section, vec))
                if chunk_rows:
                    con.executemany(
                        "INSERT INTO chunks (id, document_id, chunk_index, text, "
                        "element_type, page_number, section, embedding) "
                        "VALUES (?,?,?,?,?,?,?,?)", chunk_rows,
                    )
                    total_chunks += len(chunk_rows)
                avg = total_chunks / i
                print(f"  [{i}/{len(rows)}] {Path(file_path).name[:45]:45s} "
                      f"-> {len(chunks):2d} chunks (cumul {total_chunks}, moy {avg:.1f})",
                      flush=True)
            except Exception as e:
                print(f"  [{i}/{len(rows)}] ECHEC {Path(file_path).name[:45]} : {str(e)[:60]}",
                      flush=True)

        # 3. Reconstruire l'index HNSW.
        try:
            con.execute(
                "CREATE INDEX idx_chunks_embedding "
                "ON chunks USING HNSW (embedding) WITH (metric = 'cosine');"
            )
            print("Index HNSW chunks reconstruit.", flush=True)
        except Exception as e:
            print(f"Warning: rebuild HNSW chunks : {e}", flush=True)

        elapsed = time.time() - t0
        print(f"\n=== Re-chunking terminé en {elapsed:.0f}s ===", flush=True)
        print(f"Total chunks: {total_chunks} (moyenne {total_chunks/len(rows):.1f}/doc)",
              flush=True)
    finally:
        con.close()


if __name__ == "__main__":
    main()
