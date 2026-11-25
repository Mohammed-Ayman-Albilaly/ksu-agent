#!/usr/bin/env python3
"""Turn one downloaded study plan source into data/processed/plans/<id>.json.

The plan id is looked up in the plans list (backend/config/plans.toml) and its
SHA-256 in the meta file written by fetch_plans.py; neither the URL nor the file
name is hard-coded here.

Two parsers, chosen by the plan's ``form``:

    pdf         the page text pymupdf extracts, one table cell per line. A row is a
                course code (or an elective placeholder, ``--``) followed by its
                title, its credit hours and then its prerequisites. A level starts
                at a "LEVEL (SEMESTER) N" (or "Level N") heading, and a
                "Total N CH" line closes it.
    html_table  the HTML inside a JSON:API node's data.attributes.body.value.
                A level table is the <table> that directly follows a
                "المستوى <ordinal>" heading; each row is
                code | title | credit hours | prerequisites.

Both parsers fail loudly instead of writing a plan that is quietly wrong:

    * a PDF page with no extractable text is an error naming the page, so a scan
      cannot become an empty level;
    * a course row with no code or no parseable credit hours is an error naming
      the level and the row, so a row is never dropped;
    * a row that reads as two credit-hour numbers (a course row whose code cell was
      not recognised) is an error, not a silent merge into the row above;
    * the per-level "Total N CH" line is skipped as a course and used as a check:
      the parsed courses must add up to it, and a mismatch is an error naming the
      level. A "Grand Total" is checked the same way.

A source that does not label its rows by level — a guide whose first year covers
two levels at once, or a plan whose levels sit side by side on the page — is
refused with an error naming the row, rather than read into the wrong level.

Output (git-ignored):
    data/processed/plans/<id>.json
    { "program", "title", "source_url", "program_url", "language",
      "retrieved_at", "source_sha256", "levels": [...] }

A level is ``{"level": 1, "total_credits": 16, "courses": [...]}`` where
``total_credits`` is present only when the source states a total. A course is
``{"code", "title", "credits", "prerequisites"}``; a row that names no single
course — an elective placeholder, or a choice between named courses — is recorded
with ``"code": null``, ``"elective": true`` and, when the source names them,
``"options": [...]``, so its credit hours still count towards the level total
instead of vanishing.

Usage:
    python backend/scripts/parse_plan.py --plan swe
    python backend/scripts/parse_plan.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import pymupdf

from fetch_plans import (
    DEFAULT_CONFIG,
    DEFAULT_OUT_DIR as DEFAULT_RAW_DIR,
    REPO_ROOT,
    PlanSource,
    load_plans,
    read_meta,
    sha256_file,
)
from parse_source import clean_text

DEFAULT_OUT_DIR = REPO_ROOT / "data" / "processed" / "plans"

TATWEEL = "\u0640"
ARABIC_INDIC_DIGITS = "\u0660\u0661\u0662\u0663\u0664\u0665\u0666\u0667\u0668\u0669"
_DIGITS_TO_ASCII = str.maketrans(ARABIC_INDIC_DIGITS, "0123456789")
# Directional marks and the Arabic letter mark carry no text but split words.
_INVISIBLE = dict.fromkeys(map(ord, "\u200e\u200f\u061c\u202a\u202b\u202c\u202d\u202e"), None)


class PlanError(ValueError):
    """A source that cannot be turned into a plan that is known to be correct."""


# --------------------------------------------------------------------------
# Shared helpers
# --------------------------------------------------------------------------


def normalise_digits(text: str) -> str:
    """Map Arabic-Indic digits to ASCII, keeping their order.

    ``parse_source.fix_arabic_digits`` reverses each run, because pymupdf extracts
    Arabic numbers from a PDF in visual order. The HTML in a JSON:API body is in
    logical order, so reversing it would turn ١٤٠ (140) into ٠٤١ (041) — a course
    code that does not exist. Only the digit mapping is applied here.
    """
    return text.translate(_DIGITS_TO_ASCII)


def normalise_code(text: str) -> str:
    """Upper-case a course code and collapse its spaces: "csc  212" -> "CSC 212"."""
    return " ".join(text.split()).upper()


def clean_html_text(text: str) -> str:
    """Normalise HTML cell text: NFKC, no tatweel or bidi marks, ASCII digits."""
    folded = unicodedata.normalize("NFKC", text).replace(TATWEEL, "")
    folded = folded.translate(_INVISIBLE).replace("\xa0", " ")
    return normalise_digits(folded)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# --------------------------------------------------------------------------
# The PDF parser
# --------------------------------------------------------------------------

# A page of the SWE plan carries "LEVEL (SEMESTER) 1"; other guides write
# "Level 3" and "LEVEL (SEMESTER) 9 Summer".
_LEVEL_RE = re.compile(r"^(?:LEVEL\s*\(\s*SEMESTER\s*\)|Level)\s*(\d{1,2})\b", re.IGNORECASE)
# A heading that names two levels at once, e.g. "First Common Year (Levels 1–2)".
_LEVEL_RANGE_RE = re.compile(r"Levels?\s*\d{1,2}\s*[–—-]\s*\d{1,2}", re.IGNORECASE)
_TOTAL_RE = re.compile(r"^(Grand\s+Total|Total)\b\s*(?:(\d{1,3})\s*CH)?$", re.IGNORECASE)
_CH_RE = re.compile(r"^(\d{1,3})(?:\s*CH)?$", re.IGNORECASE)
_CREDITS_RE = re.compile(r"^\d{1,2}$")
_CODE_RE = re.compile(r"^[A-Z]{2,5}\d?\s?\d{2,4}$")
_CODE_HEAD_RE = re.compile(r"^[A-Z]{2,5}\d?$")
_DIGITS_ONLY_RE = re.compile(r"^\d{2,4}$")
# "--" in the code column marks an elective the plan does not name.
_PLACEHOLDER_RE = re.compile(r"^(?:--+|—+|–+|-+)$")
# Codes inside a prerequisite cell, e.g. "CSC 113 SWE 211" or "95 CH Passed SWE 321".
_PREREQ_CODE_RE = re.compile(r"[A-Z]{2,5}\d?\s?\d{2,4}")


def extract_pages(pdf_path: Path) -> list[str]:
    """Raw text of every page, in document order."""
    with pymupdf.open(str(pdf_path)) as doc:
        if doc.needs_pass:
            doc.authenticate("")
        return [page.get_text() for page in doc]


def _page_lines(text: str) -> list[str]:
    """The non-empty lines of one page, with inner spaces collapsed.

    The page number is printed at the top of every page, above the "YEAR" and level
    headings. A bare number as a page's first line is that page number, not a course
    row's credit hours, so it is dropped here instead of being read as one.
    """
    lines: list[str] = []
    for raw in text.splitlines():
        line = " ".join(raw.split())
        if line:
            lines.append(line)

    if lines and _CREDITS_RE.match(lines[0]):
        return lines[1:]
    return lines


def _join_split_codes(lines: list[str]) -> list[str]:
    """Rejoin a code the PDF wrapped over two lines: "CHEM1" + "101".

    A bare upper-case word with at most one digit ("MATH", "CHEM1") followed by a
    line of 2-4 digits is one cell the extraction broke in two, so the two lines
    are joined with a space. A prerequisite written the same way ("MATH" + "101")
    is joined too, which is what lets it be read as a code.
    """
    joined: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if (
            _CODE_HEAD_RE.match(line)
            and index + 1 < len(lines)
            and _DIGITS_ONLY_RE.match(lines[index + 1])
        ):
            joined.append(f"{line} {lines[index + 1]}")
            index += 2
            continue
        joined.append(line)
        index += 1
    return joined


def _starts_row(lines: list[str], index: int) -> bool:
    """True when ``lines[index]`` opens a course row rather than being a prerequisite.

    A code-shaped line is ambiguous: "ENGS 100" is a prerequisite of the row above
    it in the SWE plan, while "MATH 151" opens the next row. The two are told
    apart by what follows: a row opens with a code and reaches its credit hours
    before the next code-shaped line, whereas a prerequisite is followed by another
    code (or by the level's total) first.
    """
    line = lines[index]
    if not (_CODE_RE.match(line) or _PLACEHOLDER_RE.match(line)):
        return False

    for following in lines[index + 1:]:
        if (
            _CODE_RE.match(following)
            or _PLACEHOLDER_RE.match(following)
            or _LEVEL_RE.match(following)
            or _TOTAL_RE.match(following)
        ):
            return False
        if _CREDITS_RE.match(following):
            return True
    return False


def _prerequisites(lines: list[str]) -> list[str]:
    """Course codes found in a prerequisite cell, in source order, deduplicated."""
    codes: list[str] = []
    for match in _PREREQ_CODE_RE.finditer(" ".join(lines)):
        code = normalise_code(match.group(0))
        if code not in codes:
            codes.append(code)
    return codes


def _finish_row(row: dict, level_no: int) -> dict:
    """Turn a row's raw lines into a course, or fail naming the level and the row.

    The title lines come before the credit hours and the prerequisite lines after
    them, and a prerequisite cell ends with its course codes. A second bare number,
    or a line after a prerequisite code, means the next course row was read as part
    of this one because its code or its credit hours were not recognised.
    """
    label = row["code"] if row["code"] else "--"
    credits: int | None = None
    title: list[str] = []
    prerequisite: list[str] = []
    code_seen = False

    for line in row["lines"]:
        if not _CREDITS_RE.match(line):
            if credits is not None:
                if _PLACEHOLDER_RE.match(line):
                    # An empty co-requisite cell, not a prerequisite.
                    continue
                if _CODE_RE.match(line):
                    code_seen = True
                elif code_seen:
                    raise PlanError(
                        f"level {level_no}: course row {label!r} has {line!r} "
                        f"after its prerequisites; a course row with no code or "
                        f"no credit hours may have been read as part of it "
                        f"(lines: {' / '.join(row['lines'])})"
                    )
                prerequisite.append(line)
            else:
                title.append(line)
            continue
        if credits is not None:
            raise PlanError(
                f"level {level_no}: course row {label!r} has a second "
                f"credit-hours number {line!r}; a row without a code may have "
                f"been read as part of it (lines: {' / '.join(row['lines'])})"
            )
        credits = int(line)

    if credits is None:
        raise PlanError(
            f"level {level_no}: course row {label!r} has no credit hours "
            f"(lines: {' / '.join(row['lines'])})"
        )

    course = {
        "code": row["code"],
        "title": " ".join(title),
        "credits": credits,
        "prerequisites": _prerequisites(prerequisite),
    }
    if row["elective"]:
        course["elective"] = True
    return course


def _close_level(level: dict | None, levels: list[dict]) -> None:
    """Check a level's courses against its stated total, then keep it."""
    if level is None:
        return
    if not level["courses"]:
        raise PlanError(f"level {level['level']} has no course rows")

    parsed_sum = sum(course["credits"] for course in level["courses"])
    if level["total"] is not None and parsed_sum != level["total"]:
        raise PlanError(
            f"level {level['level']}: the courses add up to {parsed_sum} CH "
            f"but the plan says {level['total']} CH"
        )

    finished = {"level": level["level"], "courses": level["courses"]}
    if level["total"] is not None:
        finished["total_credits"] = level["total"]
    levels.append(finished)


def parse_pdf_pages(pages: list[str]) -> list[dict]:
    """Parse the text of a PDF study plan into a list of levels.

    ``pages`` is the text of each page as pymupdf extracts it, one table cell per
    line. Nothing here touches the network or the file system, so the whole grammar
    can be tested on fixture text.
    """
    if not pages:
        raise PlanError("the PDF has no pages")

    for number, text in enumerate(pages, start=1):
        if not text.strip():
            raise PlanError(
                f"page {number} has no extractable text; the PDF may be a scan, "
                f"and an empty level would be a lie"
            )

    lines = _join_split_codes(
        [
            line
            for text in pages
            for line in _page_lines(clean_text(text))
        ]
    )

    levels: list[dict] = []
    level: dict | None = None
    row: dict | None = None
    grand_total: int | None = None
    ignored = 0
    index = 0

    while index < len(lines):
        line = lines[index]
        index += 1

        # The elective pools and the appendix tables follow the grand total and are
        # not part of any level, so they are not read as course rows.
        if grand_total is not None:
            ignored += 1
            continue

        if _LEVEL_RANGE_RE.search(line):
            raise PlanError(
                f"the heading {line!r} names more than one level; this table "
                f"does not say which level each of its rows belongs to"
            )

        match = _LEVEL_RE.match(line)
        if match:
            if row is not None:
                level["courses"].append(_finish_row(row, level["level"]))
                row = None
            _close_level(level, levels)
            level = {"level": int(match.group(1)), "courses": [], "total": None}
            continue

        match = _TOTAL_RE.match(line)
        if match:
            total = int(match.group(2)) if match.group(2) else None
            if total is None and index < len(lines):
                ch = _CH_RE.match(lines[index])
                if ch:
                    total = int(ch.group(1))
                    index += 1
            if total is None:
                raise PlanError(f"the line {line!r} does not say how many credit hours")

            if match.group(1).lower().startswith("grand"):
                if row is not None:
                    level["courses"].append(_finish_row(row, level["level"]))
                    row = None
                _close_level(level, levels)
                level = None
                grand_total = total
                parsed_sum = sum(
                    course["credits"] for kept in levels for course in kept["courses"]
                )
                if parsed_sum != total:
                    raise PlanError(
                        f"the levels add up to {parsed_sum} CH but the grand "
                        f"total says {total} CH"
                    )
                continue

            if level is None:
                raise PlanError(f"the total {line!r} appears before any level heading")
            if row is not None:
                level["courses"].append(_finish_row(row, level["level"]))
                row = None
            level["total"] = total
            _close_level(level, levels)
            level = None
            continue

        if _starts_row(lines, index - 1):
            if level is None:
                if _PLACEHOLDER_RE.match(line):
                    # A bullet in the prose before the first table is not a row.
                    continue
                raise PlanError(
                    f"the course row {line!r} appears before any level heading; "
                    f"the source does not label its rows by level"
                )
            if row is not None:
                level["courses"].append(_finish_row(row, level["level"]))
            row = {
                "code": None if _PLACEHOLDER_RE.match(line) else normalise_code(line),
                "elective": bool(_PLACEHOLDER_RE.match(line)),
                "lines": [],
            }
            continue

        if row is not None:
            row["lines"].append(line)

    if row is not None and level is not None:
        level["courses"].append(_finish_row(row, level["level"]))
    _close_level(level, levels)

    if not levels:
        raise PlanError("no levels found; the source does not carry a level table")
    if ignored:
        print(
            f"note: ignored {ignored} line(s) after the grand total "
            f"(elective pools and appendix tables, not level rows)",
            file=sys.stderr,
        )
    return levels


# --------------------------------------------------------------------------
# The HTML table parser
# --------------------------------------------------------------------------

_ARABIC_ORDINALS = {
    "الأول": 1,
    "الثاني": 2,
    "الثالث": 3,
    "الرابع": 4,
    "الخامس": 5,
    "السادس": 6,
    "السابع": 7,
    "الثامن": 8,
    "التاسع": 9,
    "العاشر": 10,
}
_HTML_LEVEL_RE = re.compile(
    r"المستوى\s+(" + "|".join(_ARABIC_ORDINALS) + r"|\d{1,2})"
)
_HEADER_CELL_RE = re.compile(
    r"^(?:رمز(?:\s+المقرر)?|الرمز|Code|Course\s+Code|Course\s+number)\b", re.IGNORECASE
)
_HTML_TOTAL_RE = re.compile(r"^(?:المجموع(?:\s+الفرعي)?|Total|Subtotal)\b", re.IGNORECASE)
# A course code in an Arabic table: letters then digits ("ريض 101", "هال 4xx",
# "CSC 111"), or the Arabic-Indic order digits then letters with no space
# between them ("١٤٠ريض", read as "140ريض" once the digits are ASCII).
_HTML_CODE_RE = re.compile(
    r"(?:[A-Za-z\u0621-\u064a]{2,6}\s?\d{1,4}[xX]{0,3}"
    r"|\d{2,4}[\u0621-\u064a]{2,6})"
)
# A code cell that starts with a dash or with x's names no course: it is a
# placeholder for an elective, the way "--" is in a PDF.
_HTML_PLACEHOLDER_RE = re.compile(r"^(?:-|[xX])")
_HTML_CREDITS_RE = re.compile(r"^(\d{1,2})(?:\s*\(.*\))?$")
_BLOCK_TAGS = {
    "p", "div", "h1", "h2", "h3", "h4", "h5", "h6",
    "li", "ul", "ol", "br", "section", "article", "tr", "table",
}


class _PlanHTMLParser(HTMLParser):
    """Collect the document's text runs and its tables, in document order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple[str, object]] = []
        self._text: list[str] = []
        self._depth = 0
        self._nested = False
        self._rows: list[list[list[str]]] | None = None
        self._row: list[list[str]] | None = None
        self._cell: list[str] | None = None

    def _flush(self) -> None:
        text = " ".join("".join(self._text).split())
        if text:
            self.events.append(("text", text))
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag in _BLOCK_TAGS:
            self._flush()
        if tag == "table":
            self._depth += 1
            if self._depth == 1:
                self._rows = []
                self.events.append(("table", self._rows))
            else:
                self._nested = True
        elif tag == "tr" and self._rows is not None and not self._nested:
            self._row = []
            self._rows.append(self._row)
        elif tag in ("td", "th") and self._row is not None and not self._nested:
            self._cell = []
            self._row.append(self._cell)

    def handle_endtag(self, tag):
        if tag in _BLOCK_TAGS:
            self._flush()
        if tag == "table":
            self._depth -= 1
            if self._depth == 0:
                self._rows = None
                self._nested = False
        elif tag == "tr":
            self._row = None
        elif tag in ("td", "th"):
            self._cell = None

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)
        elif self._depth == 0:
            self._text.append(data)


def parse_jsonapi_body(text: str) -> str:
    """The HTML held in a JSON:API node's data.attributes.body.value."""
    try:
        payload = json.loads(text)
    except ValueError as exc:
        raise PlanError(f"the downloaded file is not JSON: {exc}") from exc

    try:
        body = payload["data"]["attributes"]["body"]["value"]
    except (KeyError, TypeError) as exc:
        raise PlanError(
            "the JSON:API payload has no data.attributes.body.value"
        ) from exc
    if not isinstance(body, str) or not body.strip():
        raise PlanError("data.attributes.body.value is empty")
    return body


def _cell_text(cell: list[str]) -> str:
    """One cell's text, with its spaces collapsed."""
    return " ".join(clean_html_text(" ".join(cell)).split())


def _first_int(cells: list[str]) -> int | None:
    for cell in cells:
        match = _HTML_CREDITS_RE.match(cell)
        if match:
            return int(match.group(1))
    return None


def _html_codes(text: str) -> list[str]:
    """Every course code in a cell, in source order, deduplicated.

    One prerequisite cell can name several codes ("ريض 204 / كهر 207"), and one
    code cell can list alternatives ("١٠٣كيم ١٠٤كيم …": take one of these). A
    completed-hours requirement such as "120 ساعة" is not a code and is skipped.
    """
    codes: list[str] = []
    for match in _HTML_CODE_RE.finditer(text):
        code = normalise_code(match.group(0))
        if code not in codes:
            codes.append(code)
    return codes


def _level_in_text(text: str) -> int | None:
    """The level number named in a heading or caption row, if any."""
    match = _HTML_LEVEL_RE.search(text)
    if not match:
        return None
    word = match.group(1)
    return _ARABIC_ORDINALS.get(word) or int(word)


def _level_in_first_row(rows: list[list[list[str]]]) -> int | None:
    """The level number a table names in its own first row, if any.

    The IS plan puts "المستوى الأول" in the table as a caption row, while the CE
    plan puts it in a heading above the table; both are read here.
    """
    if not rows:
        return None
    return _level_in_text(" ".join(_cell_text(cell) for cell in rows[0]))


def _parse_html_level(rows: list[list[list[str]]], level_no: int) -> dict:
    """Read one level table: code | title | credit hours | prerequisites."""
    courses: list[dict] = []
    total: int | None = None
    blank_rows = 0

    for row in rows:
        cells = [_cell_text(cell) for cell in row]
        if not cells or not any(cells):
            blank_rows += 1
            continue
        if _level_in_text(" ".join(cells)) is not None:
            # The level heading is a caption row inside the table.
            continue
        if _HEADER_CELL_RE.match(cells[0]):
            continue
        if _HTML_TOTAL_RE.match(cells[0]):
            total = _first_int(cells[1:])
            continue

        code_cell = cells[0]
        codes = _html_codes(code_cell)
        choice = len(codes) > 1
        elective = choice or bool(_HTML_PLACEHOLDER_RE.match(code_cell))
        if not elective and not codes:
            raise PlanError(
                f"level {level_no}: course row {code_cell!r} has no course code "
                f"({' | '.join(cells)})"
            )
        if len(cells) < 3:
            raise PlanError(
                f"level {level_no}: course row {code_cell!r} has no credit hours "
                f"({' | '.join(cells)})"
            )
        match = _HTML_CREDITS_RE.match(cells[2])
        if not match:
            raise PlanError(
                f"level {level_no}: course row {code_cell!r} has no parseable "
                f"credit hours ({cells[2]!r})"
            )

        course = {
            "code": None if elective else codes[0],
            "title": cells[1],
            "credits": int(match.group(1)),
            "prerequisites": _html_codes(cells[3] if len(cells) > 3 else ""),
        }
        if elective:
            course["elective"] = True
        if choice:
            course["options"] = codes
        courses.append(course)

    if not courses:
        raise PlanError(f"level {level_no} has no course rows")

    parsed_sum = sum(course["credits"] for course in courses)
    if total is not None and parsed_sum != total:
        missing = f", and the table has {blank_rows} empty row(s)" if blank_rows else ""
        raise PlanError(
            f"level {level_no}: the courses add up to {parsed_sum} CH "
            f"but the table says {total} CH{missing}"
        )

    level = {"level": level_no, "courses": courses}
    if total is not None:
        level["total_credits"] = total
    return level


def parse_html_body(html: str) -> list[dict]:
    """Parse the HTML in a JSON:API body into a list of levels.

    A level table is the <table> that follows a "المستوى <ordinal>" heading, or
    that names its level in a caption row of its own. Any other table — the
    elective pools, the course-description lists — is not a level and is skipped
    with a note, so it cannot become a level whose rows look wrong.
    """
    parser = _PlanHTMLParser()
    parser.feed(html)
    parser.close()
    parser._flush()

    levels: list[dict] = []
    seen: set[int] = set()
    heading: int | None = None
    skipped: list[str] = []

    for kind, payload in parser.events:
        if kind == "text":
            heading = _level_in_text(str(payload))
            continue

        rows = payload
        table_level = heading if heading is not None else _level_in_first_row(rows)
        heading = None
        if table_level is None:
            skipped.append(f"a table of {len(rows)} row(s) with no level heading")
            continue
        if table_level in seen:
            raise PlanError(f"the source carries level {table_level} twice")
        seen.add(table_level)
        levels.append(_parse_html_level(rows, table_level))

    if not levels:
        raise PlanError("no level tables found; the source does not carry a study plan")
    if skipped:
        print(
            f"note: skipped {len(skipped)} non-level table(s): "
            f"{'; '.join(skipped)}",
            file=sys.stderr,
        )
    return sorted(levels, key=lambda level: level["level"])


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------


def build_plan(source: PlanSource, meta: dict, levels: list[dict]) -> dict:
    """Assemble the plan document, sorted by level number."""
    plan = {
        "program": source.id,
        "title": source.title,
        "source_url": source.source_url,
        "program_url": source.program_url,
        "language": source.language,
        "retrieved_at": meta.get("downloaded_at") or _utc_now(),
        "source_sha256": meta["sha256"],
        "levels": sorted(levels, key=lambda level: level["level"]),
    }
    if source.stale_risk:
        plan["stale_risk"] = True
    return plan


def parse(
    source: PlanSource,
    *,
    raw_dir: Path,
    out_dir: Path,
) -> dict:
    """Parse one downloaded plan source and write its JSON table.

    The file on disk is hashed again before parsing: if it no longer matches the
    hash in its meta file, the plan's provenance would be wrong, so parsing stops.
    """
    raw_dir = Path(raw_dir)
    path = raw_dir / source.filename
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found; run fetch_plans.py --plan {source.id}"
        )

    meta = read_meta(raw_dir / source.meta_filename)
    if not meta or not meta.get("sha256"):
        raise PlanError(
            f"{raw_dir / source.meta_filename} is missing or unreadable; "
            f"run fetch_plans.py --plan {source.id}"
        )

    actual_sha256 = sha256_file(path)
    if actual_sha256 != meta["sha256"]:
        raise ValueError(
            f"hash mismatch for {path}: meta file has {meta['sha256']}, "
            f"file has {actual_sha256}; re-run fetch_plans.py --plan {source.id}"
        )

    if source.form == "pdf":
        levels = parse_pdf_pages(extract_pages(path))
    else:
        levels = parse_html_body(parse_jsonapi_body(path.read_text(encoding="utf-8")))

    plan = build_plan(source, meta, levels)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{source.id}.json"
    tmp_path = out_path.with_name(f"{out_path.name}.part")
    tmp_path.write_text(
        json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.replace(tmp_path, out_path)
    return plan


def _report(source: PlanSource, plan: dict, out_path: Path) -> None:
    courses = [course for level in plan["levels"] for course in level["courses"]]
    credits = sum(course["credits"] for course in courses)
    numbers = ", ".join(str(level["level"]) for level in plan["levels"])
    print(
        f"parsed {source.id}: {len(plan['levels'])} level(s) [{numbers}], "
        f"{len(courses)} course(s), {credits} CH"
    )
    if plan.get("stale_risk"):
        print("  stale_risk: not checked against the plan in force")
    print(f"  {out_path} ({out_path.stat().st_size} bytes)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Parse one downloaded study plan source into a JSON table of levels."
    )
    parser.add_argument(
        "--plan",
        action="append",
        metavar="ID",
        help="only parse this plan (repeatable); default: every plan in the list",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"plans list file (default: {DEFAULT_CONFIG})",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=DEFAULT_RAW_DIR,
        help=f"directory holding the downloaded sources (default: {DEFAULT_RAW_DIR})",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"output directory (default: {DEFAULT_OUT_DIR})",
    )
    args = parser.parse_args(argv)

    # A course title and an error row can be Arabic: do not let a redirected
    # stdout on Windows turn that into a UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    try:
        sources = load_plans(args.config)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.plan:
        known = {source.id for source in sources}
        unknown = sorted(set(args.plan) - known)
        if unknown:
            print(
                f"error: unknown plan id(s) {', '.join(unknown)}; "
                f"known: {', '.join(sorted(known))}",
                file=sys.stderr,
            )
            return 2
        wanted = set(args.plan)
        sources = [source for source in sources if source.id in wanted]

    failed = 0
    for source in sources:
        try:
            plan = parse(source, raw_dir=args.raw_dir, out_dir=args.out_dir)
        except (OSError, ValueError) as exc:
            failed += 1
            print(f"error: {source.id}: {exc}", file=sys.stderr)
            continue
        _report(source, plan, Path(args.out_dir) / f"{source.id}.json")

    if failed:
        print(f"error: {failed} of {len(sources)} plan(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
