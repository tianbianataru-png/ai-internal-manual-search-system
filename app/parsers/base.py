"""パーサー共通の型とエラー。"""
from dataclasses import dataclass


class ParseError(Exception):
    """ファイルを読み取れなかったときのエラー(メッセージは利用者に見せてよい)。"""


@dataclass
class ParsedSection:
    """抽出したテキスト1区切り。page は出典表示用(PDFのみ。他は None)。"""
    text: str
    page: int | None = None
