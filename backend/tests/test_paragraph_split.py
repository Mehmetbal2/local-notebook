import re

from workers.parsers.html_parser import _split_long_paragraph as split_html
from workers.parsers.txt_parser import _split_long_paragraph as split_txt

PROSE = "The adolescents told three stories about turning points in their lives. "


def _unescaped_dollars(text: str) -> int:
    return len(re.findall(r"(?<!\\)\$", text))


def test_formula_is_not_cut_at_its_decimal_point():
    text = PROSE * 7 + r"The effect was small, $p=.02,\;\eta_{p}^{2}=.05$ and then " + PROSE * 6
    for split in (split_txt, split_html):
        chunks = split(text, max_chars=600)
        assert len(chunks) > 1
        assert all(_unescaped_dollars(chunk) % 2 == 0 for chunk in chunks)
        assert any(r"$p=.02,\;\eta_{p}^{2}=.05$" in chunk for chunk in chunks)


def test_run_of_formulas_stays_paired():
    stats = r"$F(2,\,80)=4.23$ $p=.02,$ $\eta_{p}^{2}=.10,$ $F(2,\ 82)=8.34,$ $p=.001,$ "
    chunks = split_txt(PROSE * 5 + stats * 12 + PROSE * 3, max_chars=600)
    assert all(_unescaped_dollars(chunk) % 2 == 0 for chunk in chunks)


def test_plain_number_is_not_cut_at_its_decimal_point():
    text = "word " * 116 + "F(2, 246) = 5.83, p = 0.03 " + "word " * 60
    chunks = split_txt(text, max_chars=600)
    assert any("5.83" in chunk for chunk in chunks)
    assert any("0.03" in chunk for chunk in chunks)


def test_escaped_dollar_is_not_a_formula_delimiter():
    text = PROSE * 8 + r"Freud, S\$. (1961). " + PROSE * 8
    chunks = split_txt(text, max_chars=600)
    assert " ".join(chunks) == " ".join(text.split())


def test_prose_is_cut_at_the_last_sentence_end():
    chunks = split_txt(PROSE * 20, max_chars=600)
    assert all(chunk.endswith(".") for chunk in chunks)
    assert all(len(chunk) <= 600 for chunk in chunks)


def test_no_text_is_lost():
    text = PROSE * 4 + "$" + "x+" * 500 + "y$ " + PROSE * 4 + "unbroken" * 200
    for split in (split_txt, split_html):
        assert "".join(split(text, max_chars=600)).replace(" ", "") == text.replace(" ", "")
