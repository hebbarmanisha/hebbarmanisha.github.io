"""Screener.in fallback: polite fetching (robots.txt, delay, retries, cache) + HTML parsing.

Screener reports Indian companies in INR crores (1 crore = 1e7). The parser converts
money rows to absolute INR so they line up with the yfinance data.
"""
from __future__ import annotations

import logging
import random
import re
import time
from collections import Counter
from typing import Any, Optional
from urllib import robotparser
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

from ..cache import FileCache
from ..model import ANNUAL_FIELDS

log = logging.getLogger(__name__)

CRORE = 1e7
_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


class ScreenerClient:
    def __init__(self, cfg: dict, cache: FileCache):
        s = cfg["screener"]
        self.base = s["base_url"].rstrip("/")
        self.delay = float(s.get("min_delay_seconds", 3))
        self.timeout = float(s.get("timeout_seconds", 20))
        self.retries = int(s.get("max_retries", 3))
        self.ttl = float(cfg["cache"]["screener_ttl_hours"]) * 3600
        self.prefer_consolidated = bool(s.get("prefer_consolidated", True))
        self.cache = cache
        self.session = requests.Session()
        self.session.headers["User-Agent"] = s.get("user_agent", "finspider/0.1")
        self._robots: Optional[robotparser.RobotFileParser] = None
        self._last_request = 0.0

    # ---- politeness ----
    def _wait(self):
        gap = time.time() - self._last_request
        target = self.delay + random.uniform(0, 1)
        if gap < target:
            time.sleep(target - gap)
        self._last_request = time.time()

    def _robots_ok(self, url: str) -> bool:
        if self._robots is None:
            robots_url = f"{self.base}/robots.txt"
            text = self.cache.get(f"robots:{robots_url}", self.ttl)
            if text is None:
                self._wait()
                try:
                    r = self.session.get(robots_url, timeout=self.timeout)
                    text = r.text if r.status_code == 200 else ""
                except requests.RequestException as e:
                    log.warning("Could not read %s (%s); not scraping to be safe.", robots_url, e)
                    return False
                self.cache.set(f"robots:{robots_url}", text)
            rp = robotparser.RobotFileParser()
            rp.parse(text.splitlines())
            self._robots = rp
        return self._robots.can_fetch(self.session.headers["User-Agent"], url)

    def get(self, url: str) -> Optional[str]:
        cached = self.cache.get(f"screener:{url}", self.ttl)
        if cached is not None:
            return cached
        if not self._robots_ok(url):
            log.warning("robots.txt disallows %s; skipping.", urlparse(url).path)
            return None
        for attempt in range(self.retries):
            self._wait()
            try:
                r = self.session.get(url, timeout=self.timeout)
            except requests.RequestException as e:
                log.debug("Screener request failed (%s), attempt %d", e, attempt + 1)
                time.sleep(2 ** attempt * 2)
                continue
            if r.status_code == 200:
                self.cache.set(f"screener:{url}", r.text)
                return r.text
            if r.status_code == 404:
                return None
            if r.status_code in (429, 500, 502, 503, 504):
                retry_after = r.headers.get("Retry-After", "")
                wait = int(retry_after) if retry_after.isdigit() else 2 ** attempt * 5
                log.debug("Screener %s, backing off %ss", r.status_code, wait)
                time.sleep(min(wait, 60))
                continue
            log.debug("Screener returned HTTP %s for %s", r.status_code, url)
            return None
        return None

    def fetch_schedule(self, company_id: str, parent: str, consolidated: bool) -> Optional[dict]:
        """The breakdown behind an expandable row (e.g. 'Net Profit' -> minority share)."""
        from urllib.parse import quote
        url = (f"{self.base}/api/company/{company_id}/schedules/?parent={quote(parent)}&section=profit-loss"
               + ("&consolidated=" if consolidated else ""))
        text = self.get(url)
        if not text:
            return None
        try:
            import json
            return json.loads(text)
        except ValueError:
            return None

    def fetch_company(self, symbol: str) -> tuple[Optional[str], Optional[str]]:
        """Return (html, url). Tries consolidated first, then standalone."""
        paths = [f"/company/{symbol}/consolidated/", f"/company/{symbol}/"]
        if not self.prefer_consolidated:
            paths.reverse()
        for p in paths:
            url = self.base + p
            html = self.get(url)
            if html and _has_annual_data(html):
                return html, url
        return None, None


def screener_symbol(ticker: str) -> Optional[str]:
    """INFY.NS -> INFY, 500209.BO -> 500209; None for non-Indian tickers."""
    m = re.fullmatch(r"(.+)\.(NS|BO)", ticker.upper())
    return m.group(1) if m else None


# ---------------- parsing ----------------
def _num(text: str) -> float:
    t = text.replace(",", "").replace("%", "").replace("₹", "").strip()
    if t in ("", "-", "--"):
        return np.nan
    try:
        return float(t)
    except ValueError:
        return np.nan


def _clean_label(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return re.sub(r"\s*\+$", "", t).strip()


def parse_table(section) -> pd.DataFrame:
    """Section -> DataFrame (rows = line items, columns = header labels like 'Mar 2024')."""
    if section is None:
        return pd.DataFrame()
    table = section.find("table")
    if table is None or table.find("thead") is None:
        return pd.DataFrame()
    headers = [th.get_text(" ", strip=True) for th in table.find("thead").find_all("th")][1:]
    rows = {}
    for tr in table.find("tbody").find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        label = _clean_label(tds[0].get_text(" ", strip=True))
        vals = [_num(td.get_text(" ", strip=True)) for td in tds[1:]]
        if label and label not in rows:
            rows[label] = vals[: len(headers)] + [np.nan] * (len(headers) - len(vals))
    return pd.DataFrame.from_dict(rows, orient="index", columns=headers)


def _period_end(label: str) -> Optional[pd.Timestamp]:
    m = re.fullmatch(r"([A-Z][a-z]{2}) (\d{4})", label.strip())
    if not m or m.group(1) not in _MONTHS:
        return None
    return pd.Timestamp(year=int(m.group(2)), month=_MONTHS[m.group(1)], day=1) + pd.offsets.MonthEnd(0)


def annual_columns(df: pd.DataFrame) -> dict[str, pd.Timestamp]:
    """Keep 'Mon YYYY' columns whose month is the fiscal year-end month (drops TTM / half-years)."""
    ends = {c: _period_end(c) for c in df.columns}
    ends = {c: e for c, e in ends.items() if e is not None}
    if not ends:
        return {}
    fy_month = Counter(e.month for e in ends.values()).most_common(1)[0][0]
    return {c: e for c, e in ends.items() if e.month == fy_month}


def _row(df: pd.DataFrame, *names: str) -> Optional[pd.Series]:
    for n in names:
        if n in df.index:
            return df.loc[n]
    return None


def _has_annual_data(html: str) -> bool:
    soup = BeautifulSoup(html, "html.parser")
    pl = parse_table(soup.find("section", id="profit-loss"))
    return not pl.empty and pl.notna().any().any()


def parse_company(html: str) -> dict[str, Any]:
    """Parse a Screener company page into canonical annual data + bank NPA quarters."""
    soup = BeautifulSoup(html, "html.parser")
    pl = parse_table(soup.find("section", id="profit-loss"))
    bs = parse_table(soup.find("section", id="balance-sheet"))
    cf = parse_table(soup.find("section", id="cash-flow"))
    qt = parse_table(soup.find("section", id="quarters"))

    series: dict[str, dict[int, float]] = {f: {} for f in ANNUAL_FIELDS}
    fy_end: dict[int, pd.Timestamp] = {}

    def put(field: str, df: pd.DataFrame, row: Optional[pd.Series], scale: float = CRORE):
        if row is None:
            return
        for col, end in annual_columns(df).items():
            v = row.get(col, np.nan)
            if pd.notna(v):
                series[field][end.year] = float(v) * scale
                fy_end.setdefault(end.year, end)

    is_bank = _row(pl, "Financing Profit") is not None or _row(bs, "Deposits") is not None

    revenue = _row(pl, "Sales", "Revenue")
    put("revenue", pl, revenue)
    put("interest_expense", pl, _row(pl, "Interest"))
    put("depreciation", pl, _row(pl, "Depreciation"))
    put("pretax_income", pl, _row(pl, "Profit before tax"))
    put("net_income", pl, _row(pl, "Net Profit"))
    put("eps", pl, _row(pl, "EPS in Rs"), scale=1.0)

    op = _row(pl, "Operating Profit")
    dep = _row(pl, "Depreciation")
    if op is not None and not is_bank:
        put("operating_income", pl, op - (dep if dep is not None else 0))

    eq_cap, reserves = _row(bs, "Equity Capital", "Share Capital"), _row(bs, "Reserves")
    if eq_cap is not None and reserves is not None:
        put("total_equity", bs, eq_cap.fillna(0) + reserves.fillna(0))
    put("total_debt", bs, _row(bs, "Borrowings", "Borrowing"))
    put("deposits", bs, _row(bs, "Deposits"))
    put("total_assets", bs, _row(bs, "Total Assets"))

    put("ocf", cf, _row(cf, "Cash from Operating Activity"))
    put("fcf", cf, _row(cf, "Free Cash Flow"))

    # Derived fields
    for y in list(series["pretax_income"]):
        if not is_bank and y in series["interest_expense"]:
            series["ebit"][y] = series["pretax_income"][y] + series["interest_expense"][y]
        if is_bank and y in series["revenue"] and y in series["interest_expense"]:
            series["net_interest_income"][y] = series["revenue"][y] - series["interest_expense"][y]

    annual = pd.DataFrame({f: pd.Series(v, dtype=float) for f, v in series.items()})
    annual = annual.reindex(columns=ANNUAL_FIELDS).sort_index()
    annual.index = annual.index.astype(int)
    annual.index.name = "year"

    npa = None
    g, n = _row(qt, "Gross NPA %"), _row(qt, "Net NPA %")
    if g is not None or n is not None:
        cols = [c for c in qt.columns if _period_end(c) is not None]
        npa = pd.DataFrame({
            "gnpa_pct": [g.get(c, np.nan) if g is not None else np.nan for c in cols],
            "nnpa_pct": [n.get(c, np.nan) if n is not None else np.nan for c in cols],
        }, index=cols).dropna(how="all")

    h1 = soup.find("h1")
    name = h1.get_text(" ", strip=True) if h1 else ""
    cid_el = soup.find(attrs={"data-company-id": True})
    return {"annual": annual, "fy_end": fy_end, "quarterly_npa": npa, "is_bank": is_bank, "name": name,
            "company_id": cid_el["data-company-id"] if cid_el else None,
            "fy_month": Counter(e.month for e in fy_end.values()).most_common(1)[0][0] if fy_end else 3}


def apply_minority_split(annual: pd.DataFrame, schedule: Optional[dict], fy_month: int) -> bool:
    """Screener's 'Net Profit' includes minority interests. Keep it as net_income_incl_nci and set
    net_income to the shareholders' share (Net Profit + 'Minority share', which is negative).
    Returns True if the split was applied."""
    annual["net_income_incl_nci"] = annual["net_income"]
    rows = (schedule or {}).get("Minority share")
    if not rows:
        return False
    minority = {}
    for label, val in rows.items():
        end = _period_end(label)
        if end is not None and end.month == fy_month:
            v = _num(val)
            if v == v:
                minority[end.year] = v * CRORE
    for y in annual.index:
        if y in minority and pd.notna(annual.at[y, "net_income_incl_nci"]):
            annual.at[y, "net_income"] = annual.at[y, "net_income_incl_nci"] + minority[y]
    return True
