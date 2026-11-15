"""Where to cut a long paragraph into display blocks."""
import re

# Inline and display formulas, located the same way the source preview renders
# them: `\$` is a literal dollar sign, an inline formula starts and ends with a
# non-space character, and OCR sometimes writes the closing delimiter as `\$`.
_FORMULA_RE = re.compile(
    r"(?<!\\)\$\$[^$]+\$\$"
    r"|(?<!\\)\$[^\s$](?:[^$\n]*?[^\s$\\])?(?:\$(?!\d)|\\\$(?=\s|$))"
)

# A formula may start inside the window and end after it.
_FORMULA_LOOKAHEAD = 600


def find_paragraph_cut(remaining: str, max_chars: int, punctuation: str) -> int:
    """Length of the next block to take from `remaining` (longer than `max_chars`).

    Prefers the last sentence punctuation in the window, then the last space,
    then a hard cut at `max_chars`. A cut never lands inside a formula or on a
    decimal point ("p = .05", "3.57") when another place is available: half a
    formula cannot be rendered, and half a number reads as a different number.
    """
    window = remaining[:max_chars]
    spans = [
        (match.start(), match.end())
        for match in _FORMULA_RE.finditer(remaining[: max_chars + _FORMULA_LOOKAHEAD])
    ]

    def safe(index: int) -> bool:
        """Whether the text may be cut right after `index`."""
        if any(start <= index < end - 1 for start, end in spans):
            return False
        if window[index] in ".:" and remaining[index + 1 : index + 2].isdigit():
            return False
        return True

    def last_safe(chars: str, minimum: float) -> int:
        for index in range(len(window) - 1, int(minimum) - 1, -1):
            if window[index] in chars and safe(index):
                return index
        return -1

    # The cut used when nothing needs protecting: last punctuation, else last
    # space, else the hard limit.
    cut = max(window.rfind(char) for char in punctuation)
    if cut < max_chars * 0.55:
        cut = window.rfind(" ")
    if cut < max_chars * 0.55:
        cut = max_chars - 1
    if safe(cut):
        return cut + 1

    # A shorter block is better than a broken formula, so the search goes on
    # into the first half of the window before giving up.
    for minimum in (max_chars * 0.55, max_chars * 0.25):
        for chars in (punctuation, " "):
            alternative = last_safe(chars, minimum)
            if alternative >= 0:
                return alternative + 1

    # Nowhere safe (e.g. one very long formula): cut as before.
    return cut + 1
