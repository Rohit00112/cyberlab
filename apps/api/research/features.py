"""Feature extraction for graph ML (Phase 6, PRD §72).

Consumes the graph built by ``build_graph.py`` and optionally a submissions
export to derive node feature vectors:

- challenge nodes: attempts, solve_rate, in/out degree
- skill nodes: out-degree (challenge coverage), parent/child hierarchy degree
- category nodes: child count

Writes a feature matrix (rows aligned with the node list) + a node-name map so
training scripts can map back to graph ids.
"""
from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path


def _load_json(path: str) -> list | dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default="data/research/graph.pkl")
    parser.add_argument("--solves-json", help="Optional exported submissions JSON")
    parser.add_argument("--out", default="data/research/features.pkl")
    args = parser.parse_args()

    graph_path = Path(args.graph)
    if not graph_path.exists():
        raise SystemExit(f"Graph not found at {graph_path} — run build_graph.py first")

    with graph_path.open("rb") as handle:

        G = pickle.load(handle)

    solves: list | dict = []
    if args.solves_json:
        solves = _load_json(args.solves_json)
    per_challenge: dict[str, dict[str, int]] = {}
    for row in solves:
        cid = row.get("challenge_id")
        if not cid:
            continue
        bucket = per_challenge.setdefault(cid, {"attempts": 0, "solves": 0})
        bucket["attempts"] += 1
        if row.get("is_correct"):
            bucket["solves"] += 1

    node_ids = list(G.nodes())
    feature_rows: list[list[float]] = []
    for node_id in node_ids:
        node = G.nodes[node_id]
        ntype = node.get("type", "challenge")
        features: list[float] = [
            float(G.in_degree(node_id)),
            float(G.out_degree(node_id)),
        ]
        if ntype == "challenge":
            cid = node_id.split(":", 1)[-1]
            bucket = per_challenge.get(cid, {"attempts": 0, "solves": 0})
            solve_rate = bucket["solves"] / bucket["attempts"] if bucket["attempts"] else 0.0
            features += [solve_rate, float(bucket["attempts"]), node.get("solve_rate", 0.0)]
        elif ntype == "skill":
            features += [float(G.out_degree(node_id)), 0.0, 0.0]
        else:
            features += [0.0, 0.0, 0.0]
        feature_rows.append(features)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as handle:
        pickle.dump({"node_ids": node_ids, "features": feature_rows}, handle)
    print(f"Wrote features for {len(node_ids)} nodes -> {out}")

if __name__ == "__main__":
    main()