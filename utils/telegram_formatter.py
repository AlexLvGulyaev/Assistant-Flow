import re


_SUBSCRIPT_MAP = str.maketrans("0123456789", "₀₁₂₃₄₅₆₇₈₉")


def _to_subscript_digits(match: re.Match[str]) -> str:
    return match.group(1) + match.group(2).translate(_SUBSCRIPT_MAP)


def format_for_telegram(text: str) -> str:
    formatted = text or ""

    # Remove LaTeX wrappers.
    formatted = formatted.replace("$$", "")
    formatted = formatted.replace("\\[", "").replace("\\]", "")
    formatted = formatted.replace("\\(", "").replace("\\)", "")
    formatted = formatted.replace("$", "")

    # Simplify common LaTeX commands.
    formatted = re.sub(r"\\(?:left|right)\b", "", formatted)
    formatted = re.sub(r"\\mathrm\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", r"\1", formatted)
    formatted = re.sub(r"\\text\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}", r"\1", formatted)

    # Normalize arrows.
    formatted = formatted.replace("\\rightarrow", "→")
    formatted = formatted.replace("=>", "→")
    formatted = formatted.replace("->", "→")

    # Convert indexed forms to readable unicode subscripts:
    # CO_{2} -> CO₂, H_2O -> H₂O, C_6H_12O_6 -> C₆H₁₂O₆
    formatted = re.sub(r"([A-Za-zА-Яа-я])_\{(\d+)\}", _to_subscript_digits, formatted)
    formatted = re.sub(r"([A-Za-zА-Яа-я])_(\d+)", _to_subscript_digits, formatted)

    # Remove redundant slashes before regular characters after known replacements.
    formatted = re.sub(r"\\([A-Za-zА-Яа-я])", r"\1", formatted)

    # Clean spacing around operators while preserving paragraphs.
    formatted = re.sub(r"\s*\+\s*", " + ", formatted)
    formatted = re.sub(r"\s*→\s*", " → ", formatted)
    formatted = re.sub(r"[ \t]+", " ", formatted)

    # Collapse excessive empty lines, keep paragraph separation.
    formatted = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", formatted)
    formatted = re.sub(r"[ \t]+\n", "\n", formatted)

    return formatted.strip()
