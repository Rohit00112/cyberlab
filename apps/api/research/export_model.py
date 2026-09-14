#!/usr/bin/env python3
"""Export a trained PyTorch GNN checkpoint to ONNX (Phase 7, PRD §72).

Usage:
    python research/export_model.py --checkpoint model.pt --output data/research/model/gnn.onnx

The ONNX model must follow the contract:
  input  "features"   float32 [N, 5]
  output "embeddings"  float32 [N, D]
"""
from __future__ import annotations

import argparse
from pathlib import Path


def export(checkpoint_path: str, output_path: str, embed_dim: int = 32) -> None:
    try:
        import torch  # type: ignore[import-not-found]
    except ModuleNotFoundError as err:
        raise SystemExit("PyTorch is required: pip install torch") from err

    from research.train_gnn import CyberLabGNN  # type: ignore[import-not-found]

    FEATURE_DIM = 5

    model = CyberLabGNN(in_channels=FEATURE_DIM, hidden_channels=64, out_channels=embed_dim)
    state = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
    model.load_state_dict(state)
    model.eval()

    dummy = torch.randn(4, FEATURE_DIM)

    out_dir = Path(output_path).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    torch.onnx.export(
        model,
        (dummy,),
        output_path,
        input_names=["features"],
        output_names=["embeddings"],
        dynamic_axes={
            "features": {0: "num_challenges"},
            "embeddings": {0: "num_challenges"},
        },
        opset_version=17,
    )
    print(f"Exported ONNX model → {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Export GNN checkpoint to ONNX")
    parser.add_argument(
        "--checkpoint", required=True, help="Path to .pt checkpoint"
    )
    parser.add_argument(
        "--output",
        default="data/research/model/gnn.onnx",
        help="Output ONNX path",
    )
    parser.add_argument(
        "--embed-dim",
        type=int,
        default=32,
        help="Embedding dimension (default: 32)",
    )
    args = parser.parse_args()
    export(args.checkpoint, args.output, args.embed_dim)


if __name__ == "__main__":
    main()
