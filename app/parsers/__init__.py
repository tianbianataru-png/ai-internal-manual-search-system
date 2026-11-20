"""拡張子に応じて適切なパーサーを選ぶ入口。"""
from pathlib import Path

from app.parsers.base import ParsedSection, ParseError
from app.parsers.docx_parser import parse_docx
from app.parsers.pdf_parser import parse_pdf
from app.parsers.txt_parser import parse_txt

_PARSERS = {".pdf": parse_pdf, ".docx": parse_docx, ".txt": parse_txt}

__all__ = ["ParsedSection", "ParseError", "parse_file"]


def parse_file(path: Path) -> list[ParsedSection]:
    """ファイルからテキストを抽出する。テキストが取れなければ ParseError。"""
    path = Path(path)
    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        raise ParseError(f"未対応のファイル形式です: {path.suffix}")
    sections = parser(path)
    if not sections:
        raise ParseError("テキストを取り出せませんでした。画像だけのPDF(スキャン)は未対応です。")
    return sections
