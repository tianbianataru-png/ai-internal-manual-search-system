"""Word(.docx)から段落と表のテキストを取り出す。"""
from pathlib import Path

from docx import Document

from app.parsers.base import ParsedSection, ParseError


def parse_docx(path: Path) -> list[ParsedSection]:
    try:
        doc = Document(str(path))
    except Exception as e:
        raise ParseError("Wordファイルを開けませんでした。破損しているか、.docx形式ではない可能性があります。") from e
    lines = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    text = "\n".join(lines)
    return [ParsedSection(text=text)] if text else []
