"""CSV出力の共通処理。"""


def cell(v) -> str:
    """CSVの数式インジェクション対策: 先頭が = + - @ などなら ' を付けて文字列として扱わせる。"""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@", "\t", "\r") else v
