"""Sample GNN link-prediction experiment (Phase 6, PRD §72 — H4).

Trains a small GCN to predict whether an unobserved challenge<->skill edge
should exist, i.e. whether a challenge should be tagged with a skill. This is a
reference implementation; swap in your own model/training loop as needed.

Usage::

    python research/train_gnn.py \
        --graph data/research/graph.pkl \
        --features data/research/features.pkl \
        --epochs 50

Requires ``torch`` and ``torch-geometric`` (see requirements-optional.txt).
The API never runs models — this script is executed by a researcher against
pseudonymized exports only.
"""
from __future__ import annotations

import argparse
import pickle
from pathlib import Path

try:
    import torch
    from torch_geometric.data import Data
    from torch_geometric.nn import GCNConv
    from torch_geometric.utils import negative_sampling, train_test_split_edges
except ImportError as _import_error:  # pragma: no cover
    raise SystemExit(
        "torch / torch-geometric not installed. Run: "
        "python -m pip install -r research/requirements-optional.txt"
    ) from _import_error

def _load(path: str):
    with Path(path).open("rb") as handle:
        return pickle.load(handle)

class GCNLinkPred(torch.nn.Module):
    def __init__(self, in_dim: int, hidden: int = 32) -> None:
        super().__init__()
        self.conv1 = GCNConv(in_dim, hidden)
        self.conv2 = GCNConv(hidden, hidden)

    def encode(self, x, edge_index):
        x = self.conv1(x, edge_index).relu()
        return self.conv2(x, edge_index)

    def decode(self, z, edge_index):
        src, dst = edge_index
        return (z[src] * z[dst]).sum(dim=1)

    def forward(self, data):
        z = self.encode(data.x, data.train_pos_edge_index)
        pos = self.decode(z, data.train_pos_edge_index)
        neg = self.decode(z, data.train_neg_edge_index)
        return z, pos, neg

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", default="data/research/graph.pkl")
    parser.add_argument("--features", default="data/research/features.pkl")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--hidden", type=int, default=32)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    graph = _load(args.graph)
    feature_data = _load(args.features)

    node_ids = feature_data["node_ids"]
    features = feature_data["features"]
    id_to_index = {node_id: i for i, node_id in enumerate(node_ids)}

    x = torch.tensor(features, dtype=torch.float)
    edge_index = []
    for source, target, _edge_data in graph.edges(data=True):
        s = id_to_index.get(source)
        t = id_to_index.get(target)
        if s is not None and t is not None:
            edge_index.append([s, t])
    edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()
    if edge_index.numel() == 0:
        raise SystemExit("No edges map to feature nodes — check graph/features alignment")

    data = Data(x=x, edge_index=edge_index)
    split = train_test_split_edges(data)
    data.train_pos_edge_index = split.train_pos_edge_index
    data.train_neg_edge_index = negative_sampling(
        split.train_pos_edge_index,
        num_nodes=data.num_nodes,
        num_neg_samples=split.train_pos_edge_index.size(1),
    )
    data.val_pos_edge_index = split.val_pos_edge_index
    data.val_neg_edge_index = split.val_neg_edge_index

    model = GCNLinkPred(x.size(1), hidden=args.hidden)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    loss_fn = torch.nn.BCEWithLogitsLoss()

    def evaluate(edge_index):
        z = model.conv1(x, data.train_pos_edge_index).relu()
        z = model.conv2(z, data.train_pos_edge_index)
        pos = model.decode(z, edge_index)
        return torch.sigmoid(pos).mean().item()

    for epoch in range(1, args.epochs + 1):
        model.train()
        optimizer.zero_grad()
        z, pos, neg = model.forward(data)
        loss = loss_fn(pos, torch.ones_like(pos)) + loss_fn(neg, torch.zeros_like(neg))
        loss.backward()
        optimizer.step()
        if epoch % 10 == 0 or epoch == args.epochs:
            val_pos = evaluate(data.val_pos_edge_index)
            val_neg = evaluate(data.val_neg_edge_index)
            print(
                f"epoch {epoch:>3} loss {loss.item():.4f} "
                f"val-pos {val_pos:.4f} val-neg {val_neg:.4f}"
            )

    # Simple ranking metric: AUC via positive/negative score separation.
    model.eval()
    with torch.no_grad():
        z = model.encode(x, data.train_pos_edge_index)
        pos_scores = model.decode(z, data.val_pos_edge_index)
        neg_scores = model.decode(z, data.val_neg_edge_index)
        auc = _auc(pos_scores, neg_scores)
    print(f"VALIDATION AUC: {auc:.4f}")

def _auc(pos_scores: torch.Tensor, neg_scores: torch.Tensor) -> float:
    pairs = [(float(p), 1) for p in pos_scores] + [(float(n), 0) for n in neg_scores]
    pairs.sort(key=lambda pair: pair[0], reverse=True)
    n_pos = sum(1 for _, label in pairs if label == 1)
    n_neg = len(pairs) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    rank_sum = sum(rank for rank, (_, label) in enumerate(pairs, start=1) if label == 1)
    auc = (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
    return round(auc, 4)

if __name__ == "__main__":
    main()