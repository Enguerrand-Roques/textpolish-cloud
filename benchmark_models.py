#!/usr/bin/env python3
"""
benchmark_models.py — Compare multiple Ollama models on TextPolish cases.

Usage:
    python benchmark_models.py --models gemma3:4b llama3.2:3b
    python benchmark_models.py --models gemma3:4b --judge
    python benchmark_models.py --models gemma3:4b llama3.2:3b --judge --judge-model claude-haiku-4-5
"""

import argparse
import csv
import json
import os
import statistics
import time
from collections import defaultdict
from datetime import datetime

import requests

# Defaults — overridden by config.py if available
_OLLAMA_BASE_URL = "http://localhost:11434"
_OLLAMA_TIMEOUT = 120

try:
    from config import OLLAMA_BASE_URL as _OLLAMA_BASE_URL  # type: ignore
    from config import OLLAMA_TIMEOUT as _OLLAMA_TIMEOUT  # type: ignore
except ImportError:
    pass

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

_JUDGE_SYSTEM = """\
You are an expert text-quality evaluator. You will receive a text rewriting task: \
the original input, the rewritten output, and the rewriting mode (pro or casual).

Score the output on three criteria (integer 1–5, where 5 = perfect):
- correction: all spelling, grammar, punctuation errors are fixed
- tone: the tone matches the mode (pro → formal/professional, casual → relaxed/natural)
- preservation: the original meaning and intent are fully preserved

Also provide a one-sentence note (max 20 words) highlighting the main quality factor.

Reply ONLY with a JSON object, no markdown fences:
{"correction": <1-5>, "tone": <1-5>, "preservation": <1-5>, "note": "<sentence>"}
"""

_JUDGE_DEFAULT_MODEL = "claude-opus-4-6"


def _load_prompt(name: str) -> str:
    path = os.path.join(_PROMPTS_DIR, f"{name}.txt")
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _build_prompt(text: str, mode: str) -> str:
    system = _load_prompt(mode)
    return f"{system}\n\nTexte à réécrire :\n{text}"


def run_case(model: str, case: dict, base_url: str, timeout: int) -> dict:
    prompt_text = _build_prompt(case["input_text"], case["mode"])
    payload = {
        "model": model,
        "prompt": prompt_text,
        "keep_alive": 0,
        "stream": False,
    }

    t0 = time.perf_counter()
    error = None
    output = ""
    ollama_metrics: dict = {}

    try:
        resp = requests.post(
            f"{base_url}/api/generate",
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        output = data.get("response", "").strip()
        for key in ("total_duration", "load_duration", "prompt_eval_duration", "eval_duration"):
            if key in data:
                ollama_metrics[f"{key}_s"] = round(data[key] / 1e9, 3)
        for key in ("eval_count", "prompt_eval_count"):
            if key in data:
                ollama_metrics[key] = data[key]
    except Exception as exc:
        error = str(exc)

    wall_time = round(time.perf_counter() - t0, 3)

    return {
        "model": model,
        "case_id": case["id"],
        "label": case["label"],
        "mode": case["mode"],
        "input": case["input_text"],
        "output": output,
        "wall_time_s": wall_time,
        "metrics": ollama_metrics,
        "error": error,
        "judge": None,
    }


def judge_result(result: dict, judge_model: str) -> dict:
    """Call Claude to score a single rewriting result. Returns a scores dict or error."""
    try:
        import anthropic  # noqa: PLC0415
    except ImportError:
        return {"error": "anthropic package not installed — run: pip install anthropic"}

    client = anthropic.Anthropic()

    user_content = (
        f"Mode: {result['mode']}\n\n"
        f"Input:\n{result['input']}\n\n"
        f"Output:\n{result['output']}"
    )

    try:
        response = client.messages.create(
            model=judge_model,
            max_tokens=256,
            system=_JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = response.content[0].text.strip()
        # Strip markdown code fences if the model adds them despite instructions
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
            raw = raw.strip()
        scores = json.loads(raw)
        scores["overall"] = round(
            (scores["correction"] + scores["tone"] + scores["preservation"]) / 3, 2
        )
        return scores
    except Exception as exc:
        return {"error": str(exc)}


def _compute_stats(values: list) -> dict:
    if not values:
        return {}
    sorted_v = sorted(values)
    n = len(sorted_v)
    p95_idx = min(int(n * 0.95), n - 1)
    return {
        "count": n,
        "mean": round(statistics.mean(values), 3),
        "median": round(statistics.median(values), 3),
        "p95": round(sorted_v[p95_idx], 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
    }


def _write_json(results: list, path: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)


def _write_summary_csv(models: list, by_model: dict, scores_by_model: dict, path: str) -> None:
    has_scores = any(scores_by_model.values())
    fieldnames = ["model", "count", "mean", "median", "p95", "min", "max"]
    if has_scores:
        fieldnames += ["avg_correction", "avg_tone", "avg_preservation", "avg_overall"]

    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for model in models:
            stats = _compute_stats(by_model[model])
            if not stats:
                continue
            row: dict = {"model": model, **stats}
            if has_scores and scores_by_model[model]:
                sc = scores_by_model[model]
                for dim in ("correction", "tone", "preservation", "overall"):
                    vals = [s[dim] for s in sc if dim in s]
                    row[f"avg_{dim}"] = round(statistics.mean(vals), 2) if vals else ""
            writer.writerow(row)


def _write_markdown(
    models: list,
    cases: list,
    results: list,
    by_model: dict,
    scores_by_model: dict,
    timestamp: str,
    judge_model: str | None,
    path: str,
) -> None:
    has_scores = any(scores_by_model.values())

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Benchmark Results — {timestamp}\n\n")
        if judge_model:
            f.write(f"*Judge model: `{judge_model}`*\n\n")

        # --- Timing summary ---
        f.write("## Timing Summary (wall time, seconds)\n\n")
        f.write("| Model | Count | Mean | Median | P95 | Min | Max |\n")
        f.write("|-------|------:|-----:|-------:|----:|----:|----:|\n")
        for model in models:
            s = _compute_stats(by_model[model])
            if s:
                f.write(f"| `{model}` | {s['count']} | {s['mean']} | {s['median']} | {s['p95']} | {s['min']} | {s['max']} |\n")

        # --- Quality scores summary ---
        if has_scores:
            f.write("\n## Quality Scores (avg, 1–5)\n\n")
            f.write("| Model | Correction | Tone | Preservation | Overall |\n")
            f.write("|-------|----------:|-----:|-------------:|--------:|\n")
            for model in models:
                sc = scores_by_model[model]
                if not sc:
                    f.write(f"| `{model}` | — | — | — | — |\n")
                    continue
                avgs = {}
                for dim in ("correction", "tone", "preservation", "overall"):
                    vals = [s[dim] for s in sc if dim in s]
                    avgs[dim] = round(statistics.mean(vals), 2) if vals else "—"
                f.write(
                    f"| `{model}` | {avgs['correction']} | {avgs['tone']} | {avgs['preservation']} | {avgs['overall']} |\n"
                )

        # --- Per-case comparison ---
        f.write("\n---\n\n## Output Comparison by Case\n\n")
        for case in cases:
            f.write(f"### `{case['id']}` — {case['label']} (`{case['mode']}`)\n\n")
            f.write(f"**Input:**\n> {case['input_text']}\n\n")
            for model in models:
                match = next(
                    (r for r in results if r["model"] == model and r["case_id"] == case["id"]),
                    None,
                )
                if match is None:
                    continue
                if match["error"]:
                    f.write(f"**`{model}`** — ERROR: {match['error']}\n\n")
                    continue

                t = match["wall_time_s"]
                scores_str = ""
                if match.get("judge") and "error" not in match["judge"]:
                    j = match["judge"]
                    scores_str = (
                        f" · correction {j['correction']}/5"
                        f" · tone {j['tone']}/5"
                        f" · preservation {j['preservation']}/5"
                        f" · **overall {j['overall']}/5**"
                    )
                    if j.get("note"):
                        scores_str += f"\n> *{j['note']}*"

                f.write(f"**`{model}`** ({t}s){scores_str}\n> {match['output']}\n\n")


_VERDICT_THRESHOLDS = {
    "excellent": 4.5,
    "good":      3.8,
    "average":   3.0,
}

def _verdict(score: float) -> str:
    if score >= _VERDICT_THRESHOLDS["excellent"]:
        return "Excellent"
    if score >= _VERDICT_THRESHOLDS["good"]:
        return "Good"
    if score >= _VERDICT_THRESHOLDS["average"]:
        return "Average"
    return "Poor"


def _write_constat(
    models: list,
    by_model: dict,
    scores_by_model: dict,
    timestamp: str,
    path: str,
) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# Model Assessment — {timestamp}\n\n")
        f.write(
            "Evaluation of each model on the TextPolish corpus "
            "(spelling correction, tone appropriateness, meaning preservation).\n\n"
        )
        f.write("---\n\n")

        for model in models:
            sc = scores_by_model[model]
            timing = by_model[model]

            f.write(f"## `{model}`\n\n")

            if not sc:
                f.write("*No results available (timeouts or errors).*\n\n")
                continue

            avgs = {
                dim: round(statistics.mean(x[dim] for x in sc if dim in x), 2)
                for dim in ("correction", "tone", "preservation", "overall")
            }
            lat = _compute_stats(timing) if timing else {}

            # Scores table
            f.write("| Criterion | Avg score | Verdict |\n")
            f.write("|-----------|----------:|--------:|\n")
            for dim, label in (
                ("correction", "Spelling & grammar"),
                ("tone", "Tone appropriateness"),
                ("preservation", "Meaning preservation"),
                ("overall", "**Overall**"),
            ):
                v = avgs[dim]
                f.write(f"| {label} | {v}/5 | {_verdict(v)} |\n")

            if lat:
                f.write(f"\n**Latency** — median {lat['median']}s · P95 {lat['p95']}s · min {lat['min']}s · max {lat['max']}s\n\n")

            # Strengths / weaknesses from judge notes
            notes = [x["note"] for x in sc if x.get("note")]
            low = [x for x in sc if x.get("overall", 5) < 3.5]
            high = [x for x in sc if x.get("overall", 0) >= 4.5]

            if high:
                f.write("**Strengths:**\n")
                for x in high[:3]:
                    f.write(f"- `{x.get('case_id', '')}` — {x['note']}\n")
                f.write("\n")

            if low:
                f.write("**Weaknesses:**\n")
                for x in low[:3]:
                    f.write(f"- `{x.get('case_id', '')}` — {x['note']}\n")
                f.write("\n")

            # Recommendation
            overall = avgs["overall"]
            f.write("**Recommendation for TextPolish:**  \n")
            if overall >= 4.5:
                f.write("Recommended — excellent quality across all modes.\n\n")
            elif overall >= 3.8:
                f.write("Usable — good overall quality with minor weaknesses.\n\n")
            elif overall >= 3.0:
                f.write("Average — acceptable for occasional use, "
                        "but notable errors on some cases.\n\n")
            else:
                f.write("Insufficient — too many tone or meaning errors for production use.\n\n")

            f.write("---\n\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Benchmark multiple Ollama models on TextPolish cases.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python benchmark_models.py --models gemma3:4b llama3.2:3b\n"
            "  python benchmark_models.py --models gemma3:4b --judge\n"
            "  python benchmark_models.py --models gemma3:4b --judge --judge-model claude-haiku-4-5"
        ),
    )
    parser.add_argument("--models", nargs="+", required=True, metavar="MODEL",
                        help="Ollama model names to benchmark")
    parser.add_argument("--cases", default="benchmarks/cases.json",
                        help="Path to cases JSON (default: benchmarks/cases.json)")
    parser.add_argument("--output-dir", default="benchmarks/results",
                        help="Output directory (default: benchmarks/results)")
    parser.add_argument("--ollama-url", default=_OLLAMA_BASE_URL,
                        help=f"Ollama base URL (default: {_OLLAMA_BASE_URL})")
    parser.add_argument("--timeout", type=int, default=_OLLAMA_TIMEOUT,
                        help=f"Request timeout in seconds (default: {_OLLAMA_TIMEOUT})")
    parser.add_argument("--judge", action="store_true",
                        help="Score each output with Claude (requires ANTHROPIC_API_KEY)")
    parser.add_argument("--judge-model", default=_JUDGE_DEFAULT_MODEL,
                        help=f"Claude model used as judge (default: {_JUDGE_DEFAULT_MODEL})")
    parser.add_argument("--resume", metavar="TIMESTAMP",
                        help="Resume an interrupted run (e.g. --resume 20260406_123456)")
    args = parser.parse_args()

    with open(args.cases, "r", encoding="utf-8") as f:
        cases = json.load(f)

    os.makedirs(args.output_dir, exist_ok=True)

    # --- Resume support ---
    if args.resume:
        timestamp = args.resume
        json_path = os.path.join(args.output_dir, f"results_{timestamp}.json")
        with open(json_path, "r", encoding="utf-8") as f:
            all_results = json.load(f)
        done_keys = {(r["model"], r["case_id"]) for r in all_results}
        print(f"Resuming run {timestamp} — {len(all_results)} results already done.")
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        all_results = []
        done_keys: set = set()

    json_path = os.path.join(args.output_dir, f"results_{timestamp}.json")
    csv_path = os.path.join(args.output_dir, f"summary_{timestamp}.csv")
    md_path = os.path.join(args.output_dir, f"review_{timestamp}.md")

    # --- Run Ollama inference ---
    total = len(args.models) * len(cases)
    done = len(done_keys)

    for model in args.models:
        pending = [c for c in cases if (model, c["id"]) not in done_keys]
        if not pending:
            print(f"\n=== {model} — already complete, skipping ===")
            continue
        print(f"\n=== {model} ===")
        for case in pending:
            done += 1
            print(f"  [{done}/{total}] {case['id']} ({case['mode']}) ...", end=" ", flush=True)
            result = run_case(model, case, args.ollama_url, args.timeout)
            if result["error"]:
                print(f"ERROR: {result['error'][:80]}")
            else:
                print(f"{result['wall_time_s']}s")
            all_results.append(result)
            done_keys.add((model, case["id"]))
            # Save after every case so interruption loses nothing
            _write_json(all_results, json_path)

    # --- Claude judge pass ---
    if args.judge:
        scoreable = [r for r in all_results if not r["error"] and r["output"] and r.get("judge") is None]
        if scoreable:
            print(f"\n=== Judging {len(scoreable)} outputs with {args.judge_model} ===")
            for i, result in enumerate(scoreable, 1):
                print(f"  [{i}/{len(scoreable)}] {result['model']} / {result['case_id']} ...", end=" ", flush=True)
                scores = judge_result(result, args.judge_model)
                scores["case_id"] = result["case_id"]
                result["judge"] = scores
                if "error" in scores:
                    print(f"ERROR: {scores['error'][:80]}")
                else:
                    print(f"overall {scores['overall']}/5")
                # Save after every judge call too
                _write_json(all_results, json_path)
        else:
            print("\n=== All outputs already judged, skipping ===")

    # --- Aggregate stats ---
    by_model: dict = defaultdict(list)
    scores_by_model: dict = defaultdict(list)
    for r in all_results:
        if not r["error"]:
            by_model[r["model"]].append(r["wall_time_s"])
        if r.get("judge") and "error" not in (r["judge"] or {}):
            scores_by_model[r["model"]].append(r["judge"])

    _write_json(all_results, json_path)
    _write_summary_csv(args.models, by_model, scores_by_model, csv_path)
    _write_markdown(
        args.models, cases, all_results, by_model, scores_by_model,
        timestamp, args.judge_model if args.judge else None, md_path,
    )
    if args.judge and any(scores_by_model.values()):
        constat_path = os.path.join(args.output_dir, f"constat_{timestamp}.md")
        _write_constat(args.models, by_model, scores_by_model, timestamp, constat_path)
    else:
        constat_path = None

    print(f"\nResults saved to {args.output_dir}/")
    print(f"  {os.path.basename(json_path)}  — full results (JSON)")
    print(f"  {os.path.basename(csv_path)}  — timing summary (CSV)")
    print(f"  {os.path.basename(md_path)}  — human-readable review (Markdown)")
    if constat_path:
        print(f"  {os.path.basename(constat_path)}  — model verdict (Markdown)")

    # --- Inline timing summary ---
    print("\n--- Timing Summary (wall time, seconds) ---")
    has_scores = any(scores_by_model.values())
    header = f"{'Model':<30} {'Count':>5} {'Mean':>7} {'Median':>8} {'P95':>7} {'Min':>7} {'Max':>7}"
    if has_scores:
        header += f"  {'Correction':>10} {'Tone':>6} {'Preserv.':>9} {'Overall':>8}"
    print(header)
    print("-" * len(header))
    for model in args.models:
        s = _compute_stats(by_model[model])
        if not s:
            print(f"{model:<30}  (all errors)")
            continue
        line = f"{model:<30} {s['count']:>5} {s['mean']:>7} {s['median']:>8} {s['p95']:>7} {s['min']:>7} {s['max']:>7}"
        if has_scores:
            sc = scores_by_model[model]
            if sc:
                avgs = {
                    dim: round(statistics.mean(x[dim] for x in sc if dim in x), 2)
                    for dim in ("correction", "tone", "preservation", "overall")
                }
                line += f"  {avgs['correction']:>10} {avgs['tone']:>6} {avgs['preservation']:>9} {avgs['overall']:>8}"
            else:
                line += "           —      —         —        —"
        print(line)


if __name__ == "__main__":
    main()
