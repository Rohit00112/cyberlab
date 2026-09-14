"""Offline ML/GNN research track for IIC CyberLab (Phase 6, PRD §72).

Pipeline
--------
1. In the app, a researcher exports a pseudonymized dataset and downloads the
   knowledge-graph JSON from ``GET /api/v1/research/graph``.
2. ``build_graph.py`` turns the graph JSON (nodes/edges) into a ``networkx``
   DiGraph, optionally enriched with solve-rate attributes from a submissions
   export.
3. ``features.py`` derives node/edge feature vectors and writes them to disk.
4. ``train_gnn.py`` runs a sample torch-geometric link-prediction experiment.
   Results can be recorded back in the app via the experiment registry.

Governance
----------
All scripts operate on *exported* pseudonymized artifacts only — never on the
live database and never on raw identities. Participants appear solely as
``participant_id`` values. See ``docs/ARCHITECTURE.md`` (decision 9).

These scripts are intentionally NOT imported by the application and carry no
optional dependencies by default. Install extras with::

    python -m pip install -r research/requirements-optional.txt
"""