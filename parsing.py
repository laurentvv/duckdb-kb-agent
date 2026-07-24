"""Extraction structurée et chunking sémantique des documents.

Ce module produit des *éléments* structurés (texte + type + page + section)
à partir de PDF, DOCX, HTML, et fichiers texte, puis les découpe en chunks
cohérents pour l'embedding et la recherche.

Contrairement à l'ancien ``extract_text`` (qui concaténait tout le texte),
``extract_elements`` conserve les numéros de page, les titres de section et
les tableaux, ce qui permet :
  - un chunking respectant la structure (pas de coupure au milieu d'une section),
  - des citations vérifiables (page/section) dans les réponses de l'agent,
  - une extraction correcte des tableaux (pdfplumber/mammoth).

Dépendances optionnelles : pdfplumber (PDF), mammoth (DOCX), trafilatura
(HTML). En cas d'absence, on repli sur PyMuPDF / python-docx / texte brut.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# --------------------------------------------------------------------- Élément


@dataclass
class Element:
    """Unité logique extraite d'un document (paragraphe, titre, table...)."""

    text: str
    element_type: str = "NarrativeText"  # Title | NarrativeText | Table | ListItem | Section
    page_number: int | None = None
    section: str | None = None


@dataclass
class Chunk:
    """Chunk produit par ``chunk_elements`` (sérialisable en ligne DuckDB)."""

    text: str
    element_type: str = "NarrativeText"
    page_number: int | None = None
    section: str | None = None
    chunk_index: int = 0


# ----------------------------------------------------------------- Extraction

# Types d'éléments considérés comme titres (marquent un changement de section).
_TITLE_TYPES = {"Title", "Section"}


def extract_elements(file_path: str) -> list[Element]:
    """Extrait les éléments structurés d'un fichier.

    Routeur par extension. Renvoie une liste d'``Element`` ordonnée comme le
    document. Lève ``ValueError`` si l'extraction échoue définitivement.
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return _extract_pdf(file_path)
    if ext == ".docx":
        return _extract_docx(file_path)
    if ext in (".html", ".htm"):
        return _extract_html(file_path)
    if ext == ".csv":
        return _extract_csv(file_path)
    if ext == ".xlsx":
        return _extract_xlsx(file_path)
    return _extract_text_file(file_path)


def _current_section(elements: list[Element]) -> str | None:
    """Renvoie le titre de section courant (dernier Title/Section rencontré)."""
    for el in reversed(elements):
        if el.element_type in _TITLE_TYPES and el.text.strip():
            return el.text.strip()[:200]
    return None


def _extract_pdf(file_path: str) -> list[Element]:
    """PDF via pdfplumber (texte + tables + page), repli PyMuPDF si besoin."""
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        return _extract_pdf_fitz(file_path)

    elements: list[Element] = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page_no, page in enumerate(pdf.pages, start=1):
                # 1. Tables de la page (priorité : structure préservée).
                tables = page.find_tables()
                table_bboxes = [t.bbox for t in tables]
                for tbl in tables:
                    rows = tbl.extract()
                    if not rows:
                        continue
                    # Représentation texte lisible (séparateur tabulation).
                    text = "\n".join(
                        "\t".join("" if c is None else str(c) for c in row)
                        for row in rows
                    ).strip()
                    if text:
                        elements.append(Element(
                            text=text, element_type="Table",
                            page_number=page_no,
                            section=_current_section(elements),
                        ))
                # 2. Texte hors tables (on exclut les zones couvertes par les tables).
                words = page.extract_words(
                    keep_blank_chars=False,
                    use_text_flow=True,
                    extra_attrs=["size", "fontname"],
                )
                if not words and not table_bboxes:
                    # Page sans texte extractible (PDF image potentiel) : on note rien.
                    continue
                # Reconstruire des lignes par regroupement vertical (top).
                lines = _group_words_into_lines(words, exclude_bboxes=table_bboxes)
                for line_text, is_title in lines:
                    line_text = line_text.strip()
                    if not line_text:
                        continue
                    etype = "Title" if is_title else "NarrativeText"
                    elements.append(Element(
                        text=line_text, element_type=etype,
                        page_number=page_no,
                        section=_current_section(elements),
                    ))
    except Exception as e:
        # Repli PyMuPDF si pdfplumber échoue.
        try:
            return _extract_pdf_fitz(file_path)
        except Exception:
            raise ValueError(f"Échec extraction PDF ({file_path}) : {e}") from e
    return elements


def _group_words_into_lines(
    words: list[dict], exclude_bboxes: list[tuple] | None = None,
    title_size_threshold: float = 13.0,
) -> list[tuple[str, bool]]:
    """Regroupe les mots en lignes (même top ± tolérance) et détecte les titres.

    Détecte un titre si la police contient 'Bold'/'black' ou si la taille
    moyenne dépasse le seuil (heuristique simple, fonctionne sur la plupart
    des PDF business).
    """
    if not words:
        return []
    exclude_bboxes = exclude_bboxes or []

    def _in_excluded(w):
        wx, wy = w.get("x0", 0), w.get("top", 0)
        for (x0, top, x1, bottom) in exclude_bboxes:
            if x0 <= wx <= x1 and top <= wy <= bottom:
                return True
        return False

    filtered = [w for w in words if not _in_excluded(w)]
    if not filtered:
        return []

    # Trier par (top, x0) puis regrouper par top proche.
    filtered.sort(key=lambda w: (round(float(w.get("top", 0)), 1), float(w.get("x0", 0))))
    lines: list[list[dict]] = []
    current: list[dict] = []
    current_top: float | None = None
    tol = 3.0  # tolérance verticale (pts)
    for w in filtered:
        top = float(w.get("top", 0))
        if current_top is None or abs(top - current_top) <= tol:
            current.append(w)
            current_top = top  # top courant glissant (dernier mot de la ligne)
        else:
            lines.append(current)
            current = [w]
            current_top = top
    if current:
        lines.append(current)

    # Trier chaque ligne par x0 (ordre de lecture) et reconstruire le texte.
    result: list[tuple[str, bool]] = []
    for line in lines:
        line.sort(key=lambda w: float(w.get("x0", 0)))
        text = " ".join(str(w.get("text", "")) for w in line).strip()
        if not text:
            continue
        sizes = [float(w.get("size", 0)) for w in line if w.get("size")]
        avg_size = sum(sizes) / len(sizes) if sizes else 0.0
        fonts = " ".join(str(w.get("fontname", "")).lower() for w in line)
        is_title = avg_size >= title_size_threshold or "bold" in fonts or "black" in fonts
        result.append((text, is_title))
    return result


def _extract_pdf_fitz(file_path: str) -> list[Element]:
    """Repli PyMuPDF (texte natif uniquement, pas de tables)."""
    import fitz  # type: ignore  # noqa: PLC0415

    elements: list[Element] = []
    doc = fitz.open(file_path)
    try:
        for page_no, page in enumerate(doc, start=1):
            text = page.get_text() or ""
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                elements.append(Element(
                    text=line, element_type="NarrativeText",
                    page_number=page_no,
                    section=_current_section(elements),
                ))
    finally:
        doc.close()
    return elements


def _extract_docx(file_path: str) -> list[Element]:
    """DOCX : python-docx en principal, mammoth en repli.

    python-docx est préféré car il préserve fidèlement TOUT le contenu des
    paragraphes (y compris le texte dans les balises internes : run, liens,
    mises en forme) ainsi que l'ordre paragraphe/table du corps. mammoth
    (HTML) perdait une partie du contenu sur certains DOCX (texte dans des
    spans imbriqués non récupérés par le parcours BeautifulSoup), d'où le
    repli uniquement si python-docx échoue ou renvoie un contenu vide.
    """
    try:
        elements = _extract_docx_python_docx(file_path)
        # Garde-fou : si python-docx renvoie un contenu manifestement incomplet,
        # on tente mammoth (qui peut mieux gérer certains formats exotiques).
        text_len = sum(len(e.text) for e in elements)
        if elements and text_len > 0:
            return elements
    except Exception:
        pass
    # Repli mammoth.
    return _extract_docx_mammoth(file_path)


def _extract_docx_mammoth(file_path: str) -> list[Element]:
    """Repli DOCX via mammoth (HTML structuré) + BeautifulSoup.

    mammoth convertit en HTML (titres <h1>-<h6>, <p>, <table>), ce qu'on parse
    pour retrouver types et tables. Moins fidèle que python-docx sur certains
    contenus (texte dans spans imbriqués), d'où son usage en repli.
    """
    try:
        import mammoth  # type: ignore
        import bs4  # type: ignore  # beautifulsoup4
    except ImportError as e:
        raise ValueError(f"Échec extraction DOCX ({file_path}) : "
                         f"ni python-docx ni mammoth disponible : {e}") from e

    try:
        with open(file_path, "rb") as f:
            result = mammoth.convert_to_html(f)
        html = result.value
    except Exception as e:
        raise ValueError(f"Échec extraction DOCX mammoth ({file_path}) : {e}") from e

    elements: list[Element] = []
    soup = bs4.BeautifulSoup(html, "html.parser")
    for node in soup.descendants:
        if not getattr(node, "name", None):
            continue
        if node.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = node.get_text(strip=True)
            if text:
                elements.append(Element(
                    text=text, element_type="Title",
                    section=_current_section(elements),
                ))
        elif node.name == "table":
            text = _table_to_text(node)
            if text:
                elements.append(Element(
                    text=text, element_type="Table",
                    section=_current_section(elements),
                ))
        elif node.name == "p":
            text = node.get_text(strip=True)
            if text:
                etype = "ListItem" if _is_list_item(node) else "NarrativeText"
                elements.append(Element(
                    text=text, element_type=etype,
                    section=_current_section(elements),
                ))
    return elements


def _is_list_item(node) -> bool:
    """Détecte si un <p> est un élément de liste (parent <li>/<ul>/<ol>)."""
    p = node.parent
    return p is not None and getattr(p, "name", None) in ("li", "ul", "ol")


def _table_to_text(table_node) -> str:
    """Convertit un <table> BeautifulSoup en texte tabulé (lignes × cellules)."""
    rows = []
    for tr in table_node.find_all("tr"):
        cells = [tr_cell.get_text(strip=True) for tr_cell in tr.find_all(["td", "th"])]
        if cells:
            rows.append("\t".join(cells))
    return "\n".join(rows).strip()


def _extract_docx_python_docx(file_path: str) -> list[Element]:
    """Repli python-docx : paragraphes (avec style Heading) + tables inline."""
    import docx  # type: ignore  # noqa: PLC0415

    doc = docx.Document(file_path)
    elements: list[Element] = []
    # Parcourir le corps en respectant l'ordre paragraphes/tables (iter Inner).
    # python-docx expose doc.paragraphs et doc.tables séparément ; on reconstruit
    # l'ordre via le body XML.
    from docx.oxml.ns import qn  # type: ignore  # noqa: PLC0415

    body = doc.element.body
    para_idx = 0
    table_idx = 0
    paragraphs = doc.paragraphs
    tables = doc.tables
    for child in body.iterchildren():
        tag = child.tag
        if tag == qn("w:p") and para_idx < len(paragraphs):
            para = paragraphs[para_idx]
            para_idx += 1
            text = para.text.strip()
            if not text:
                continue
            style = (para.style.name or "").lower() if para.style else ""
            if "heading" in style or "title" in style:
                elements.append(Element(
                    text=text, element_type="Title",
                    section=_current_section(elements),
                ))
            elif "list" in style:
                elements.append(Element(
                    text=text, element_type="ListItem",
                    section=_current_section(elements),
                ))
            else:
                elements.append(Element(
                    text=text, element_type="NarrativeText",
                    section=_current_section(elements),
                ))
        elif tag == qn("w:tbl") and table_idx < len(tables):
            tbl = tables[table_idx]
            table_idx += 1
            rows = []
            for row in tbl.rows:
                cells = [c.text.strip() for c in row.cells]
                rows.append("\t".join(cells))
            text = "\n".join(rows).strip()
            if text:
                elements.append(Element(
                    text=text, element_type="Table",
                    section=_current_section(elements),
                ))
    return elements


def _extract_html(file_path: str) -> list[Element]:
    """HTML via trafilatura (contenu principal + titres) avec repli bs4."""
    try:
        import trafilatura  # type: ignore
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        return _extract_html_bs4(file_path)

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            html_content = f.read()
        # trafilatura extrait le contenu principal ; on récupère aussi la structure.
        extracted = trafilatura.extract(
            html_content, output_format="xml", include_tables=True, include_images=False,
        )
        if extracted:
            soup = BeautifulSoup(f"<root>{extracted}</root>", "xml")
            elements: list[Element] = []
            for node in soup.descendants:
                if not getattr(node, "name", None):
                    continue
                # "hi" = highlight/heading trafilatura (contenu) ; "head" est la
                # balise <head> HTML (métadonnées : title/meta/script) qu'il ne
                # faut PAS indexer comme titre de contenu.
                if node.name == "hi":
                    text = node.get_text(strip=True)
                    if text:
                        elements.append(Element(
                            text=text, element_type="Title",
                            section=_current_section(elements),
                        ))
                elif node.name == "table":
                    text = _table_to_text(node)
                    if text:
                        elements.append(Element(
                            text=text, element_type="Table",
                            section=_current_section(elements),
                        ))
                elif node.name in ("p", "li"):
                    text = node.get_text(strip=True)
                    if text:
                        etype = "ListItem" if node.name == "li" else "NarrativeText"
                        elements.append(Element(
                            text=text, element_type=etype,
                            section=_current_section(elements),
                        ))
            if elements:
                return elements
        # Repli si trafilatura ne renvoie rien.
        return _extract_html_bs4(file_path)
    except Exception as e:
        try:
            return _extract_html_bs4(file_path)
        except Exception:
            raise ValueError(f"Échec extraction HTML ({file_path}) : {e}") from e


def _extract_html_bs4(file_path: str) -> list[Element]:
    """Repli HTML : BeautifulSoup (lxml) sur les balises structurelles."""
    from bs4 import BeautifulSoup  # type: ignore  # noqa: PLC0415

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        html_content = f.read()
    soup = BeautifulSoup(html_content, "lxml")
    # Supprimer script/style.
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    elements: list[Element] = []
    for node in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "table", "li"]):
        if node.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
            text = node.get_text(strip=True)
            if text:
                elements.append(Element(
                    text=text, element_type="Title",
                    section=_current_section(elements),
                ))
        elif node.name == "table":
            text = _table_to_text(node)
            if text:
                elements.append(Element(
                    text=text, element_type="Table",
                    section=_current_section(elements),
                ))
        elif node.name == "li":
            text = node.get_text(strip=True)
            if text:
                elements.append(Element(
                    text=text, element_type="ListItem",
                    section=_current_section(elements),
                ))
        elif node.name == "p":
            text = node.get_text(strip=True)
            if text:
                elements.append(Element(
                    text=text, element_type="NarrativeText",
                    section=_current_section(elements),
                ))
    return elements


def _extract_csv(file_path: str) -> list[Element]:
    """CSV : une table entière + métadonnées fichier."""
    import pandas as pd  # type: ignore  # noqa: PLC0415

    df = pd.read_csv(file_path)
    text = df.to_string(index=False)
    return [Element(text=text, element_type="Table",
                    section=os.path.basename(file_path))]


def _extract_xlsx(file_path: str) -> list[Element]:
    """XLSX : une table par feuille (section = nom de feuille)."""
    import pandas as pd  # type: ignore  # noqa: PLC0415

    try:
        all_sheets = pd.read_excel(file_path, sheet_name=None)
    except Exception as e:
        raise ValueError(f"Échec lecture XLSX ({file_path}) : {e}") from e
    elements: list[Element] = []
    for sheet_name, df in all_sheets.items():
        if df.empty:
            continue
        text = df.to_string(index=False)
        elements.append(Element(
            text=text, element_type="Table",
            section=sheet_name,
        ))
    return elements


def _extract_text_file(file_path: str) -> list[Element]:
    """Fichiers texte/Markdown/etc. : lignes structurées en NarrativeText.

    Détection simple de titres Markdown (# ...) et de listes (- /* ...).
    """
    for enc in ("utf-8", "cp1252"):
        try:
            with open(file_path, "r", encoding=enc) as f:
                content = f.read()
            break
        except UnicodeDecodeError:
            content = None
            continue
    if content is None:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

    elements: list[Element] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        # Détection Markdown.
        if line.startswith("#"):
            # Titre Markdown : on garde le texte sans les #.
            clean = line.lstrip("#").strip()
            if clean:
                elements.append(Element(
                    text=clean, element_type="Title",
                    section=_current_section(elements) or clean[:200],
                ))
        elif line[:2] in ("- ", "* ", "+ "):
            elements.append(Element(
                text=line[2:].strip(), element_type="ListItem",
                section=_current_section(elements),
            ))
        else:
            elements.append(Element(
                text=line, element_type="NarrativeText",
                section=_current_section(elements),
            ))
    return elements


# --------------------------------------------------------------- Concaténation


def elements_to_text(elements: list[Element]) -> str:
    """Concatène les textes des éléments (compat avec l'ancien extract_text).

    Utilisé pour le résumé LLM (analyse du document complet) et pour remplir
    ``document_content.raw_text`` (full-text au niveau document).
    """
    return "\n".join(el.text for el in elements if el.text).strip()


# -------------------------------------------------------------------- Chunking

# Paramètres du chunking sémantique.
CHUNK_MAX_CHARS = 1200        # taille cible d'un chunk (caractères)
CHUNK_OVERLAP = 150           # chevauchement entre chunks consécutifs (car.)
CHUNK_MIN_MERGE = 200         # fusionner les éléments plus petits que ça
CHUNK_TABLE_MAX_CHARS = 3000  # une table reste un chunk unique jusqu'à cette taille
# Taille minimale d'un chunk avant qu'un titre puisse déclencher une frontière.
# En dessous, on accumule (même à travers les titres) pour éviter la fragmentation
# en micro-chunks sur les docs à structure très titrée (ex. modes opératoires).
CHUNK_SECTION_MIN_CHARS = 400
# Nombre maximum de chunks par document. Au-delà, on tronque (on garde les
# premiers chunks = le début du document, largement suffisant pour le retrieval).
# Évite qu'un document monstrueux (ex: .doc de 8 Mo) ne génère des milliers de
# chunks et sature embeddings/stockage. 100 chunks × ~600 car = ~60 000 car indexés.
CHUNK_MAX_PER_DOC = 100


def chunk_elements(
    elements: list[Element],
    max_chars: int = CHUNK_MAX_CHARS,
    overlap: int = CHUNK_OVERLAP,
    min_merge: int = CHUNK_MIN_MERGE,
    section_min_chars: int = CHUNK_SECTION_MIN_CHARS,
) -> list[Chunk]:
    """Découpe les éléments en chunks cohérents (structure-aware).

    Règles :
      - Un titre (Title/Section) démarre un nouveau chunk UNIQUEMENT si le chunk
        courant a déjà atteint ``section_min_chars`` ; sinon on accumule (évite
        la fragmentation en micro-chunks sur les docs très titrés).
      - Les petits éléments (< ``min_merge``) sont fusionnés avec les suivants.
      - Une table reste un chunk dédié (non découpée) tant qu'elle < ``CHUNK_TABLE_MAX_CHARS``.
      - Les éléments plus longs que ``max_chars`` sont découpés par phrases avec
        chevauchement (``overlap``).
      - Métadonnées (page_number, section) = celles du premier élément du chunk.

    Renvoie une liste de ``Chunk`` avec ``chunk_index`` séquentiel.
    """
    chunks: list[Chunk] = []
    current_text = ""
    current_meta: dict = {"element_type": "NarrativeText", "page_number": None, "section": None}

    def _flush():
        nonlocal current_text
        text = current_text.strip()
        if text:
            chunks.append(Chunk(
                text=text,
                element_type=current_meta["element_type"],
                page_number=current_meta["page_number"],
                section=current_meta["section"],
            ))
        current_text = ""

    for el in elements:
        if not el.text or not el.text.strip():
            continue
        text = el.text.strip()

        # Frontière : un titre démarre un nouveau chunk, MAIS seulement si le
        # chunk courant est déjà assez gros (sinon on accumule pour éviter les
        # micro-chunks). On force aussi la frontière si on est déjà à max_chars.
        if el.element_type in _TITLE_TYPES and current_text:
            if len(current_text) >= section_min_chars or len(current_text) >= max_chars:
                _flush()

        # Table : chunk dédié si elle tient, sinon découpée.
        if el.element_type == "Table":
            _flush()
            if len(text) <= CHUNK_TABLE_MAX_CHARS:
                chunks.append(Chunk(
                    text=text, element_type="Table",
                    page_number=el.page_number, section=el.section,
                ))
            else:
                # Grande table : on la découpe en tranches de lignes.
                for sub in _split_long_text(text, max_chars, overlap):
                    chunks.append(Chunk(
                        text=sub, element_type="Table",
                        page_number=el.page_number, section=el.section,
                    ))
            # Initialiser le prochain chunk avec les métadonnées courantes.
            current_meta = {"element_type": "NarrativeText",
                            "page_number": el.page_number, "section": el.section}
            continue

        # Élément long seul : le découper (et flusher le courant d'abord).
        if len(text) > max_chars:
            _flush()
            for sub in _split_long_text(text, max_chars, overlap):
                chunks.append(Chunk(
                    text=sub, element_type=el.element_type,
                    page_number=el.page_number, section=el.section,
                ))
            continue

        # Élément normal : l'ajouter au chunk courant si la place le permet.
        separator = "\n" if current_text else ""
        candidate = current_text + separator + text
        if len(candidate) <= max_chars:
            if not current_text:
                # Premier élément du chunk : ses métadonnées deviennent celles du chunk.
                current_meta = {"element_type": el.element_type,
                                "page_number": el.page_number, "section": el.section}
            current_text = candidate
        else:
            _flush()
            current_text = text
            current_meta = {"element_type": el.element_type,
                            "page_number": el.page_number, "section": el.section}

    _flush()

    # Plafond anti-explosion : un document monstrueux (ex: .doc de 8 Mo avec
    # 200k éléments) ne doit pas générer des milliers de chunks. On garde les
    # CHUNK_MAX_PER_DOC premiers (début du doc, suffisant pour le retrieval).
    if len(chunks) > CHUNK_MAX_PER_DOC:
        chunks = chunks[:CHUNK_MAX_PER_DOC]

    # Indexer séquentiellement.
    for i, c in enumerate(chunks):
        c.chunk_index = i
    return chunks


def _split_long_text(text: str, max_chars: int, overlap: int) -> list[str]:
    """Découpe un texte long en sous-segments avec chevauchement.

    Privilégie les coupures sur fin de phrase (. ! ?) ou fin de ligne.
    """
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            # Chercher une coupure naturelle dans la dernière fenêtre.
            window = text[start:end]
            # Dernière ponctuation de phrase ou newline dans le dernier quart.
            search_start = max(start, end - max_chars // 4)
            cut = max(
                text.rfind(". ", search_start, end),
                text.rfind("! ", search_start, end),
                text.rfind("? ", search_start, end),
                text.rfind("\n", search_start, end),
            )
            if cut > start + max_chars // 2:
                end = cut + 1  # inclure la ponctuation
        parts.append(text[start:end].strip())
        if end >= n:
            break
        start = max(0, end - overlap)
    return [p for p in parts if p]
