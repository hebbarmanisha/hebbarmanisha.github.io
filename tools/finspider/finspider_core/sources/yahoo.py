"""Fetch and normalise data from Yahoo Finance (via yfinance)."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

import numpy as np
import pandas as pd

from ..cache import FileCache
from ..errors import DataUnavailable
from ..model import ANNUAL_FIELDS

log = logging.getLogger(__name__)

# canonical field -> yfinance row names, in order of preference
INCOME_MAP = {
    "revenue": ["Total Revenue", "Operating Revenue"],
    "operating_income": ["Operating Income", "Total Operating Income As Reported"],
    "ebit": ["EBIT"],
    "pretax_income": ["Pretax Income"],
    "net_income": ["Net Income Common Stockholders", "Net Income",
                   "Net Income From Continuing Operation Net Minority Interest"],
    "net_income_incl_nci": ["Net Income Including Noncontrolling Interests"],
    "eps": ["Diluted EPS", "Basic EPS"],
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
    "depreciation": ["Reconciled Depreciation", "Depreciation And Amortization In Income Statement"],
    "net_interest_income": ["Net Interest Income"],
}
BALANCE_MAP = {
    "total_assets": ["Total Assets"],
    "total_equity": ["Stockholders Equity", "Common Stock Equity"],
    "total_debt": ["Total Debt"],
    "current_assets": ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
    "inventory": ["Inventory"],
    "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"],
    "deposits": ["Deposits", "Total Deposits"],
}
CASHFLOW_MAP = {
    "ocf": ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"],
    "capex": ["Capital Expenditure"],
    "fcf": ["Free Cash Flow"],
}
# fields that are per-share or ratios: converted for currency but never scaled otherwise
PER_SHARE = {"eps"}

# Yahoo quotes some markets in minor units (pence, cents, agorot)
MINOR_UNITS = {"GBp": ("GBP", 100), "GBX": ("GBP", 100), "ZAc": ("ZAR", 100), "ILA": ("ILS", 100)}


def _with_retries(fn, what: str, tries: int = 2):
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # yfinance raises a variety of errors, incl. rate limits
            last = e
            wait = 2 ** i * 2
            log.debug("%s failed (%s); retrying in %ss", what, e, wait)
            time.sleep(wait)
    raise DataUnavailable(f"Could not fetch {what} from Yahoo Finance: {last}")


def fetch_raw(ticker: str, cache: FileCache, ttl_hours: float) -> dict[str, Any]:
    """Download everything we need for one ticker (cached)."""
    import yfinance as yf

    def _fetch():
        t = yf.Ticker(ticker)
        try:
            info = t.info or {}
        except Exception as e:
            log.warning("yfinance info failed for %s: %s", ticker, e)
            info = {}
        raw = {
            "info": info,
            "income": _with_retries(lambda: t.income_stmt, "income statement"),
            "balance": _with_retries(lambda: t.balance_sheet, "balance sheet"),
            "cashflow": _with_retries(lambda: t.cashflow, "cash flow"),
            "history": _with_retries(lambda: t.history(period="15y", interval="1mo", auto_adjust=False),
                                     "price history"),
        }
        try:
            raw["splits"] = t.splits
        except Exception:
            raw["splits"] = pd.Series(dtype=float)
        if (raw["income"] is None or raw["income"].empty) and not info:
            return None
        return raw

    raw = cache.get_or_set(f"yf:{ticker}", ttl_hours * 3600, _fetch)
    if raw is None:
        raise DataUnavailable(f"Yahoo Finance returned no data for {ticker}.")
    return raw


def fetch_fx_history(pair: str, cache: FileCache, ttl_hours: float) -> pd.Series:
    """Monthly close for an FX pair like 'USDINR=X'."""
    import yfinance as yf

    def _fetch():
        h = yf.Ticker(pair).history(period="15y", interval="1mo")
        return None if h is None or h.empty else h["Close"]

    s = cache.get_or_set(f"fx:{pair}", ttl_hours * 3600, _fetch)
    return s if s is not None else pd.Series(dtype=float)


def _pick_row(df: pd.DataFrame, names: list[str]) -> Optional[pd.Series]:
    if df is None or df.empty:
        return None
    for n in names:
        if n in df.index:
            row = pd.to_numeric(df.loc[n], errors="coerce")
            if row.notna().any():
                return row
    return None


def _value_at(series: pd.Series, when: pd.Timestamp) -> Optional[float]:
    """Last value on or before `when` (tz-naive comparison)."""
    if series is None or series.empty:
        return None
    s = series.copy()
    idx = pd.to_datetime(s.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s.index = idx
    s = s.sort_index()
    s = s[s.index <= when]   # monthly bars are dated the 1st of their month
    s = s.dropna()
    return float(s.iloc[-1]) if not s.empty else None


def normalise(raw: dict[str, Any], cache: FileCache, ttl_hours: float) -> dict[str, Any]:
    """Return canonical annual frame (price currency, absolute units) + metadata."""
    info = raw.get("info") or {}
    warnings: list[str] = []

    price_cur = info.get("currency") or ""
    price_div = 1.0
    if price_cur in MINOR_UNITS:
        price_cur, price_div = MINOR_UNITS[price_cur]
    fin_cur = info.get("financialCurrency") or price_cur

    columns: dict[str, pd.Series] = {}
    for df_key, mapping in (("income", INCOME_MAP), ("balance", BALANCE_MAP), ("cashflow", CASHFLOW_MAP)):
        df = raw.get(df_key)
        for field, names in mapping.items():
            row = _pick_row(df, names)
            if row is not None:
                columns[field] = row

    if not columns:
        annual = pd.DataFrame(columns=ANNUAL_FIELDS, dtype=float)
        return {"annual": annual, "fy_end": {}, "price_currency": price_cur, "price_divisor": price_div,
                "warnings": ["Yahoo Finance has no financial statements for this ticker."]}

    frame = pd.DataFrame(columns)
    frame.index = pd.to_datetime(frame.index)
    frame = frame.sort_index()
    # one row per fiscal year (keep the latest period if a year appears twice)
    frame["_year"] = frame.index.year
    fy_end = {int(y): ts for ts, y in zip(frame.index, frame["_year"])}
    frame = frame.groupby("_year").last()
    frame.index = frame.index.astype(int)
    frame.index.name = "year"

    # Convert filings currency -> price currency (e.g. Infosys files in USD, trades in INR)
    if fin_cur and price_cur and fin_cur != price_cur:
        pair = f"{fin_cur}{price_cur}=X"
        fx = fetch_fx_history(pair, cache, ttl_hours)
        if fx.empty:
            warnings.append(f"Financials are in {fin_cur} but no {pair} FX history was found; "
                            "valuation ratios may be wrong.")
        else:
            for y in frame.index:
                rate = _value_at(fx, fy_end[y])
                if rate:
                    frame.loc[y] = frame.loc[y] * rate
            warnings.append(f"Yahoo financials were reported in {fin_cur}; converted to {price_cur} "
                            "at each fiscal year-end exchange rate.")

    for f in ANNUAL_FIELDS:
        if f not in frame.columns:
            frame[f] = np.nan
    frame = frame[ANNUAL_FIELDS].astype(float)
    if "capex" in frame:
        frame["capex"] = frame["capex"].abs()
    if "interest_expense" in frame:
        frame["interest_expense"] = frame["interest_expense"].abs()
    return {"annual": frame, "fy_end": fy_end, "price_currency": price_cur,
            "price_divisor": price_div, "warnings": warnings}


def monthly_prices(raw: dict[str, Any], divisor: float) -> pd.Series:
    h = raw.get("history")
    if h is None or h.empty or "Close" not in h:
        return pd.Series(dtype=float)
    s = h["Close"].dropna() / divisor   # yfinance Close is split-adjusted
    idx = pd.to_datetime(s.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s.index = idx
    return s


def splits_series(raw: dict[str, Any]) -> pd.Series:
    s = raw.get("splits")
    if s is None or len(s) == 0:
        return pd.Series(dtype=float)
    s = s.copy()
    idx = pd.to_datetime(s.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    s.index = idx
    return s[s > 0]
