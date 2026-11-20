import pytest

from app.chunking import split_sections
from app.parsers import ParsedSection


def test_short_text_is_one_chunk():
    chunks = split_sections([ParsedSection("短い文章です。", page=1)])
    assert len(chunks) == 1 and chunks[0].page == 1 and chunks[0].index == 0


def test_long_text_split_with_overlap_and_no_loss():
    sentences = [f"これは{i}番目の文です。" for i in range(100)]
    chunks = split_sections([ParsedSection("".join(sentences))], max_chars=100, overlap=20)
    assert len(chunks) > 1
    assert all(len(c.text) <= 100 for c in chunks)
    joined = "".join(c.text for c in chunks)
    for s in sentences:  # どの文も失われない
        assert s in joined
    # 隣のチャンクと重なっている
    assert chunks[0].text[-10:] in chunks[1].text
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_pages_not_merged():
    secs = [ParsedSection("一ページ目。", page=1), ParsedSection("二ページ目。", page=2)]
    chunks = split_sections(secs)
    assert [c.page for c in chunks] == [1, 2]
    assert [c.index for c in chunks] == [0, 1]


def test_very_long_sentence_is_force_split():
    chunks = split_sections([ParsedSection("あ" * 1200)], max_chars=500, overlap=50)
    assert all(len(c.text) <= 500 for c in chunks)
    assert sum(len(c.text) for c in chunks) >= 1200


def test_invalid_args():
    with pytest.raises(ValueError):
        split_sections([], max_chars=100, overlap=100)
