"""テキストファイルを読む(文字コードを自動で試す)。"""
from pathlib import Path

from app.parsers.base import ParsedSection, ParseError

# 日本語のテキストでよく使われる順
_ENCODINGS = ("utf-8-sig", "cp932", "utf-16")


def parse_txt(path: Path) -> list[ParsedSection]:
    data = path.read_bytes()
    for enc in _ENCODINGS:
        try:
            text = data.decode(enc).strip()
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ParseError("文字コードを判別できませんでした。UTF-8で保存し直してください。")
    return [ParsedSection(text=text)] if text else []
