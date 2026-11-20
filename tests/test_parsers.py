import pymupdf
import pytest
from docx import Document

from app.parsers import ParseError, parse_file


def test_txt_utf8_and_cp932(tmp_path):
    a = tmp_path / "a.txt"
    a.write_text("有給休暇の申請方法", encoding="utf-8")
    b = tmp_path / "b.txt"
    b.write_bytes("経費精算の手順".encode("cp932"))
    assert parse_file(a)[0].text == "有給休暇の申請方法"
    assert parse_file(b)[0].text == "経費精算の手順"


def test_docx_paragraph_and_table(tmp_path):
    p = tmp_path / "a.docx"
    d = Document()
    d.add_paragraph("第1章 総則")
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text = "項目"
    t.rows[0].cells[1].text = "内容"
    d.save(p)
    text = parse_file(p)[0].text
    assert "第1章 総則" in text and "項目 | 内容" in text


def test_pdf_pages(tmp_path):
    p = tmp_path / "a.pdf"
    doc = pymupdf.open()
    for s in ("page one", "page two"):
        doc.new_page().insert_text((72, 72), s)
    doc.save(p)
    secs = parse_file(p)
    assert [s.page for s in secs] == [1, 2]
    assert "page two" in secs[1].text


def test_errors(tmp_path):
    empty = tmp_path / "e.txt"
    empty.write_text("   ")
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    other = tmp_path / "x.xlsx"
    other.write_text("x")
    for f in (empty, bad, other):
        with pytest.raises(ParseError):
            parse_file(f)
