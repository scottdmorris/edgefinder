from edgefinder.ui import about_tab


def test_the_documents_the_app_shows_exist_and_are_not_empty():
    for name, path in about_tab.DOCS.items():
        text = about_tab.load_doc(path)
        assert len(text) > 500, name
        assert "isn't available" not in text, name


def test_the_how_it_works_page_is_the_methodology_document():
    text = about_tab.load_doc(about_tab.DOCS["How it works"])
    assert "How Ball Knowledge predicts player stats" in text


def test_a_missing_document_gives_a_plain_note_instead_of_an_error(tmp_path):
    note = about_tab.load_doc(tmp_path / "gone.md")
    assert "gone.md" in note and "isn't available" in note
