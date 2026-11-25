"""PDF からページ単位でテキストを取り出す。"""
from pathlib import Path

import pymupdf

from app.parsers.base import ParsedSection, ParseError


def parse_pdf(path: Path) -> list[ParsedSection]:
    try:
        # ファイルを直接開くと、壊れたPDFのとき Windows でファイルが開いたまま残り削除できなくなる。
        # そのため中身を読み込んでから開く。
        doc = pymupdf.open(stream=path.read_bytes(), filetype="pdf")
    except Exception as e:
        raise ParseError("PDFを開けませんでした。破損しているか、PDFではない可能性があります。") from e
    with doc:
        if doc.needs_pass:
            raise ParseError("パスワード付きPDFは読み込めません。")
        sections = []
        for i, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            if text:
                sections.append(ParsedSection(text=text, page=i))
    return sections
