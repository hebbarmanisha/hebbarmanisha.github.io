"""SEC EDGAR: official annual figures (10-K XBRL) for US-listed companies.

Every value keeps a citation to the exact filing it came from, so a reader can open the
10-K on sec.gov and check it. Uses the free public "company facts" API.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date
from typing import Any, Optional

import numpy as np
import pandas as pd
import requests

from ..cache import FileCache
from ..model import ANNUAL_FIELDS

log = logging.getLogger(__name__)

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

# canonical field -> us-gaap tags, most preferred first (companies switch tags over the years)
DURATION_TAGS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet",
                "RevenueFromContractWithCustomerIncludingAssessedTax",
                "RevenuesNetOfInterestExpense"],                 # banks and brokers
    "net_interest_income": ["InterestIncomeExpenseNet", "InterestIncomeExpenseAfterProvisionForLoanLoss"],
    "operating_income": ["OperatingIncomeLoss"],
    "pretax_income": ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                      "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"],
    "net_income": ["NetIncomeLoss"],                 # attributable to the parent's shareholders
    "net_income_incl_nci": ["ProfitLoss"],           # incl. noncontrolling interests
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasicAndDiluted"],
    "interest_expense": ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt"],
    "depreciation": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization",
                     "DepreciationAmortizationAndAccretionNet"],
    "ocf": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
}
INSTANT_TAGS = {
    "total_assets": ["Assets"],
    "total_equity": ["StockholdersEquity"],
    "current_assets": ["AssetsCurrent"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "inventory": ["InventoryNet"],
    "cash": ["CashAndCashEquivalentsAtCarryingValue"],
}
# Total debt = sum of whichever of these the company reports
DEBT_PARTS = [["LongTermDebtNoncurrent"], ["LongTermDebtCurrent", "DebtCurrent"], ["ShortTermBorrowings"],
              ["CommercialPaper"]]
DEBT_TOTAL_FALLBACK = ["LongTermDebt"]

ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT"}


class SecClient:
    def __init__(self, cfg: dict, cache: FileCache):
        s = cfg.get("sec", {})
        self.ua = s.get("user_agent", "finspider research tool (personal, non-commercial)")
        self.ttl = float(s.get("ttl_hours", 168)) * 3600
        self.timeout = float(s.get("timeout_seconds", 30))
        self.cache = cache
        self._last = 0.0

    def get_json(self, url: str) -> Optional[dict]:
        hit = self.cache.get(f"sec:{url}", self.ttl)
        if hit is not None:
            return hit
        for attempt in range(3):
            gap = time.time() - self._last
            if gap < 0.25:                      # SEC allows 10 requests/second; stay well under
                time.sleep(0.25 - gap)
            self._last = time.time()
            try:
                r = requests.get(url, headers={"User-Agent": self.ua, "Accept-Encoding": "gzip, deflate"},
                                 timeout=self.timeout)
            except requests.RequestException as e:
                log.debug("SEC request failed (%s)", e)
                time.sleep(2 ** attempt)
                continue
            if r.status_code == 200:
                data = r.json()
                self.cache.set(f"sec:{url}", data)
                return data
            if r.status_code == 404:
                return None
            log.debug("SEC HTTP %s for %s", r.status_code, url)
            time.sleep(2 ** attempt * 2)
        return None

    def cik_for(self, ticker: str) -> Optional[tuple[int, str]]:
        data = self.get_json(TICKERS_URL)
        if not data:
            return None
        want = ticker.upper().replace(".", "-")
        for row in data.values():
            if str(row.get("ticker", "")).upper() == want:
                return int(row["cik_str"]), row.get("title", "")
        return None


def is_us_ticker(ticker: str) -> bool:
    """Yahoo uses a suffix for non-US listings (INFY.NS); US tickers have none (BRK-B is fine)."""
    return re.fullmatch(r"[A-Z][A-Z0-9\-]{0,9}", ticker.upper()) is not None


def _days(start: str, end: str) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def _pick(units: dict, duration: bool) -> dict[str, dict]:
    """Annual 10-K facts keyed by period end; for each end keep the most recently filed value
    (later filings restate earlier years consistently)."""
    out: dict[str, dict] = {}
    for unit, facts in units.items():
        if unit not in ("USD", "USD/shares"):
            continue
        for f in facts:
            if f.get("form") not in ANNUAL_FORMS:
                continue
            if duration:
                if "start" not in f or not 350 <= _days(f["start"], f["end"]) <= 380:
                    continue
            elif f.get("fp") != "FY":
                continue
            prev = out.get(f["end"])
            if prev is None or f.get("filed", "") > prev.get("filed", ""):
                out[f["end"]] = f
    return out


def _filing_url(cik: int, accn: str) -> str:
    return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/"


def _citation(cik: int, company: str, f: dict, tag: str) -> dict[str, Any]:
    return {
        "source": "SEC",
        # a 10-K also reports earlier years for comparison, so name the filing and the period separately
        "doc": f"{company} Form {f.get('form', '10-K')} filed {f.get('filed', '?')} (figure for fiscal year ended {f['end']})",
        "url": _filing_url(cik, f["accn"]),
        "tag": f"us-gaap:{tag}",
        "status": "official",
    }


def parse_companyfacts(facts: dict, cik: int, company: str) -> dict[str, Any]:
    """Company facts JSON -> canonical annual frame (USD) + per-value citations + fiscal year ends."""
    gaap = (facts.get("facts") or {}).get("us-gaap") or {}
    series: dict[str, dict[int, float]] = {f: {} for f in ANNUAL_FIELDS}
    prov: dict[str, dict[int, dict]] = {}
    fy_end: dict[int, pd.Timestamp] = {}

    def take(field: str, tags: list[str], duration: bool):
        for tag in tags:                                    # earlier tags win per year
            if tag not in gaap:
                continue
            for end, f in _pick(gaap[tag]["units"], duration).items():
                year = date.fromisoformat(end).year
                if year in series[field]:
                    continue
                series[field][year] = float(f["val"])
                prov.setdefault(field, {})[year] = _citation(cik, company, f, tag)
                if field in ("revenue", "net_income"):
                    fy_end.setdefault(year, pd.Timestamp(end))

    for field, tags in DURATION_TAGS.items():
        take(field, tags, True)
    for field, tags in INSTANT_TAGS.items():
        take(field, tags, False)

    # total debt: sum of reported parts per year
    parts = []
    for options in DEBT_PARTS:
        for tag in options:
            if tag in gaap:
                parts.append((tag, _pick(gaap[tag]["units"], False)))
                break
    if not parts and DEBT_TOTAL_FALLBACK[0] in gaap:
        parts.append((DEBT_TOTAL_FALLBACK[0], _pick(gaap[DEBT_TOTAL_FALLBACK[0]]["units"], False)))
    by_year: dict[int, list] = {}
    for tag, picked in parts:
        for end, f in picked.items():
            by_year.setdefault(date.fromisoformat(end).year, []).append((tag, f))
    for year, items in by_year.items():
        series["total_debt"][year] = float(sum(f["val"] for _, f in items))
        tag, f = items[0]
        c = _citation(cik, company, f, "+".join(t for t, _ in items))
        prov.setdefault("total_debt", {})[year] = c

    if "capex" in series:
        series["capex"] = {y: abs(v) for y, v in series["capex"].items()}

    annual = pd.DataFrame({f: pd.Series(v, dtype=float) for f, v in series.items()})
    annual = annual.reindex(columns=ANNUAL_FIELDS).sort_index()
    annual.index = annual.index.astype(int)
    annual.index.name = "year"
    # keep only fiscal years that have an income statement
    if fy_end:
        annual = annual.loc[[y for y in annual.index if y in fy_end]]
    return {"annual": annual, "provenance": prov, "fy_end": fy_end}


def fetch(ticker: str, cfg: dict, cache: FileCache) -> Optional[dict[str, Any]]:
    client = SecClient(cfg, cache)
    found = client.cik_for(ticker)
    if not found:
        return None
    cik, title = found
    facts = client.get_json(FACTS_URL.format(cik=cik))
    if not facts:
        return None
    company = facts.get("entityName") or title
    parsed = parse_companyfacts(facts, cik, company)
    parsed["cik"] = cik
    parsed["company"] = company
    return parsed if not parsed["annual"].empty else None
