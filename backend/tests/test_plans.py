"""Tests for the study plan pipeline: scripts/parse_plan.py and scripts/plans.py.

No network and no downloaded document: the fixtures are written to tmp_path, either
as the text pymupdf extracts from a plan PDF (one table cell per line) or as a
JSON:API-shaped payload holding the HTML tables the CE and IS pages publish.
"""

import json

import pytest

import parse_plan
import plans
from fetch_plans import PlanSource, load_plans

# One page of the SWE plan, as pymupdf extracts it: the page number, the "YEAR"
# line, the level heading, the column headings, then one cell per line.
SWE_PAGE = """\
1
YEAR 1
LEVEL (SEMESTER) 1
Course
Code
Course Title
Credit
Hours
Pre-
requisites
ENGL 100
English Language
6
MATH 101
Differential Calculus
3
CHEM1
101
General Chemistry
(1)
4
ARAB 100
Writing Skills
2
ENT 101
Entrepreneurship
1
Total
16 CH
LEVEL (SEMESTER) 2
ENGL 110
English
6
ENGS 100
Total
6 CH
"""

# "Total 6 CH" is a summary line, not a course, and the "--" row is an elective
# whose 2 CH still count towards the level's total.
SWE_ELECTIVE_PAGE = """\
LEVEL (SEMESTER) 1
CSC 111
Computer Programming I
4
CT 101
--
General Education
2
Total
6 CH
"""

# Two Arabic level tables: the first names its level in a caption row inside the
# table, the second in a heading above it. The third table is an elective pool,
# which is not a level. The digits are Arabic-Indic and in logical order, so ١٤٠ is
# 140 and must not be reversed into 041.
ARABIC_BODY = """\
<h2>الخطة الدراسية</h2>
<table align="center">
\t<thead>
\t\t<tr><td colspan="4">المستوى الأول</td></tr>
\t\t<tr><td>الرمز</td><td>اسم المقرر</td><td>الساعات</td><td>المتطلبات</td></tr>
\t</thead>
\t<tbody>
\t\t<tr><td>١٤٠ريض</td><td>مدخل إلى الرياضيات ١</td><td>٢</td><td>&nbsp;</td></tr>
\t\t<tr><td>١١١عال</td><td>برمجة الحاسبات ١</td><td>٤</td><td>١٤٠ريض</td></tr>
\t</tbody>
\t<tfoot>
\t\t<tr><td>المجموع</td><td>&nbsp;</td><td>٦</td><td>&nbsp;</td></tr>
\t</tfoot>
</table>
<h2>المستوى الثاني</h2>
<table align="center">
\t<thead>
\t\t<tr><td>الرمز</td><td>اسم المقرر</td><td>الساعات</td><td>المتطلبات</td></tr>
\t</thead>
\t<tbody>
\t\t<tr><td>ريض 101</td><td>حساب التفاضل</td><td>3(0,1,3)</td><td>—</td></tr>
\t</tbody>
\t<tfoot>
\t\t<tr><td>المجموع</td><td>&nbsp;</td><td>٣</td><td>&nbsp;</td></tr>
\t</tfoot>
</table>
<table align="center">
\t<thead>
\t\t<tr><td>الرمز</td><td>اسم المقرر</td></tr>
\t</thead>
\t<tbody>
\t\t<tr><td>كهر 203</td><td>الكهرومغناطيسية الهندسية</td></tr>
\t</tbody>
</table>
"""

PLAN_JSON = {
    "program": "swe",
    "title": "Software Engineering (SWE) — BSc study plan, 2023",
    "source_url": "https://example.test/swe.pdf",
    "program_url": "https://example.test/ar/se/se-bsc-program",
    "language": "en",
    "retrieved_at": "2026-01-01T00:00:00Z",
    "source_sha256": "0" * 64,
    "levels": [
        {
            "level": 1,
            "total_credits": 6,
            "courses": [
                {
                    "code": "MATH 101",
                    "title": "Differential Calculus",
                    "credits": 3,
                    "prerequisites": [],
                },
                {
                    "code": "ENGL 100",
                    "title": "English Language",
                    "credits": 3,
                    "prerequisites": [],
                },
            ],
        },
        {
            "level": 2,
            "total_credits": 3,
            "courses": [
                {
                    "code": "MATH 106",
                    "title": "Integral Calculus",
                    "credits": 3,
                    "prerequisites": ["MATH 101"],
                }
            ],
        },
    ],
}


def _payload(body):
    """A JSON:API node page whose body holds the given HTML."""
    return json.dumps(
        {
            "jsonapi": {"version": "1.0"},
            "data": {
                "type": "node--page",
                "id": "5c9f148e-2721-4512-9702-fcf63fe9f08c",
                "attributes": {"body": {"value": body, "format": "full_html"}},
            },
        }
    )


def _write_plan(directory, plan, name="swe.json"):
    path = directory / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# The PDF parser
# --------------------------------------------------------------------------


def test_pdf_text_parses_levels_and_courses():
    levels = parse_plan.parse_pdf_pages([SWE_PAGE])

    assert [level["level"] for level in levels] == [1, 2]
    assert levels[0]["total_credits"] == 16
    assert [course["code"] for course in levels[0]["courses"]] == [
        "ENGL 100",
        "MATH 101",
        "CHEM1 101",
        "ARAB 100",
        "ENT 101",
    ]
    assert [course["credits"] for course in levels[0]["courses"]] == [6, 3, 4, 2, 1]
    assert levels[0]["courses"][0]["title"] == "English Language"
    assert levels[0]["courses"][0]["prerequisites"] == []
    assert levels[1]["courses"][0]["prerequisites"] == ["ENGS 100"]


def test_pdf_prerequisite_is_not_read_as_a_course_row():
    # "ENGS 100" is the prerequisite of ENGL 110, not a row: it is followed by
    # the level's total, not by credit hours.
    levels = parse_plan.parse_pdf_pages([SWE_PAGE])

    codes = [course["code"] for course in levels[1]["courses"]]
    assert codes == ["ENGL 110"]


def test_pdf_total_line_is_skipped_and_elective_row_kept():
    levels = parse_plan.parse_pdf_pages([SWE_ELECTIVE_PAGE])

    assert levels[0]["total_credits"] == 6
    assert "Total" not in [course["title"] for course in levels[0]["courses"]]

    elective = levels[0]["courses"][1]
    assert elective["code"] is None
    assert elective["elective"] is True
    assert elective["title"] == "General Education"
    assert elective["credits"] == 2


def test_pdf_total_mismatch_is_rejected_naming_the_level():
    page = """\
LEVEL (SEMESTER) 3
CSC 111
Computer Programming I
4
Total
16 CH
"""

    with pytest.raises(parse_plan.PlanError) as excinfo:
        parse_plan.parse_pdf_pages([page])

    message = str(excinfo.value)
    assert "level 3" in message
    assert "16" in message


def test_pdf_row_without_credit_hours_is_rejected_naming_the_level():
    # MATH 101 has no credit hours, so its row is read as part of ENGL 100's.
    page = """\
LEVEL (SEMESTER) 1
ENGL 100
English Language
6
MATH 101
Differential Calculus
Total
6 CH
"""

    with pytest.raises(parse_plan.PlanError) as excinfo:
        parse_plan.parse_pdf_pages([page])

    message = str(excinfo.value)
    assert "level 1" in message
    assert "ENGL 100" in message


def test_pdf_page_without_text_is_rejected_naming_the_page():
    with pytest.raises(parse_plan.PlanError) as excinfo:
        parse_plan.parse_pdf_pages(["", SWE_PAGE])

    assert "page 1" in str(excinfo.value)


def test_pdf_without_levels_is_rejected():
    with pytest.raises(parse_plan.PlanError, match="no levels"):
        parse_plan.parse_pdf_pages(["Just a cover page\nwith no table"])


def test_pdf_heading_that_names_two_levels_is_rejected():
    # A guide can cover levels 1 and 2 with one table; its rows cannot be
    # attributed to one of them, so the table is refused rather than guessed at.
    page = """\
First Common Year (Levels 1–2)
MATH 101
Differential Calculus
3
"""

    with pytest.raises(parse_plan.PlanError, match="more than one level"):
        parse_plan.parse_pdf_pages([page])


# --------------------------------------------------------------------------
# The HTML table parser
# --------------------------------------------------------------------------


def test_html_tables_parse_arabic_levels_and_courses():
    levels = parse_plan.parse_html_body(parse_plan.parse_jsonapi_body(_payload(ARABIC_BODY)))

    assert [level["level"] for level in levels] == [1, 2]
    assert levels[0]["total_credits"] == 6
    assert [course["code"] for course in levels[0]["courses"]] == ["140ريض", "111عال"]
    assert [course["credits"] for course in levels[0]["courses"]] == [2, 4]
    assert levels[0]["courses"][0]["title"] == "مدخل إلى الرياضيات 1"
    assert levels[0]["courses"][1]["prerequisites"] == ["140ريض"]

    assert levels[1]["courses"][0]["code"] == "ريض 101"
    assert levels[1]["courses"][0]["credits"] == 3
    assert levels[1]["courses"][0]["prerequisites"] == []


def test_html_arabic_indic_digits_are_mapped_not_reversed():
    # The HTML is in logical order, so reversing the run would give 041, not 140.
    assert parse_plan.normalise_digits("١٤٠ريض") == "140ريض"
    assert parse_plan.normalise_digits("٢٤٤١") == "2441"


def test_html_non_level_table_is_skipped_with_a_note(capsys):
    parse_plan.parse_html_body(parse_plan.parse_jsonapi_body(_payload(ARABIC_BODY)))

    assert "skipped 1 non-level table" in capsys.readouterr().err


def test_html_row_without_credit_hours_is_rejected_naming_the_level():
    body = """\
<h2>المستوى الأول</h2>
<table>
\t<tr><td>الرمز</td><td>اسم المقرر</td><td>الساعات</td><td>المتطلبات</td></tr>
\t<tr><td>ريض 101</td><td>حساب التفاضل</td><td>—</td><td>—</td></tr>
</table>
"""

    with pytest.raises(parse_plan.PlanError) as excinfo:
        parse_plan.parse_html_body(parse_plan.parse_jsonapi_body(_payload(body)))

    message = str(excinfo.value)
    assert "level 1" in message
    assert "ريض 101" in message


def test_html_total_mismatch_is_rejected_naming_the_level():
    body = """\
<h2>المستوى الثاني</h2>
<table>
\t<tr><td>الرمز</td><td>اسم المقرر</td><td>الساعات</td><td>المتطلبات</td></tr>
\t<tr><td>ريض 101</td><td>حساب التفاضل</td><td>3</td><td>—</td></tr>
\t<tr><td>المجموع</td><td>&nbsp;</td><td>6</td><td>&nbsp;</td></tr>
</table>
"""

    with pytest.raises(parse_plan.PlanError) as excinfo:
        parse_plan.parse_html_body(parse_plan.parse_jsonapi_body(_payload(body)))

    assert "level 2" in str(excinfo.value)


def test_html_payload_without_body_value_is_rejected():
    with pytest.raises(parse_plan.PlanError, match="body"):
        parse_plan.parse_jsonapi_body(json.dumps({"data": {"attributes": {}}}))


# --------------------------------------------------------------------------
# The driver
# --------------------------------------------------------------------------


def _source():
    return PlanSource(
        id="ce",
        title="هندسة الحاسب (CE) — خطة البرنامج",
        program_url="https://example.test/ar/ce/new-bsc-program",
        source_url="https://example.test/ar/jsonapi/node/page/abc",
        form="html_table",
        language="ar",
        stale_risk=True,
    )


def test_parse_writes_a_plan_file(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    payload = _payload(ARABIC_BODY).encode("utf-8")
    (raw_dir / "ce.json").write_bytes(payload)
    (raw_dir / "ce.meta.json").write_text(
        json.dumps(
            {
                "plan_id": "ce",
                "source_url": _source().source_url,
                "downloaded_at": "2026-01-01T00:00:00Z",
                "sha256": parse_plan.sha256_file(raw_dir / "ce.json"),
            }
        ),
        encoding="utf-8",
    )

    plan = parse_plan.parse(_source(), raw_dir=raw_dir, out_dir=tmp_path / "processed")

    written = json.loads(
        (tmp_path / "processed" / "ce.json").read_text(encoding="utf-8")
    )
    assert written == plan
    assert plan["program"] == "ce"
    assert plan["language"] == "ar"
    assert plan["stale_risk"] is True
    assert plan["retrieved_at"] == "2026-01-01T00:00:00Z"
    assert len(plan["levels"]) == 2


def test_parse_refuses_a_file_that_no_longer_matches_its_meta(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "ce.json").write_text(_payload(ARABIC_BODY), encoding="utf-8")
    (raw_dir / "ce.meta.json").write_text(
        json.dumps({"sha256": "0" * 64}), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="hash"):
        parse_plan.parse(_source(), raw_dir=raw_dir, out_dir=tmp_path / "processed")


# --------------------------------------------------------------------------
# The loader
# --------------------------------------------------------------------------


def test_load_reads_a_plan(tmp_path):
    _write_plan(tmp_path, PLAN_JSON)

    plan = plans.load("swe", plans_dir=tmp_path)

    assert plan.program == "swe"
    assert plan.source_url == "https://example.test/swe.pdf"
    assert [level.level for level in plan.levels] == [1, 2]


def test_load_refuses_a_plan_with_no_levels(tmp_path):
    _write_plan(tmp_path, {**PLAN_JSON, "levels": []})

    with pytest.raises(plans.PlanError, match="no levels"):
        plans.load("swe", plans_dir=tmp_path)


def test_load_refuses_a_plan_with_no_source_url(tmp_path):
    _write_plan(tmp_path, {**PLAN_JSON, "source_url": ""})

    with pytest.raises(plans.PlanError, match="source_url"):
        plans.load("swe", plans_dir=tmp_path)


def test_load_refuses_an_absent_plan(tmp_path):
    with pytest.raises(FileNotFoundError):
        plans.load("swe", plans_dir=tmp_path)


def test_level_returns_the_levels_courses(tmp_path):
    _write_plan(tmp_path, PLAN_JSON)
    plan = plans.load("swe", plans_dir=tmp_path)

    assert [course.code for course in plans.level(plan, 2).courses] == ["MATH 106"]

    with pytest.raises(plans.PlanError, match="level 9"):
        plans.level(plan, 9)


def test_course_matches_case_insensitively(tmp_path):
    _write_plan(tmp_path, PLAN_JSON)
    plan = plans.load("swe", plans_dir=tmp_path)

    assert plans.course(plan, "math  101").code == "MATH 101"
    assert plans.course(plan, "Math 101").code == "MATH 101"

    with pytest.raises(plans.PlanError, match="no course"):
        plans.course(plan, "MATH 999")


def test_prerequisites_is_empty_for_a_first_level_course(tmp_path):
    _write_plan(tmp_path, PLAN_JSON)
    plan = plans.load("swe", plans_dir=tmp_path)

    assert plans.prerequisites(plan, "MATH 101") == []
    assert plans.prerequisites(plan, "MATH 106") == ["MATH 101"]


# --------------------------------------------------------------------------
# The plans list
# --------------------------------------------------------------------------


def test_plans_list_is_read_and_validated(tmp_path):
    config = tmp_path / "plans.toml"
    config.write_text(
        "[[plan]]\n"
        'id = "swe"\n'
        'title = "Software Engineering"\n'
        'program_url = "https://example.test/se"\n'
        'source_url = "https://example.test/swe.pdf"\n'
        'form = "pdf"\n'
        'language = "en"\n'
        "\n"
        "[[plan]]\n"
        'id = "ce"\n'
        'title = "Computer Engineering"\n'
        'program_url = "https://example.test/ce"\n'
        'source_url = "https://example.test/ce.json"\n'
        'form = "html_table"\n'
        'language = "ar"\n'
        "stale_risk = true\n",
        encoding="utf-8",
    )

    sources = load_plans(config)

    assert [source.id for source in sources] == ["swe", "ce"]
    assert sources[0].filename == "swe.pdf"
    assert sources[1].filename == "ce.json"
    assert sources[1].stale_risk is True
    assert sources[0].stale_risk is False


def test_plans_list_rejects_an_unknown_form(tmp_path):
    config = tmp_path / "plans.toml"
    config.write_text(
        "[[plan]]\n"
        'id = "swe"\n'
        'title = "Software Engineering"\n'
        'program_url = "https://example.test/se"\n'
        'source_url = "https://example.test/swe.pdf"\n'
        'form = "docx"\n'
        'language = "en"\n',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="form"):
        load_plans(config)
