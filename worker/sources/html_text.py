"""Shared HTML-to-text helper for source adapters (Phase 4.2B, stdlib only).

Small ``html.parser``-based extractor: drops script/style content, unescapes
entities (``&nbsp;`` etc.), collapses whitespace, preserves line breaks for
block elements. Used by the Lever parser; the Greenhouse parser predates it
and keeps its own equivalent implementation (left untouched by design).
"""

import re
from html import unescape
from html.parser import HTMLParser

_WS = re.compile(r"\s+")
_BLOCK_TAGS = ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "ul", "ol")


class _TextExtractor(HTMLParser):
    """Collect visible text; skip script/style content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._parts: list = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag in ("script", "style"):
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self._parts.append("\n")

    def handle_endtag(self, tag) -> None:
        if tag in ("script", "style") and self._skip_depth:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS and tag != "br":
            self._parts.append("\n")

    def handle_data(self, data) -> None:
        if not self._skip_depth:
            self._parts.append(data)

    def text(self) -> str:
        raw = unescape("".join(self._parts))
        lines = [_WS.sub(" ", line).strip() for line in raw.split("\n")]
        return "\n".join(line for line in lines if line)


def html_to_text(html: object) -> str:
    """Convert HTML to clean plain text ('' for missing/non-string input)."""
    if not isinstance(html, str) or not html.strip():
        return ""
    if "<" not in html:
        return _WS.sub(" ", html).strip()
    extractor = _TextExtractor()
    try:
        extractor.feed(html)
        extractor.close()
    except Exception:
        return _WS.sub(" ", unescape(html)).strip()
    return extractor.text()
