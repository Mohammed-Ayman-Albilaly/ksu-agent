#!/usr/bin/env python3
"""Measure the router on both question sets: the regex first, the classifier on a miss.

`eval/phase2_router.json` is the set the regex patterns were written against, so the
regex alone scores 101/101 on it and that number says nothing about a question it has
never seen. `eval/phase2_router_heldout.json` is the check: 33 questions written apart
from the patterns, of which the regex recognises 22. The other 11 reach the fallback
classifier in `backend/app/intent.py`.

For every question this run records the route the endpoint would take — the regex's
answer, or the classifier's when the regex returns None — next to the routes the set
accepts. Both sets are reported on their own, because averaging a set the patterns were
written against with a set they were not would hide the overfitting.

A question the set treats as genuinely ambiguous carries `accept`, the routes a student could
reasonably mean, in place of a single `expected` route, and `ambiguous_reason` saying why. It
is counted as correct when the route it took is one of them.

The run ends with the accuracy per set and per route, every miss, and two safety lines. A
regulation question sent to a reasoning route is a hard failure: it would send the student's data
after consent, for a question the regulation answers. A regulation question sent to a tool route is
reported, because the read happens in the browser and sends nothing, and it fails only when the item
does not accept that tool. The targets are 95% on each set, no regulation question on a reasoning
route, and no tool read an item does not accept; the exit status is 1 when a target is missed.

`--repeat N` routes every question N times, because the classifier is not fully deterministic. An
item is correct when every run's route is one the set accepts: a question that moved between two
accepted routes is printed as VARIES (accepted) and does not fail, while a move that reaches a route
the set does not accept is UNSTABLE and fails the run.

This calls the real chat model, so it needs LLM_API_KEY and it is not part of pytest.

Usage:
    python eval/run_router_eval.py [--set PATH ...] [--repeat N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = Path(__file__).resolve().parent
BACKEND_DIR = REPO_ROOT / "backend"
SCRIPTS_DIR = BACKEND_DIR / "scripts"

for directory in (EVAL_DIR, SCRIPTS_DIR, BACKEND_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import answer  # noqa: E402  (needs backend/scripts on sys.path)
from app import intent  # noqa: E402
from app.tools import detect_personal_request  # noqa: E402

DEFAULT_SETS = (
    EVAL_DIR / "phase2_router.json",
    EVAL_DIR / "phase2_router_heldout.json",
)

REGULATION = intent.REGULATION
TARGET_ACCURACY = 0.95


@dataclass(frozen=True)
class Row:
    """One question's accepted routes, the routes it took, and which router chose them."""

    id: str
    question: str
    accepted: tuple[str, ...]
    runs: tuple[str, ...]
    sources: tuple[str, ...]
    latency_ms: float

    @property
    def route(self) -> str:
        """The route of the first run: the answer when every run agrees."""
        return self.runs[0]

    @property
    def source(self) -> str:
        """The router that chose, or "mixed" when two runs were routed by different ones."""
        return self.sources[0] if len(set(self.sources)) == 1 else "mixed"

    @property
    def varies(self) -> bool:
        """The same question took more than one route between the runs."""
        return len(set(self.runs)) > 1

    @property
    def unstable(self) -> bool:
        """The variation left the accepted set: the classifier cannot be relied on here.

        A question that moved between two routes the set accepts is `varies`, not `unstable`: the
        set says both answers are right, so which one a run picks is not a defect.
        """
        return self.varies and not self.ok

    @property
    def status(self) -> str:
        """The word printed for this item."""
        if self.unstable:
            return "UNSTABLE"
        if self.varies:
            return "VARIES (accepted)"
        return "ok" if self.ok else "MISS"

    @property
    def seen(self) -> str:
        """Every route taken when they differ, the one route otherwise."""
        return " / ".join(self.runs) if self.varies else self.route

    @property
    def ok(self) -> bool:
        """Correct when every run's route is one the set accepts, however many routes it takes."""
        return all(route in self.accepted for route in self.runs)

    @property
    def is_regulation_question(self) -> bool:
        """The set expects a rule answer: retrieval, and none of the student's pages."""
        return REGULATION in self.accepted

    @property
    def sent_to_a_reasoning_route(self) -> bool:
        """A rule question would send the student's data after consent: never acceptable."""
        return self.is_regulation_question and any(
            route.startswith(intent.REASON_PREFIX) for route in self.runs
        )

    @property
    def sent_to_a_tool_route(self) -> bool:
        """A rule question read the student's own pages: in the browser, nothing sent."""
        return self.is_regulation_question and any(
            route != REGULATION and not route.startswith(intent.REASON_PREFIX)
            for route in self.runs
        )

    @property
    def unaccepted_tool_routes(self) -> tuple[str, ...]:
        """Tool routes a rule question took that the item does not accept: real failures."""
        if not self.is_regulation_question:
            return ()

        return tuple(
            dict.fromkeys(
                route
                for route in self.runs
                if route != REGULATION
                and not route.startswith(intent.REASON_PREFIX)
                and route not in self.accepted
            )
        )

    @property
    def sent_to_an_unaccepted_tool_route(self) -> bool:
        return bool(self.unaccepted_tool_routes)


@dataclass(frozen=True)
class SetResult:
    """One set, routed end to end."""

    path: Path
    rows: tuple[Row, ...]

    @property
    def correct(self) -> int:
        return sum(row.ok for row in self.rows)

    @property
    def accuracy(self) -> float:
        return self.correct / len(self.rows) if self.rows else 0.0

    @property
    def by_source(self) -> dict[str, int]:
        counts = {"regex": 0, "classifier": 0}
        for row in self.rows:
            counts[row.source] = counts.get(row.source, 0) + 1
        return counts

    @property
    def varies(self) -> int:
        return sum(row.varies for row in self.rows)

    @property
    def unstable(self) -> int:
        return sum(row.unstable for row in self.rows)

    @property
    def regulation_sent_to_a_reasoning_route(self) -> int:
        return sum(row.sent_to_a_reasoning_route for row in self.rows)

    @property
    def regulation_sent_to_a_tool_route(self) -> int:
        return sum(row.sent_to_a_tool_route for row in self.rows)

    @property
    def regulation_sent_to_an_unaccepted_tool_route(self) -> int:
        return sum(row.sent_to_an_unaccepted_tool_route for row in self.rows)

    @property
    def meets_targets(self) -> bool:
        """Accuracy, no unstable item, no data sent for a rule question, no refused read."""
        return (
            self.accuracy >= TARGET_ACCURACY
            and self.unstable == 0
            and self.regulation_sent_to_a_reasoning_route == 0
            and self.regulation_sent_to_an_unaccepted_tool_route == 0
        )


def accepted_routes(item: dict) -> tuple[str, ...]:
    """Every route the set accepts, in the same vocabulary the classifier answers in.

    A question with one answer carries `expected`; a genuinely ambiguous one carries `accept`,
    the routes a student could reasonably mean, and `ambiguous_reason` saying why.
    """
    if "accept" in item:
        return tuple(item["accept"])

    expected = item["expected"]

    if expected["kind"] == "regulation":
        return (REGULATION,)
    if expected["kind"] == "reason":
        return (f"{intent.REASON_PREFIX}{expected['reasoning']}",)

    return (expected["tools"][0],)


def load_set(path: Path) -> list[dict]:
    """One set as shipped, with the fields the report reads checked before it is used."""
    items = json.loads(path.read_text(encoding="utf-8"))

    for item in items:
        missing = {"id", "question"} - set(item)
        if missing:
            raise ValueError(f"{path}: {item.get('id', '?')} is missing {sorted(missing)}")

        if "accept" in item:
            if "expected" in item:
                raise ValueError(f"{path}: {item['id']} has both expected and accept")
            if len(item["accept"]) < 2:
                raise ValueError(f"{path}: {item['id']} accepts one route: use expected")
            if not str(item.get("ambiguous_reason", "")).strip():
                raise ValueError(
                    f"{path}: {item['id']} accepts several routes without a reason"
                )
        elif "expected" not in item:
            raise ValueError(f"{path}: {item['id']} has neither expected nor accept")

    return items


def route(item: dict, *, client, config, repeat: int = 1) -> Row:
    """The routes `/chat` would take for one question over `repeat` runs."""
    question = item["question"]
    started = time.perf_counter()
    routes, sources = [], []

    # The regex is deterministic, so only a question it misses costs a model call per run.
    for _ in range(repeat):
        request = detect_personal_request(question)

        if request is not None:
            routes.append(intent.route_name(request, question))
            sources.append("regex")
        else:
            routes.append(intent.classify(question, client=client, config=config))
            sources.append("classifier")

    return Row(
        id=item["id"],
        question=question,
        accepted=accepted_routes(item),
        runs=tuple(routes),
        sources=tuple(sources),
        latency_ms=(time.perf_counter() - started) * 1000 / repeat,
    )


def run_set(path: Path, *, client, config, repeat: int = 1) -> SetResult:
    """Route a whole set, printing each question as it goes so a slow run is visible."""
    rows = []
    for item in load_set(path):
        row = route(item, client=client, config=config, repeat=repeat)
        rows.append(row)
        print(f"  {row.status:<17} {row.id}  -> {row.seen} ({row.source})")
    return SetResult(path=path, rows=tuple(rows))


def per_route(rows: tuple[Row, ...]) -> dict[str, tuple[int, int]]:
    """Correct and total per route, keyed by each item's first accepted route."""
    counts: dict[str, list[int]] = {}
    for row in rows:
        entry = counts.setdefault(row.accepted[0], [0, 0])
        entry[0] += row.ok
        entry[1] += 1
    return {route: (correct, total) for route, (correct, total) in counts.items()}


def report(result: SetResult) -> str:
    """The set's accuracy, the split between the two routers, and every miss."""
    sources = result.by_source
    mixed = f", mixed {sources['mixed']}" if sources.get("mixed") else ""
    lines = [
        f"{result.path.name}: {result.correct}/{len(result.rows)} "
        f"({result.accuracy:.1%})  —  regex {sources['regex']}, "
        f"classifier {sources['classifier']}{mixed}"
    ]

    lines.append("  per route:")
    lines += [
        f"    {route:<22} {correct}/{total}"
        for route, (correct, total) in per_route(result.rows).items()
    ]

    varying = [row for row in result.rows if row.varies]
    lines.append(f"  varies: {len(varying)}  (unstable: {result.unstable})")
    lines += [
        f"    {row.id}  ({row.question})  saw {row.seen} ({row.source})  {row.status}"
        for row in varying
    ]

    misses = [row for row in result.rows if not row.ok]
    lines.append(f"  misses: {len(misses)}")
    lines += [
        f"    {row.id}  ({row.question})  accepts {list(row.accepted)}, "
        f"got {row.seen} ({row.source})"
        for row in misses
    ]

    lines.append(
        "  regulation sent to a reasoning route: "
        f"{result.regulation_sent_to_a_reasoning_route}  (must be 0)"
    )
    lines.append(
        f"  regulation sent to a tool route: {result.regulation_sent_to_a_tool_route} "
        f"(unaccepted: {result.regulation_sent_to_an_unaccepted_tool_route})"
    )
    lines.append(
        f"  target {TARGET_ACCURACY:.0%}, no reasoning route, no unaccepted tool: "
        f"{'PASS' if result.meets_targets else 'FAIL'}"
    )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--set",
        dest="sets",
        type=Path,
        action="append",
        default=None,
        help="a router set to run; defaults to both, and may be given more than once",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=answer.DEFAULT_CONFIG,
        help="the chat config, for the model and the client's timeout",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        metavar="N",
        help="route every question N times; an item is correct when every run's route is "
        "accepted, a question that moved inside its accepted routes is printed as "
        "VARIES (accepted), and one that moved outside them as UNSTABLE",
    )
    args = parser.parse_args(argv)

    if args.repeat < 1:
        parser.error("--repeat must be at least 1")

    sets = tuple(args.sets) if args.sets else DEFAULT_SETS
    config = answer.load_config(args.config)
    client = answer.make_client(config)

    print(
        f"router eval — model {config.model}, {len(sets)} set(s), "
        f"{args.repeat} run(s) per item\n"
    )

    results = []
    for path in sets:
        result = run_set(path, client=client, config=config, repeat=args.repeat)
        results.append(result)
        print(f"\n{report(result)}\n")

    print("summary")
    for result in results:
        print(
            f"  {result.path.name:<32} {result.correct:>3}/{len(result.rows):<3} "
            f"{result.accuracy:>6.1%}   varies {result.varies}   unstable {result.unstable}   "
            f"regulation->reason {result.regulation_sent_to_a_reasoning_route}   "
            f"regulation->tool {result.regulation_sent_to_a_tool_route} "
            f"(unaccepted {result.regulation_sent_to_an_unaccepted_tool_route})   "
            f"{'PASS' if result.meets_targets else 'FAIL'}"
        )

    return 0 if all(result.meets_targets for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
