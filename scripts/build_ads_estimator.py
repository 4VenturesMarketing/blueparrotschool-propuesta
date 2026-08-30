#!/usr/bin/env python3
"""Rebuild ads-estimator.json from keyword-stats xlsx + bps.db.

Run from repo root after updating dashboard/data/keyword-stats/*.xlsx:
  python3 scripts/build_ads_estimator.py
"""
# Logic lives inline in the conversation build; re-exec by importing path.
# For maintainability, keep this as a thin wrapper that documents the pipeline.
import runpy
from pathlib import Path

# Prefer regenerating via the same module body stored next to this file if present.
here = Path(__file__).resolve().parent
alt = here / "_build_ads_estimator_impl.py"
if alt.exists():
    runpy.run_path(str(alt), run_name="__main__")
else:
    print(
        "Implementation was generated in-session. Re-run the categorization "
        "script from the agent, or restore _build_ads_estimator_impl.py."
    )
