"""Combine a primary source with a second, independent one and label every figure.

Each (field, year) gets a citation and a status:
  official  - taken from a regulator filing (SEC 10-K)
  verified  - primary source agrees with an independent second source within the tolerance
  single    - only one source has it (nothing to compare against); shown, and scored
  mismatch  - the two sources disagree by more than the tolerance; shown, but never scored
"""
from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd

from ..model import ANNUAL_FIELDS

STATUS_RANK = {"official": 0, "verified": 1, "single": 2, "mismatch": 3}


def worst(statuses) -> str:
    st = [s for s in statuses if s in STATUS_RANK]
    return max(st, key=STATUS_RANK.get) if st else "single"


def _num(v) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def pct_diff(a: float, b: float) -> float:
    """% difference of a from reference b (0 when both are 0)."""
    if b == 0:
        return 0.0 if a == 0 else math.inf
    return (a / b - 1) * 100


def combine(primary: pd.DataFrame, primary_cite: dict[str, Any], primary_prov: Optional[dict],
            secondary: Optional[pd.DataFrame], secondary_cite: Optional[dict[str, Any]],
            compare_fields: list[str], tolerance_pct: float, history_years: int
            ) -> tuple[pd.DataFrame, dict[str, dict[int, dict]]]:
    """Primary wins; secondary fills gaps and cross-checks overlapping figures."""
    years = set(primary.index) if primary is not None else set()
    if secondary is not None and not secondary.empty:
        years |= set(secondary.index) if primary is None or primary.empty else set()
    years = sorted(years)[-history_years:]
    out = pd.DataFrame(index=pd.Index(years, name="year"), columns=ANNUAL_FIELDS, dtype=float)
    prov: dict[str, dict[int, dict]] = {}

    for f in ANNUAL_FIELDS:
        for y in years:
            p = _num(primary.at[y, f]) if primary is not None and y in primary.index and f in primary else None
            s = (_num(secondary.at[y, f]) if secondary is not None and y in secondary.index and f in secondary
                 else None)
            if p is not None:
                cite = dict((primary_prov or {}).get(f, {}).get(y) or primary_cite)
                if s is not None and f in compare_fields and secondary_cite:
                    d = pct_diff(s, p)
                    agree = abs(d) <= tolerance_pct
                    cite["check"] = f"{secondary_cite['source']}: {'agrees' if agree else 'differs'} ({d:+.1f}%)"
                    if cite.get("status") != "official":
                        cite["status"] = "verified" if agree else "mismatch"
                cite.setdefault("status", "single")
                out.at[y, f] = p
                prov.setdefault(f, {})[y] = cite
            elif s is not None and secondary_cite:
                out.at[y, f] = s
                prov.setdefault(f, {})[y] = dict(secondary_cite, status="single")
    out = out.dropna(how="all")
    return out, prov


def summary(prov: dict[str, dict[int, dict]], fields: Optional[list[str]] = None,
            years: Optional[list[int]] = None) -> dict[str, int]:
    counts = {k: 0 for k in STATUS_RANK}
    for f, by_year in prov.items():
        if fields and f not in fields:
            continue
        for y, c in by_year.items():
            if years and y not in years:
                continue
            counts[c.get("status", "single")] += 1
    return counts
