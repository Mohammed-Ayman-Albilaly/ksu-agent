#!/usr/bin/env python3
"""Load a study plan table and answer level, course and prerequisite questions.

A plan is the JSON table parse_plan.py writes under data/processed/plans
(git-ignored), one file per program:

    { "program": "swe", "title": "...", "source_url": "...", "program_url": "...",
      "language": "en", "retrieved_at": "...", "source_sha256": "...",
      "levels": [ { "level": 1, "total_credits": 16, "courses": [ { "code": ...,
                    "title": ..., "credits": 3, "prerequisites": [] } ] } ] }

The table is the only source of an answer built on it: no level, course or
prerequisite is ever inferred from the model. A table whose levels are empty or
whose source_url is missing is refused, because a row from it could not be cited.

Usage:
    python backend/scripts/plans.py --program swe --level 1
    python backend/scripts/plans.py --program swe --course "MATH 101"
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLANS_DIR = REPO_ROOT / "data" / "processed" / "plans"


class PlanError(ValueError):
    """A plan table that is absent, unreadable, or not fit to answer from."""


@dataclass(frozen=True)
class Course:
    """One course row of a plan."""

    code: str | None
    title: str
    credits: int
    prerequisites: tuple[str, ...]
    elective: bool = False
    # The courses a row offers when it names a choice ("take one of these").
    options: tuple[str, ...] = ()

    def describe(self) -> str:
        label = self.code if self.code else "elective"
        return f"{label}  {self.title}  {self.credits} CH"


@dataclass(frozen=True)
class Level:
    """One level of a plan: its number, its courses and the stated total."""

    level: int
    courses: tuple[Course, ...]
    total_credits: int | None = None

    @property
    def credits(self) -> int:
        return sum(course.credits for course in self.courses)


@dataclass(frozen=True)
class Plan:
    """One program's study plan, as parsed from its source."""

    program: str
    title: str
    source_url: str
    program_url: str
    language: str
    retrieved_at: str
    source_sha256: str
    levels: tuple[Level, ...]
    stale_risk: bool = False

    @property
    def courses(self) -> tuple[Course, ...]:
        return tuple(course for level in self.levels for course in level.courses)


def plan_key(code: str) -> str:
    """The comparison key for a course code: no case, one space between parts."""
    return " ".join(str(code).split()).upper()


def _course_from_json(data: object) -> Course:
    if not isinstance(data, dict):
        raise PlanError(f"a course row is not an object: {data!r}")
    try:
        return Course(
            code=data["code"],
            title=str(data["title"]),
            credits=int(data["credits"]),
            prerequisites=tuple(str(code) for code in data.get("prerequisites", [])),
            elective=bool(data.get("elective", False)),
            options=tuple(str(code) for code in data.get("options", [])),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise PlanError(f"a course row is malformed: {exc}") from exc


def _level_from_json(data: object) -> Level:
    if not isinstance(data, dict):
        raise PlanError(f"a level is not an object: {data!r}")

    courses = tuple(_course_from_json(row) for row in data.get("courses") or [])
    try:
        number = int(data["level"])
    except (KeyError, TypeError, ValueError) as exc:
        raise PlanError(f"a level has no number: {exc}") from exc
    if not courses:
        raise PlanError(f"level {number} has no courses")

    total = data.get("total_credits")
    return Level(
        level=number,
        courses=courses,
        total_credits=int(total) if total is not None else None,
    )


def load(program_id: str, plans_dir: Path = DEFAULT_PLANS_DIR) -> Plan:
    """Load one program's plan table.

    Raises FileNotFoundError when the table has not been parsed yet, and
    PlanError when it cannot be cited or carries no levels.
    """
    path = Path(plans_dir) / f"{program_id}.json"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found; run parse_plan.py --plan {program_id}"
        )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PlanError(f"{path} is not readable JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PlanError(f"{path} does not hold a plan object")

    if not str(data.get("source_url") or "").strip():
        raise PlanError(f"{path} has no source_url, so a row from it cannot be cited")

    raw_levels = data.get("levels")
    if not isinstance(raw_levels, list) or not raw_levels:
        raise PlanError(f"{path} has no levels")

    levels = tuple(_level_from_json(level) for level in raw_levels)
    return Plan(
        program=str(data.get("program") or program_id),
        title=str(data.get("title") or ""),
        source_url=str(data["source_url"]),
        program_url=str(data.get("program_url") or ""),
        language=str(data.get("language") or ""),
        retrieved_at=str(data.get("retrieved_at") or ""),
        source_sha256=str(data.get("source_sha256") or ""),
        levels=levels,
        stale_risk=bool(data.get("stale_risk", False)),
    )


def level(plan: Plan, number: int) -> Level:
    """The level with this number, e.g. level(plan, 5)."""
    for candidate in plan.levels:
        if candidate.level == int(number):
            return candidate
    known = ", ".join(str(candidate.level) for candidate in plan.levels)
    raise PlanError(f"{plan.program} has no level {number}; the plan has {known}")


def course(plan: Plan, code: str) -> Course:
    """The course with this code, compared without case or extra spaces."""
    wanted = plan_key(code)
    for candidate in plan.courses:
        if candidate.code is not None and plan_key(candidate.code) == wanted:
            return candidate
    raise PlanError(f"{plan.program} has no course {code!r}")


def prerequisites(plan: Plan, code: str) -> list[str]:
    """The course codes this course requires; [] when it requires none."""
    return list(course(plan, code).prerequisites)


def _describe_plan(plan: Plan) -> str:
    lines = [f"{plan.program} — {plan.title}"]
    lines.append(f"source: {plan.source_url}")
    if plan.program_url and plan.program_url != plan.source_url:
        lines.append(f"page: {plan.program_url}")
    if plan.stale_risk:
        lines.append(
            "warning: this plan has not been checked against the plan in force"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read a parsed study plan: one level's courses, or one course "
        "and its prerequisites."
    )
    parser.add_argument("--program", required=True, help="program id, e.g. swe")
    parser.add_argument("--level", type=int, help="print this level's courses")
    parser.add_argument("--course", help='print this course, e.g. "MATH 101"')
    parser.add_argument(
        "--plans-dir",
        type=Path,
        default=DEFAULT_PLANS_DIR,
        help=f"directory holding the parsed plans (default: {DEFAULT_PLANS_DIR})",
    )
    args = parser.parse_args(argv)

    # A course title and a citation can be Arabic: do not let a redirected stdout
    # on Windows turn that into a UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    if (args.level is None) == (args.course is None):
        print("error: give exactly one of --level or --course", file=sys.stderr)
        return 2

    try:
        plan = load(args.program, args.plans_dir)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        if args.level is not None:
            found = level(plan, args.level)
            total = (
                f"{found.total_credits} CH"
                if found.total_credits is not None
                else f"{found.credits} CH"
            )
            answer = [
                f"level {found.level}: {len(found.courses)} courses, {total}",
                *(f"  {row.describe()}" for row in found.courses),
            ]
        else:
            found_course = course(plan, args.course)
            where = next(
                candidate.level
                for candidate in plan.levels
                if found_course in candidate.courses
            )
            required = prerequisites(plan, args.course)
            answer = [
                f"level {where}: {found_course.describe()}",
                f"  prerequisites: {', '.join(required) if required else 'none'}",
            ]
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(_describe_plan(plan))
    print("\n".join(answer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
