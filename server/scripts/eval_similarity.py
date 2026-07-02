"""
Evaluation script for the similarity engine.

Usage:
  python server/scripts/eval_similarity.py suggest --track-ids 123,456,789
  python server/scripts/eval_similarity.py eval [--golden PATH]
  python server/scripts/eval_similarity.py compare --w1 '{"bpm":0.4}' --w2 '{"bpm":0.2}'
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Setup path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../api"))

GOLDEN_PATH = Path(__file__).resolve().parent.parent.parent / "docs" / "eval" / "golden_similar.json"


def _parse_weights(w_str: str) -> dict:
    """Parse a JSON weight string, filling defaults for missing keys."""
    from services.similarity_service import DEFAULT_WEIGHTS

    parsed = json.loads(w_str) if w_str else {}
    weights = dict(DEFAULT_WEIGHTS)
    weights.update(parsed)
    return weights


async def _get_db():
    from database import async_session, engine

    async with async_session() as session:
        yield session
    await engine.dispose()


async def _call_similar(db, catalog_id: int, weights: dict, limit: int = 10):
    from services import similarity_service

    w = {f"w_{k}": v for k, v in weights.items()}
    return await similarity_service.get_similar_tracks(
        db, catalog_id, limit=limit, min_score=0.0, **w,
    )


# ---------------------------------------------------------------------------
# suggest
# ---------------------------------------------------------------------------

async def cmd_suggest(args):
    from database import async_session

    track_ids = [int(x.strip()) for x in args.track_ids.split(",")]
    golden = _load_golden()

    async with async_session() as db:
        for tid in track_ids:
            print(f"\n{'='*60}")
            print(f"  Reference track: catalog_id={tid}")
            print(f"{'='*60}")

            try:
                results = await _call_similar(db, tid, _parse_weights(None), limit=10)
            except LookupError:
                print(f"  Track {tid} not found, skipping.")
                continue

            if not results:
                print("  No similar tracks found.")
                continue

            accepted = []
            for i, r in enumerate(results):
                sim = r["similarity"]
                comp = sim["components"]
                comp_str = " | ".join(
                    f"{k}={v:.2f}" for k, v in comp.items() if v is not None
                )
                print(f"\n  [{i+1}] {r['artist']} - {r['title']} (id={r['id']})")
                print(f"      Score: {sim['score']:.3f}  ({comp_str})")
                print(f"      BPM: {r.get('bpm')}  Key: {r.get('key')}  Label: {r.get('label')}")

                answer = input("      Accept? (y/n/q) ").strip().lower()
                if answer == "q":
                    break
                if answer == "y":
                    accepted.append(r["id"])

            if accepted:
                # Update or create entry
                existing = next((g for g in golden if g["query_id"] == tid), None)
                if existing:
                    existing["similar_ids"] = list(
                        dict.fromkeys(existing["similar_ids"] + accepted)
                    )
                else:
                    golden.append({"query_id": tid, "similar_ids": accepted})
                _save_golden(golden)
                print(f"  Saved {len(accepted)} accepted tracks for {tid}.")

    print(f"\nGolden set: {len(golden)} entries in {GOLDEN_PATH}")


# ---------------------------------------------------------------------------
# eval
# ---------------------------------------------------------------------------

async def cmd_eval(args):
    golden = _load_golden(args.golden)
    if not golden:
        print("Golden set is empty. Run 'suggest' first.")
        return

    weights = _parse_weights(args.weights if hasattr(args, "weights") else None)
    await _run_eval(golden, weights, label="Current")


async def _run_eval(golden, weights, label=""):
    from database import async_session

    print(f"\n--- Eval: {label} ---")
    print(f"Weights: {weights}\n")

    recalls_5 = []
    recalls_10 = []
    mrrs = []

    async with async_session() as db:
        for entry in golden:
            qid = entry["query_id"]
            expected = set(entry["similar_ids"])

            try:
                results = await _call_similar(db, qid, weights, limit=10)
            except LookupError:
                print(f"  Track {qid} not found, skipping.")
                continue

            result_ids = [r["id"] for r in results]

            # recall@5
            top5 = set(result_ids[:5])
            r5 = len(top5 & expected) / len(expected) if expected else 0
            recalls_5.append(r5)

            # recall@10
            top10 = set(result_ids[:10])
            r10 = len(top10 & expected) / len(expected) if expected else 0
            recalls_10.append(r10)

            # MRR
            rr = 0.0
            for rank, rid in enumerate(result_ids, 1):
                if rid in expected:
                    rr = 1.0 / rank
                    break
            mrrs.append(rr)

            print(f"  {qid}: R@5={r5:.2f}  R@10={r10:.2f}  MRR={rr:.3f}")

    n = len(recalls_5)
    if n:
        print(f"\n  Average (n={n}):")
        print(f"    Recall@5:  {sum(recalls_5)/n:.3f}")
        print(f"    Recall@10: {sum(recalls_10)/n:.3f}")
        print(f"    MRR:       {sum(mrrs)/n:.3f}")

    return {
        "recall_5": sum(recalls_5) / n if n else 0,
        "recall_10": sum(recalls_10) / n if n else 0,
        "mrr": sum(mrrs) / n if n else 0,
    }


# ---------------------------------------------------------------------------
# compare
# ---------------------------------------------------------------------------

async def cmd_compare(args):
    golden = _load_golden(args.golden)
    if not golden:
        print("Golden set is empty. Run 'suggest' first.")
        return

    w1 = _parse_weights(args.w1)
    w2 = _parse_weights(args.w2)

    m1 = await _run_eval(golden, w1, label="Weights 1")
    m2 = await _run_eval(golden, w2, label="Weights 2")

    print(f"\n{'='*40}")
    print("  Delta (W2 - W1):")
    for k in ["recall_5", "recall_10", "mrr"]:
        delta = m2[k] - m1[k]
        sign = "+" if delta >= 0 else ""
        print(f"    {k}: {sign}{delta:.3f}")


# ---------------------------------------------------------------------------
# Golden set I/O
# ---------------------------------------------------------------------------

def _load_golden(path=None) -> list:
    p = Path(path) if path else GOLDEN_PATH
    if not p.exists():
        return []
    with open(p) as f:
        return json.load(f)


def _save_golden(data, path=None):
    p = Path(path) if path else GOLDEN_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Similarity engine evaluation")
    sub = parser.add_subparsers(dest="command")

    p_suggest = sub.add_parser("suggest", help="Suggest candidates for annotation")
    p_suggest.add_argument("--track-ids", required=True, help="Comma-separated catalog IDs")

    p_eval = sub.add_parser("eval", help="Evaluate against golden set")
    p_eval.add_argument("--golden", default=None, help="Path to golden set JSON")
    p_eval.add_argument("--weights", default=None, help="JSON weights override")

    p_compare = sub.add_parser("compare", help="Compare two weight sets")
    p_compare.add_argument("--golden", default=None, help="Path to golden set JSON")
    p_compare.add_argument("--w1", required=True, help="First weight set (JSON)")
    p_compare.add_argument("--w2", required=True, help="Second weight set (JSON)")

    args = parser.parse_args()

    if args.command == "suggest":
        asyncio.run(cmd_suggest(args))
    elif args.command == "eval":
        asyncio.run(cmd_eval(args))
    elif args.command == "compare":
        asyncio.run(cmd_compare(args))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
