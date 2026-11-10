"""Nickname blocklist: words from the main site's admin backend are replaced with * where they appear.

The folding rule is shared with the main site (ported to TypeScript) and documented in protocol/PROTOCOL.md,
section 昵称屏蔽. Indices are code points, not UTF-16 units.
"""
from __future__ import annotations

import unicodedata
from typing import Iterable


def fold(text: str) -> list[tuple[str, int]]:
    """Kept characters of [text], each with the index of the code point it came from.

    Each code point is NFKD-decomposed, then each resulting character is lowercased on its own; only characters
    of Unicode category L* or N* are kept.
    """
    out: list[tuple[str, int]] = []
    for i, c in enumerate(text):
        for d in unicodedata.normalize("NFKD", c):
            for ch in d.lower():
                if unicodedata.category(ch)[0] in "LN":
                    out.append((ch, i))
    return out


def folded(text: str) -> str:
    return "".join(ch for ch, _ in fold(text))


class Blocklist:
    def __init__(self, words: Iterable[str] = ()) -> None:
        self.words: set[str] = {f for f in map(folded, words) if f}
        self._lengths = sorted({len(w) for w in self.words})

    def __len__(self) -> int:
        return len(self.words)

    def _spans(self, text: str, first: bool = False) -> list[tuple[int, int]]:
        """Code point ranges (inclusive) of every match; with [first], stop at the first one."""
        if not self.words:
            return []
        kept = fold(text)
        s = "".join(ch for ch, _ in kept)
        spans: list[tuple[int, int]] = []
        for start in range(len(s)):
            for n in self._lengths:
                if start + n > len(s):
                    break
                if s[start:start + n] in self.words:
                    spans.append((kept[start][1], kept[start + n - 1][1]))
                    if first:
                        return spans
        return spans

    def hits(self, text: str) -> bool:
        return bool(self._spans(text, first=True))

    def mask(self, text: str) -> str:
        spans = self._spans(text)
        if not spans:
            return text
        chars = list(text)
        for a, b in spans:
            for i in range(a, b + 1):
                chars[i] = "*"
        return "".join(chars)
