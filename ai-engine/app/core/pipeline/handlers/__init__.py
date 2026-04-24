"""DAG node handlers — one module per primitive.

Existing handlers still live in dag_executor.py for now; new primitives
(model_call, branch) live here as standalone modules to keep them clean.
"""
