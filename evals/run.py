"""
Replay saved article fixtures through the brief generator and score the results.

    python -m evals.run --runs 3 --model claude-sonnet-4-6 --model claude-sonnet-5-5
"""

from __future__ import annotations

import argparse
import datetime
import glob
import json
import os
import pathlib
import statistics
import sys

import agent
from evals.checks import run_structural_checks
from evals.judge import DEFAULT_JUDGE_MODEL, judge_grounding

RESULTS_DIR = pathlib.Path(__file__).resolve().parent / "results"


def load_eval_portfolio(path: str) -> dict:
    """A single portfolio JSON file, or a directory of account files like ./portfolio."""
    if os.path.isdir(path):
        agent.PORTFOLIO_DIR = path
        portfolio = agent.load_portfolio_from_directory()
    else:
        with open(path) as f:
            portfolio = json.load(f)
    agent.validate_portfolio_allocations(portfolio)
    return portfolio


def run_one(fixture_name, articles, portfolio, model, run_idx, judge_model, out_dir) -> dict:
    record = {"fixture": fixture_name, "model": model, "run": run_idx}
    prompt = agent.build_prompt(articles, portfolio)
    try:
        response = agent.call_llm(prompt, model)
    except Exception as e:  # keep going so one bad call doesn't sink the run
        record["error"] = f"generation failed: {e}"
        return record

    brief = response.content[0].text
    brief_path = out_dir / f"{fixture_name}__{model}__run{run_idx}.md"
    brief_path.write_text(brief)
    record.update({
        "brief_path": str(brief_path.relative_to(out_dir)),
        "stop_reason": response.stop_reason,
        "usage": {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens},
        "checks": [c.to_dict() for c in run_structural_checks(brief, portfolio, articles, response.stop_reason)],
    })

    if judge_model:
        try:
            record["grounding"] = judge_grounding(brief, articles, portfolio, judge_model).to_dict()
        except Exception as e:
            record["error"] = f"judge failed: {e}"
    return record


def summarize(records: list[dict], judged: bool) -> str:
    lines = []
    for model in sorted({r["model"] for r in records}):
        rows = [r for r in records if r["model"] == model]
        ok = [r for r in rows if "checks" in r]
        lines.append(f"## {model}\n")
        lines.append(f"Runs: {len(rows)} ({len(rows) - len(ok)} failed to generate)\n")

        if ok:
            lines.append("| Check | Severity | Pass rate |")
            lines.append("|---|---|---|")
            for i, check in enumerate(ok[0]["checks"]):
                passed = sum(r["checks"][i]["passed"] for r in ok)
                lines.append(f"| {check['name']} | {check['severity']} | {passed}/{len(ok)} |")
            out_tokens = [r["usage"]["output_tokens"] for r in ok]
            lines.append(f"\nOutput tokens: mean {statistics.mean(out_tokens):.0f}, max {max(out_tokens)} "
                         f"(limit {agent.MAX_TOKENS})\n")

            failures = [(r, c) for r in ok for c in r["checks"] if not c["passed"]]
            if failures:
                lines.append("Check failures:")
                for r, c in failures:
                    lines.append(f"- {r['fixture']} run {r['run']} · {c['name']}: {c['detail']}")
                lines.append("")

        if judged:
            graded = [r for r in rows if r.get("grounding", {}).get("supported_rate") is not None]
            if graded:
                rates = [r["grounding"]["supported_rate"] for r in graded]
                lines.append(f"Grounding: mean supported {statistics.mean(rates):.0%}, "
                             f"min {min(rates):.0%}, max {max(rates):.0%} over {len(graded)} briefs\n")
                flagged = [(r, c) for r in graded for c in r["grounding"]["flagged"]]
                if flagged:
                    lines.append("Unsupported / contradicted claims:")
                    for r, c in flagged:
                        lines.append(f"- [{c['verdict']}] {r['fixture']} run {r['run']} §{c['section']}: "
                                     f"{c['claim']} — {c['explanation']}")
                    lines.append("")

        errors = [r for r in rows if "error" in r]
        if errors:
            lines.append("Errors:")
            lines += [f"- {r['fixture']} run {r['run']}: {r['error']}" for r in errors]
            lines.append("")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate daily briefs against saved article fixtures.")
    parser.add_argument("--fixtures", default="briefs/articles_*.json", help="glob of article fixture files")
    parser.add_argument("--model", action="append", help="model to evaluate (repeatable)")
    parser.add_argument("--runs", type=int, default=3, help="runs per fixture per model")
    parser.add_argument("--portfolio", default="portfolio/example.json", help="portfolio JSON file or directory")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE_MODEL)
    parser.add_argument("--no-judge", action="store_true", help="skip the LLM grounding judge")
    args = parser.parse_args(argv)

    fixtures = sorted(glob.glob(args.fixtures))
    if not fixtures:
        print(f"No fixtures match {args.fixtures}")
        return 2
    models = args.model or [agent.DEFAULT_MODEL]
    judge_model = None if args.no_judge else args.judge_model
    portfolio = load_eval_portfolio(args.portfolio)

    out_dir = RESULTS_DIR / datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True)

    records = []
    total = len(fixtures) * len(models) * args.runs
    for fixture in fixtures:
        with open(fixture) as f:
            articles = json.load(f)
        name = pathlib.Path(fixture).stem.removeprefix("articles_")
        for model in models:
            for run_idx in range(1, args.runs + 1):
                print(f"[{len(records) + 1}/{total}] {name} · {model} · run {run_idx}")
                records.append(run_one(name, articles, portfolio, model, run_idx, judge_model, out_dir))

    config = {
        "fixtures": fixtures, "models": models, "runs": args.runs, "portfolio": args.portfolio,
        "judge_model": judge_model, "system_prompt": agent.SYSTEM_PROMPT, "max_tokens": agent.MAX_TOKENS,
    }
    (out_dir / "results.json").write_text(json.dumps({"config": config, "records": records}, indent=2))
    summary = summarize(records, judged=judge_model is not None)
    (out_dir / "summary.md").write_text(f"# Brief eval · {out_dir.name}\n\n{summary}")

    print("\n" + summary)
    print(f"Results: {out_dir}")

    hard_fail = any("error" in r for r in records) or any(
        not c["passed"] and c["severity"] == "fail" for r in records for c in r.get("checks", [])
    )
    return 1 if hard_fail else 0


if __name__ == "__main__":
    sys.exit(main())
