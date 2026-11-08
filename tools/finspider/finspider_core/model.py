"""Shared data structures."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import pandas as pd

# Canonical annual fields. All money values are absolute amounts in the
# company's *price* currency (converted if the filings use another currency).
ANNUAL_FIELDS = [
    # net_income = profit attributable to the company's shareholders (used for ROE, EPS);
    # net_income_incl_nci = consolidated profit incl. minority interests (used for cash conversion)
    "revenue", "operating_income", "ebit", "pretax_income", "net_income", "net_income_incl_nci", "eps",
    "interest_expense", "depreciation", "total_assets", "total_equity", "total_debt",
    "current_assets", "current_liabilities", "inventory", "cash", "ocf", "capex",
    "fcf", "net_interest_income", "deposits",
]


@dataclass
class CompanyData:
    ticker: str
    name: str
    currency: str                       # price currency, e.g. INR, USD
    price: Optional[float]
    shares: Optional[float]             # current shares outstanding
    info: dict[str, Any]
    annual: pd.DataFrame                # index: fiscal year (int), columns: ANNUAL_FIELDS
    fy_end: dict[int, pd.Timestamp]     # fiscal year -> period end date
    prices: pd.Series                   # monthly close, split-adjusted
    splits: pd.Series                   # split/bonus ratios by date
    quarterly_npa: Optional[pd.DataFrame] = None   # index: quarter label, cols gnpa_pct / nnpa_pct
    sources: dict[str, str] = field(default_factory=dict)   # field -> "yfinance" / "screener"
    warnings: list[str] = field(default_factory=list)
    screener_url: Optional[str] = None
    trailing_pe: Optional[float] = None
    manual: dict[str, Any] = field(default_factory=dict)
    # field -> year -> {source, doc, url, status: official|verified|single|mismatch, check?}
    provenance: dict[str, dict[int, dict]] = field(default_factory=dict)
    primary_source: str = "Yahoo Finance"
    sec: Optional[dict[str, Any]] = None


@dataclass
class Metric:
    key: str
    label: str
    value: Optional[float]
    unit: str                           # "x", "%", "pp", "money", "count"
    history: dict[int, float] = field(default_factory=dict)
    note: str = ""                      # e.g. "5y avg 24.1x", "4y CAGR"
    trend: str = ""                     # improving / worsening / stable (vs 3 years earlier)
    workings: Optional[dict[str, Any]] = None   # {formula, inputs: [...]} - how the value was built
    verified: bool = True               # False if any input's sources disagree -> never scored
    score: Optional[float] = None
    flag: str = "n/a"                   # good / ok / bad / n/a
    category: Optional[str] = None


@dataclass
class RedFlag:
    key: str
    severity: str                       # critical / warning
    text: str


@dataclass
class Assessment:
    profile: str
    metrics: dict[str, Metric]
    category_scores: dict[str, Optional[float]]
    category_weights: dict[str, float]
    overall: Optional[float]
    coverage: float
    verdict: str
    verdict_note: str
    strengths: list[str]
    weaknesses: list[str]
    red_flags: list[RedFlag]
