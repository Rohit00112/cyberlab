"""Build a networkx graph from a knowledge-graph export + optional submissions.

Usage::

    python research/build_graph.py \
        --graph-json data/research/exports-graph.json \
        --solves-json data/research/exports-submissions.json \
        --out data/research/graph.pkl

The graph JSON comes from ``GET /api/v1/research/graph`` (nodes are typed
``skill``/``challenge``/``category``; edges carry a ``relation``). The solves
export optionally supplies per-node solve-rate / attempt features.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: str) -> list | dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))

def _relation_weight(relation: str) -> float:
    return {"requires": 2.0, "in": 1.0, "co_solved": 1.0, "step": 2.0}.get(relation, 1.0)

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-json", required=True, help="Exported knowledge-graph JSON")
    parser.add_argument("--solves-json", help="Optional exported submissions JSON")
    parser.add_argument("--out", default="data/research/graph.pkl")
    args = parser.parse_args()

    try:
        import networkx as nx
    except ImportError as exc:
        deps = "python -m pip install -r research/requirements-optional.txt"
        raise SystemExit(f"networkx is not installed. Run: {deps}") from exc

    graph = _load(args.graph_json)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    G = nx.DiGraph()
    for node in nodes:
        G.add_node(node["id"], type=node["type"], label=node["label"])
    for edge in edges:
        G.add_edge(
            edge["source"],
            edge["target"],
            relation=edge["relation"],
            weight=_relation_weight(edge["relation"]),
        )

    if args.solves_json:
        solves = _load(args.solves_json)
        per_challenge: dict[str, dict[str, int]] = {}
        for row in solves:
            cid = row.get("challenge_id")
            if not cid:
                continue
            bucket = per_challenge.setdefault(cid, {"attempts": 0, "solves": 0})
            bucket["attempts"] += 1
            if row.get("is_correct"):
                bucket["solves"] += 1
        for cid, bucket in per_challenge.items():
            node_id = f"challenge:{cid}"
            if G.has_node(node_id):
                solve_rate = bucket["solves"] / bucket["attempts"] if bucket["attempts"] else 0.0
                G.nodes[node_id]["attempts"] = bucket["attempts"]
                G.nodes[node_id]["solve_rate"] = round(solve_rate, 4)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("wb") as handle:
        import pickle

        pickle.dump(G, handle)
    print(
        f"Wrote {G.number_of_nodes()} nodes / {G.number_of_edges()} edges -> {out} "
        f"({len(nodes)} exported nodes, {len(edges)} exported edges)"
    )

if __name__ == "__main__":
    main()