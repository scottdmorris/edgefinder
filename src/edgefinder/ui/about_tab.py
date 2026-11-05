"""How it works and what's new, read from the project's own documents so the
app and the repo never disagree."""

from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
DOCS = {"How it works": ROOT / "docs" / "METHODOLOGY.md",
        "What's new": ROOT / "CHANGELOG.md"}


def load_doc(path: Path) -> str:
    """The document's text, or a plain note if it can't be read."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return f"_{path.name} isn't available right now._"


def render() -> None:
    st.subheader("About")
    tabs = st.tabs(list(DOCS))
    for tab, path in zip(tabs, DOCS.values()):
        with tab:
            st.markdown(load_doc(path))
