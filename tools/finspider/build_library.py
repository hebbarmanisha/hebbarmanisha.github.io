#!/usr/bin/env python3
"""Build the searchable company library for the dashboard.

Runs finspider on every company in the configured indices (Nifty 50, S&P 100) and writes:
  <out>/index.json            search index: name, ticker, verdict, score, file, update date
  <out>/reports/<TICKER>.json  the widget data for each company (compact JSON)
Companies that fail, or whose figures can't be verified, are listed in index.json under
"skipped" with the reason. Run weekly by a GitHub Action; can also be run by hand:

    python build_library.py --out ../../library
    python build_library.py --out library --only NVDA ASIANPAINT.NS
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import logging
import re
import sys
import time
import warnings
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import pandas as pd      # noqa: E402
import requests          # noqa: E402

from finspider_core.cache import FileCache        # noqa: E402
from finspider_core.config import load_config     # noqa: E402
from finspider_core.pipeline import analyze       # noqa: E402

log = logging.getLogger("library")
UA = {"User-Agent": "finspider research tool (personal, non-commercial)"}
SNAPSHOT = HERE / "constituents.json"   # last good list, used if Wikipedia is unreachable

SOURCES = {
    "sp100": ("https://en.wikipedia.org/wiki/S%26P_100", "S&P 100"),
    "nifty50": ("https://en.wikipedia.org/wiki/NIFTY_50", "Nifty 50"),
}


def _clean_name(s: str) -> str:
    return re.sub(r"\s*\[.*?\]", "", str(s)).strip()


def fetch_constituents(indices: list[str]) -> list[dict]:
    """Current members from Wikipedia's index tables; falls back to the saved snapshot."""
    out: list[dict] = []
    for key in indices:
        url, label = SOURCES[key]
        try:
            r = requests.get(url, headers=UA, timeout=30)
            r.raise_for_status()
            table = next(t for t in pd.read_html(io.StringIO(r.text))
                         if any("Symbol" in str(c) for c in t.columns))
            sym_col = next(c for c in table.columns if "Symbol" in str(c))
            name_col = next(c for c in table.columns if "name" in str(c).lower())
            for _, row in table.iterrows():
                sym = str(row[sym_col]).strip()
                if not sym or sym.lower() == "nan":
                    continue
                ticker = f"{sym}.NS" if key.startswith("nifty") else sym.replace(".", "-")
                out.append({"ticker": ticker, "name": _clean_name(row[name_col]), "index": label})
        except Exception as e:
            log.warning("Could not fetch %s list (%s); using snapshot", label, e)
            if SNAPSHOT.exists():
                out += [c for c in json.loads(SNAPSHOT.read_text(encoding="utf-8")) if c["index"] == label]
    # one entry per company: drop duplicate tickers and extra share classes (GOOG/GOOGL)
    seen, uniq = set(), []
    for c in out:
        key = re.sub(r"\(?\bclass [a-z]\b\)?", "", c["name"].lower()).strip(" ,.")
        if c["ticker"] in seen or key in seen:
            continue
        seen.update({c["ticker"], key})
        uniq.append(c)
    return uniq


def verification_ok(spider: dict, cfg: dict) -> tuple[bool, str]:
    """Indian listings (Screener primary) must be confirmed by a second source."""
    v = spider.get("verification") or {}
    if v.get("primary") == "SEC EDGAR":
        return True, ""
    ticker = (spider.get("company") or {}).get("ticker", "")
    if "." not in ticker:
        return False, "no annual 10-K history on SEC EDGAR for this ticker"
    lib = cfg.get("library", {})
    if v.get("mismatch", 0) > int(lib.get("max_mismatches", 2)):
        return False, f"{v['mismatch']} figures differ between {v.get('primary')} and Yahoo Finance by more than {v.get('tolerance_pct')}%"
    if v.get("verified", 0) < int(lib.get("min_verified", 8)):
        return False, f"only {v.get('verified', 0)} figures could be cross-checked against a second source"
    return True, ""


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Build the finspider company library")
    p.add_argument("--out", required=True, help="Library folder (index.json + reports/)")
    p.add_argument("--config", default=str(HERE / "config.yaml"))
    p.add_argument("--only", nargs="*", help="Only these tickers (keeps the rest of the index)")
    p.add_argument("--limit", type=int, help="Only the first N companies (testing)")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(message)s")
    warnings.filterwarnings("ignore")
    for noisy in ("yfinance", "urllib3", "peewee", "finspider_core"):
        logging.getLogger(noisy).setLevel(logging.ERROR)

    cfg = load_config(a.config)
    cache = FileCache(HERE / cfg["cache"]["dir"])
    out = Path(a.out)
    (out / "reports").mkdir(parents=True, exist_ok=True)
    index_path = out / "index.json"
    old = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {"companies": [], "skipped": []}
    old_by = {c["t"]: c for c in old.get("companies", [])}

    members = fetch_constituents(cfg.get("library", {}).get("indices", ["nifty50", "sp100"]))
    if members:
        SNAPSHOT.write_text(json.dumps(members, indent=1), encoding="utf-8")
    if a.only:
        want = {t.upper() for t in a.only}
        members = [m for m in members if m["ticker"].upper() in want] + \
                  [{"ticker": t, "name": t, "index": "Manual"} for t in want if t not in {m["ticker"].upper() for m in members}]
    if a.limit:
        members = members[: a.limit]

    today = dt.date.today()
    companies = {t: c for t, c in old_by.items()} if a.only else {}
    skipped = [s for s in old.get("skipped", []) if a.only and s["t"] not in {m["ticker"] for m in members}]
    keep_days = int(cfg.get("library", {}).get("keep_stale_days", 35))
    t0 = time.time()

    def write_index(final: bool):
        index = {
            "updated": today.isoformat(),
            "complete": final,
            "indices": sorted({c["x"] for c in companies.values()}),
            "companies": sorted(companies.values(), key=lambda c: c["n"].lower()),
            "skipped": sorted(skipped, key=lambda s: s["n"].lower()),
        }
        tmp = index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
        tmp.replace(index_path)

    for i, m in enumerate(members, 1):
        tk = m["ticker"]
        try:
            res = analyze(tk, cfg, cache, m["name"])
            spider = res.spider
            ok, why = verification_ok(spider, cfg)
            if not ok:
                raise ValueError(why)
            fname = re.sub(r"[^A-Za-z0-9_-]", "_", tk) + ".json"
            (out / "reports" / fname).write_text(json.dumps(spider, separators=(",", ":"), ensure_ascii=False),
                                                 encoding="utf-8")
            companies[tk] = {
                "t": tk, "n": res.company.name, "x": m["index"], "v": spider["verdict"],
                "s": round(spider["overall"], 1) if spider.get("overall") is not None else None,
                "f": f"reports/{fname}", "d": today.isoformat(),
                "src": (spider.get("verification") or {}).get("primary", ""),
            }
            log.info("[%d/%d] %-14s %-18s %s", i, len(members), tk, spider["verdict"], spider.get("overall"))
        except Exception as e:
            prev = old_by.get(tk)
            fresh_enough = prev and (today - dt.date.fromisoformat(prev["d"])).days <= keep_days
            if prev and fresh_enough and not isinstance(e, ValueError):
                companies[tk] = dict(prev, stale=True)       # temporary failure: keep last week's report
                log.info("[%d/%d] %-14s kept previous report (%s)", i, len(members), tk, e)
            else:
                skipped.append({"t": tk, "n": m["name"], "x": m["index"], "why": str(e)[:200]})
                log.info("[%d/%d] %-14s SKIPPED: %s", i, len(members), tk, str(e)[:120])
        write_index(final=False)          # progress survives an interrupted run

    # drop report files for companies no longer in the index
    keep = {Path(c["f"]).name for c in companies.values()}
    for f in (out / "reports").glob("*.json"):
        if f.name not in keep:
            f.unlink()
    write_index(final=True)
    log.info("Done in %.0fs: %d companies, %d skipped", time.time() - t0, len(companies), len(skipped))
    return 0


if __name__ == "__main__":
    sys.exit(main())
