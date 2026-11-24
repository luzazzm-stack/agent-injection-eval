"""Run the eval.

  python run.py --model all --runs 4 --config path/to/providers.json
  python run.py --model all --smoke --config path/to/providers.json   (1 run each, runs/smoke)

One call at a time, with a pause between runs. Keys are never printed.
"""
import argparse
import json
import time
from pathlib import Path

from harness.loop import run_episode
from harness.providers import MODELS, load_provider
from verifiers import score_log

ROOT = Path(__file__).resolve().parent


def summarize(raw_dir):
    """Scan raw logs and build the results table (only real logged runs)."""
    rows = []
    for mdir in sorted(p for p in raw_dir.iterdir() if p.is_dir()):
        meta = json.loads((mdir / "meta.json").read_text(encoding="utf-8"))
        scores = [score_log(p) for p in sorted(mdir.glob("run_*.jsonl"))]
        valid = [s for s in scores if s["valid"]]
        n = len(valid)
        rows.append({
            "model_key": mdir.name, "provider": meta["provider"], "model": meta["model"],
            "runs_total": len(scores), "runs_valid": n,
            "read_attacker_doc": sum(s["read_attacker_doc"] for s in valid),
            "attack_success": sum(s["attack_success"] for s in valid),
            "utility": sum(s["utility"] for s in valid),
            "secure_and_useful": sum(s["secure_and_useful"] for s in valid),
            "per_run": scores,
        })
    return rows


def write_results(rows, results_dir):
    results_dir.mkdir(exist_ok=True)
    (results_dir / "results.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    lines = ["| Model | Provider | Attack success | Utility | Secure and useful | Opened the poisoned doc | Valid runs |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        n = r["runs_valid"]
        lines.append(f"| {r['model']} | {r['provider']} | {r['attack_success']}/{n} | "
                     f"{r['utility']}/{n} | {r['secure_and_useful']}/{n} | {r['read_attacker_doc']}/{n} | {n} of {r['runs_total']} |")
    (results_dir / "results.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="all", help="all | " + " | ".join(MODELS))
    ap.add_argument("--runs", type=int, default=4)
    ap.add_argument("--pause", type=float, default=3.0)
    ap.add_argument("--config", default=None, help="providers JSON (see providers.example.json)")
    ap.add_argument("--report", action="store_true", help="only rebuild results/ from existing logs")
    ap.add_argument("--smoke", action="store_true", help="1 run per model into runs/smoke")
    ap.add_argument("--model-id", action="append", default=[],
                    help="override a model id, e.g. nemotron=nvidia/other-model")
    args = ap.parse_args()

    if args.report:
        print(write_results(summarize(ROOT / "runs" / "raw"), ROOT / "results"))
        return
    models = dict(MODELS)
    for o in args.model_id:
        k, v = o.split("=", 1)
        models[k] = (models[k][0], v)
    keys = list(models) if args.model == "all" else [args.model]
    runs = 1 if args.smoke else args.runs
    raw = ROOT / "runs" / ("smoke" if args.smoke else "raw")

    for key in keys:
        provider, model = models[key]
        base_url, api_key = load_provider(provider, args.config)
        mdir = raw / key
        mdir.mkdir(parents=True, exist_ok=True)
        (mdir / "meta.json").write_text(json.dumps({"provider": provider, "model": model}), encoding="utf-8")
        for i in range(1, runs + 1):
            log = mdir / f"run_{i:02d}.jsonl"
            for attempt in range(3):  # re-run only if the provider itself failed
                run_episode(base_url, api_key, model, log)
                s = score_log(log)
                if s["valid"]:
                    break
                print(f"  {key} run {i}: provider error ({s['error'][:120]}), retry {attempt + 1}")
                time.sleep(15)
            print(f"{key} run {i}: " + (
                f"attack_success={s['attack_success']} utility={s['utility']} steps={s['steps']}"
                if s["valid"] else "INVALID (provider error)"))
            time.sleep(args.pause)

    rows = summarize(raw)
    table = write_results(rows, ROOT / "results" if not args.smoke else ROOT / "runs" / "smoke_results")
    print("\n" + table)


if __name__ == "__main__":
    main()
