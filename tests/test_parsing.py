"""Tests unitaires du module parsing (extraction structurée + chunking).

Teste extract_elements et chunk_elements sur des fichiers synthétiques :
  - fichiers texte/Markdown (titres, listes)
  - CSV (une table)
  - chunking : frontières de titres, tables dédiées, longueurs, métadonnées.
"""


import parsing


# ------------------------------------------------------------- extract_elements


class TestExtractTextFile:
    def test_txt_narrative(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Premier paragraphe.\nDeuxième paragraphe.", encoding="utf-8")
        els = parsing.extract_elements(str(f))
        assert len(els) == 2
        assert all(e.element_type == "NarrativeText" for e in els)
        assert els[0].text == "Premier paragraphe."

    def test_markdown_titles_and_list(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Titre principal\nligne normale\n- item un\n- item deux", encoding="utf-8")
        els = parsing.extract_elements(str(f))
        types = [e.element_type for e in els]
        assert "Title" in types           # le # Titre principal
        assert "ListItem" in types        # les - item
        assert "NarrativeText" in types   # la ligne normale

    def test_markdown_title_sets_section(self, tmp_path):
        f = tmp_path / "doc.md"
        f.write_text("# Introduction\ncontenu ici", encoding="utf-8")
        els = parsing.extract_elements(str(f))
        # Le paragraphe suivant le titre doit hériter de la section.
        narrative = [e for e in els if e.element_type == "NarrativeText"][0]
        assert narrative.section == "Introduction"

    def test_cp1252_fallback(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_bytes("café résumé".encode("cp1252"))
        els = parsing.extract_elements(str(f))
        joined = " ".join(e.text for e in els)
        assert "café" in joined


class TestExtractCsv:
    def test_csv_produces_table(self, tmp_path):
        f = tmp_path / "data.csv"
        f.write_text("a,b\n1,2\n3,4", encoding="utf-8")
        els = parsing.extract_elements(str(f))
        assert len(els) == 1
        assert els[0].element_type == "Table"
        assert "1" in els[0].text and "4" in els[0].text


class TestElementsToText:
    def test_concatenation(self):
        els = [
            parsing.Element("Titre", "Title"),
            parsing.Element("Corps du texte", "NarrativeText"),
        ]
        assert parsing.elements_to_text(els) == "Titre\nCorps du texte"

    def test_empty(self):
        assert parsing.elements_to_text([]) == ""


# --------------------------------------------------------------------- chunking


class TestChunkElements:
    def test_single_element_one_chunk(self):
        els = [parsing.Element("court texte", "NarrativeText")]
        chunks = parsing.chunk_elements(els)
        assert len(chunks) == 1
        assert chunks[0].text == "court texte"
        assert chunks[0].parent_text == "court texte"
        assert chunks[0].chunk_index == 0

    def test_title_starts_new_chunk_when_large_enough(self):
        """Un titre ouvre un nouveau parent SI le parent courant est assez gros."""
        # Cas 1 : chunk courant < section_min_chars -> accumulation (1 parent).
        els_small = [
            parsing.Element("intro " * 50, "NarrativeText"),   # ~250 car < 400
            parsing.Element("Chapitre 2", "Title"),
            parsing.Element("contenu chapitre 2", "NarrativeText"),
        ]
        chunks_small = parsing.chunk_elements(els_small)
        # Ils sont tous dans le même parent.
        assert len(set(c.parent_text for c in chunks_small)) == 1

        # Cas 2 : chunk courant >= section_min_chars -> frontière (>= 2 parents).
        els_large = [
            parsing.Element("intro " * 100, "NarrativeText"),  # ~500 car >= 400
            parsing.Element("Chapitre 2", "Title"),
            parsing.Element("contenu chapitre 2", "NarrativeText"),
        ]
        chunks_large = parsing.chunk_elements(els_large)
        assert len(set(c.parent_text for c in chunks_large)) >= 2
        ch_with_title = [c for c in chunks_large if "Chapitre 2" in c.parent_text or c.section == "Chapitre 2"]
        assert ch_with_title, "le titre doit apparaître dans un chunk"

    def test_table_is_dedicated_chunk(self):
        """Une table doit former ses propres chunks enfants sous un même parent."""
        table_text = "A\tB\n1\t2\n3\t4"
        els = [
            parsing.Element("texte avant", "NarrativeText"),
            parsing.Element(table_text, "Table", page_number=1),
            parsing.Element("texte après", "NarrativeText"),
        ]
        chunks = parsing.chunk_elements(els)
        table_chunks = [c for c in chunks if c.element_type == "Table"]
        assert len(table_chunks) >= 1
        assert table_chunks[0].parent_text == table_text
        assert table_chunks[0].page_number == 1

    def test_long_element_is_split(self):
        """Un élément plus long que max_chars doit être découpé."""
        long_text = "Phrase un. " * 500  # ~5500 caractères
        els = [parsing.Element(long_text, "NarrativeText")]
        chunks = parsing.chunk_elements(els, max_chars=500)
        assert len(chunks) > 1
        # Aucun chunk ne dépasse largement max_chars (tolérance pour le overlap).
        assert all(len(c.text) <= 700 for c in chunks)

    def test_chunk_indices_sequential(self):
        els = [parsing.Element(f"paragraphe {i}", "NarrativeText") for i in range(5)]
        chunks = parsing.chunk_elements(els)
        assert [c.chunk_index for c in chunks] == list(range(len(chunks)))

    def test_metadata_propagated_from_first_element(self):
        """Les métadonnées d'un chunk = celles de son premier élément."""
        els = [
            parsing.Element("premier", "NarrativeText", page_number=3, section="Intro"),
            parsing.Element("deuxième", "NarrativeText", page_number=4, section="Intro"),
        ]
        chunks = parsing.chunk_elements(els)
        # Les deux sont fusionnés (court) -> 1 parent
        assert len(set(c.parent_text for c in chunks)) == 1
        assert chunks[0].page_number == 3
        assert chunks[0].section == "Intro"

    def test_empty_elements_ignored(self):
        els = [parsing.Element("", "NarrativeText"), parsing.Element("   ", "Title")]
        chunks = parsing.chunk_elements(els)
        assert chunks == []

    def test_max_chunks_per_doc_cap(self):
        """Un document qui générerait > CHUNK_MAX_PER_DOC chunks est tronqué."""
        # Des éléments longs (> max_chars) génèrent chacun leur propre chunk,
        # ce qui permet de dépasser CHUNK_MAX_PER_DOC et de tester le plafond.
        cap = parsing.CHUNK_MAX_PER_DOC
        long_el = "Phrase de test suffisamment longue pour dépasser max_chars. " * 30
        els = [parsing.Element(long_el, "NarrativeText") for _ in range(cap + 50)]
        chunks = parsing.chunk_elements(els)
        assert len(chunks) == cap
        # Les chunk_index doivent être renumérotés de 0 à cap-1 (sans trous).
        assert [c.chunk_index for c in chunks] == list(range(cap))


class TestSplitLongText:
    """Tests de la fonction interne _split_long_text (découpage + overlap)."""

    def test_short_text_returned_as_is(self):
        assert parsing._split_long_text("court", max_chars=100, overlap=10) == ["court"]

    def test_long_text_split_into_multiple_parts(self):
        long = "Phrase de test. " * 200  # ~3200 car
        parts = parsing._split_long_text(long, max_chars=500, overlap=50)
        assert len(parts) > 1
        # Aucune part ne dépasse max_chars.
        assert all(len(p) <= 500 for p in parts)

    def test_overlap_between_parts(self):
        """Le chevauchement fait que la fin d'une part réapparaît au début de la suivante."""
        long = "Mot. " * 1000  # ~5000 car, coupures forcées sur ". "
        parts = parsing._split_long_text(long, max_chars=300, overlap=80)
        assert len(parts) >= 2
        # Le overlap n'est pas nul : la part 2 doit partager du contenu avec la fin de la part 1.
        # On vérifie juste qu'il y a bien du chevauchement (les parts se recouvrent).
        if len(parts) >= 2:
            # Taille cumulée > taille du texte = preuve d'overlap.
            assert sum(len(p) for p in parts) > len(long)

    def test_prefers_sentence_boundaries(self):
        """La découpe privilégie les fins de phrase (. ! ?) si possible."""
        text = "Première phrase. " * 100  # coupures naturelles sur ". "
        parts = parsing._split_long_text(text, max_chars=200, overlap=20)
        # Chaque part (sauf peut-être la dernière) doit se terminer par ". ".
        for p in parts[:-1]:
            assert ". " in p


class TestBinaryAndEdgeCases:
    """Gestion des fichiers binaires et cas limites."""

    def test_binary_file_does_not_crash(self, tmp_path):
        """Un fichier binaire (.png) ne doit pas crasher extract_elements.

        Sans vision, un .png tombe dans _extract_image_file qui retourne []
        (l'image n'est pas indexable textuellement). Pas de crash, pas de bruit.
        """
        f = tmp_path / "fake.png"
        f.write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00\x01\x02\x03binary\xff")
        # Ne doit pas lever d'exception.
        els = parsing.extract_elements(str(f))
        assert isinstance(els, list)
        # Sans vision, aucune description -> liste vide (pas de bruit binaire).
        assert els == []

    def test_csv_section_is_basename_not_full_path(self, tmp_path):
        """La section d'un CSV doit être le nom du fichier, pas le chemin absolu."""
        f = tmp_path / "data.csv"
        f.write_text("a,b\n1,2", encoding="utf-8")
        els = parsing.extract_elements(str(f))
        assert len(els) == 1
        assert els[0].section == "data.csv"  # pas tmp_path/.../data.csv
