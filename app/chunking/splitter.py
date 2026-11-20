"""抽出したテキストを、検索しやすい大きさ(チャンク)に分割する。

- 段落 → 文(。！？や改行)の順に区切り、文の途中では切らない
- 隣り合うチャンクに少し重なり(overlap)を持たせ、文脈の切れ目で情報が失われるのを防ぐ
- ページをまたいで結合しない(出典のページ番号を正確に保つため)
"""
import re
from dataclasses import dataclass

from app.parsers import ParsedSection

DEFAULT_MAX_CHARS = 500
DEFAULT_OVERLAP = 80

# 文末(。！？!?)の直後、または改行で区切る
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？!?])|\n+")


@dataclass
class Chunk:
    text: str
    page: int | None
    index: int  # 資料全体での通し番号(0始まり)


def _split_units(text: str, max_chars: int) -> list[str]:
    """文単位に分け、max_chars を超える文はさらに強制分割する。"""
    units = []
    for s in _SENTENCE_SPLIT.split(text):
        s = s.strip()
        if not s:
            continue
        while len(s) > max_chars:
            units.append(s[:max_chars])
            s = s[max_chars:]
        units.append(s)
    return units


def _split_section(text: str, max_chars: int, overlap: int) -> list[str]:
    units = _split_units(text, max_chars)
    chunks: list[str] = []
    cur: list[str] = []
    cur_len = 0
    for u in units:
        if cur and cur_len + len(u) > max_chars:
            chunks.append("".join(cur))
            # 末尾の文を overlap 文字以内で次のチャンクに引き継ぐ
            carry: list[str] = []
            carry_len = 0
            for prev in reversed(cur):
                if carry_len + len(prev) > overlap:
                    break
                carry.insert(0, prev)
                carry_len += len(prev)
            cur, cur_len = carry, carry_len
        cur.append(u)
        cur_len += len(u)
    if cur:
        chunks.append("".join(cur))
    return chunks


def split_sections(
    sections: list[ParsedSection],
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[Chunk]:
    if max_chars <= 0 or not 0 <= overlap < max_chars:
        raise ValueError("max_chars は正の数、overlap は 0 以上 max_chars 未満にしてください。")
    result: list[Chunk] = []
    for sec in sections:
        for text in _split_section(sec.text, max_chars, overlap):
            result.append(Chunk(text=text, page=sec.page, index=len(result)))
    return result
