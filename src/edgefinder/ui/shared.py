"""Streamlit helpers shared across tabs."""


def fmt_american(american: float | None) -> str:
    """American odds with an explicit plus sign: 150 -> '+150', -110 -> '-110'."""
    if american is None:
        return "—"
    return f"+{american:.0f}" if american > 0 else f"{american:.0f}"
