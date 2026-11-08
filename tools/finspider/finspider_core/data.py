"""Assemble a CompanyData with a citation and verification status for every figure.

Source policy (see config.yaml -> verification):
  US listings     primary = SEC EDGAR 10-K filings (official), cross-checked against Yahoo Finance
  Indian listings primary = Screener.in (compiled from exchange filings), cross-checked against Yahoo
  everything else primary = Yahoo Finance (single source)
Gaps in the primary source are filled from Yahoo and labelled single-source.
"""
from __future__ import annotations

import logging

import pandas as pd

from .cache import FileCache
from .errors import DataUnavailable
from .model import CompanyData
from .sources import merge as merge_mod
from .sources import screener, sec, yahoo

log = logging.getLogger(__name__)

KEY_FIELDS = ["revenue", "net_income", "total_equity"]


def _yahoo_cite(ticker: str) -> dict:
    return {"source": "Yahoo Finance", "doc": "Yahoo Finance annual financial statements",
            "url": f"https://finance.yahoo.com/quote/{ticker}/financials/"}


def load_company(ticker: str, cfg: dict, cache: FileCache, display_name: str = "") -> CompanyData:
    dcfg = cfg["data"]
    vcfg = cfg.get("verification", {})
    tol = float(vcfg.get("tolerance_pct", 2.0))
    compare = list(vcfg.get("compare_fields", []))
    yf_ttl = float(cfg["cache"]["yfinance_ttl_hours"])

    # Yahoo is optional when an official/primary source exists (cloud servers are often blocked).
    yahoo_error = None
    try:
        raw = yahoo.fetch_raw(ticker, cache, yf_ttl)
    except Exception as e:
        yahoo_error = str(e)
        raw = {"info": {}}
    norm = yahoo.normalise(raw, cache, yf_ttl)
    info = raw.get("info") or {}
    warnings = list(norm["warnings"]) if not yahoo_error else []
    if yahoo_error:
        warnings.append("Yahoo Finance was unavailable: no cross-check, share price or valuation ratios.")
    ydf = norm["annual"]
    fy_end = dict(norm["fy_end"])
    ycite = _yahoo_cite(ticker)

    primary, primary_cite, primary_prov, primary_name = ydf, dict(ycite), None, "Yahoo Finance"
    npa, screener_url, sec_meta, source_name = None, None, None, ""

    # ---- US: official SEC filings
    if sec.is_us_ticker(ticker) and cfg.get("sec", {}).get("enabled", True):
        try:
            got = sec.fetch(ticker, cfg, cache)
            if got and got["annual"]["revenue"].notna().sum() >= 4:
                primary, primary_prov, primary_name = got["annual"], got["provenance"], "SEC EDGAR"
                primary_cite = {"source": "SEC", "doc": "SEC EDGAR filing", "url": "", "status": "official"}
                sec_meta = {"cik": got["cik"], "company": got["company"]}
                source_name = got["company"]
                for y, ts in got["fy_end"].items():
                    fy_end[y] = ts
            elif got is None:
                warnings.append("No SEC filings found for this ticker; using Yahoo Finance only.")
        except Exception as e:                          # network etc. - fall back, but say so
            log.warning("SEC fetch failed: %s", e)
            warnings.append(f"SEC EDGAR unavailable ({e}); using Yahoo Finance only.")

    # ---- India: Screener (exchange filings), cross-checked with Yahoo
    sym = screener.screener_symbol(ticker)
    if sym and cfg["screener"].get("enabled", True):
        try:
            client = screener.ScreenerClient(cfg, cache)
            html, screener_url = client.fetch_company(sym)
            if html:
                parsed = screener.parse_company(html)
                npa = parsed["quarterly_npa"]
                if parsed["is_bank"] and (npa is None or npa.empty) and "/consolidated/" in screener_url:
                    standalone = client.get(screener_url.replace("consolidated/", ""))
                    if standalone:
                        npa = screener.parse_company(standalone)["quarterly_npa"]
                        if npa is not None and not npa.empty:
                            warnings.append("Gross/Net NPA % taken from Screener's standalone (bank-only) figures.")
                # profit attributable to shareholders = Net Profit + (negative) minority share
                if parsed.get("company_id"):
                    sched = client.fetch_schedule(parsed["company_id"], "Net Profit", "/consolidated/" in screener_url)
                    if not screener.apply_minority_split(parsed["annual"], sched, parsed["fy_month"]):
                        warnings.append("Screener's minority-interest split was unavailable; net profit may "
                                        "include minority interests.")
                if parsed["annual"]["revenue"].notna().sum() >= 4:
                    primary, primary_prov, primary_name = parsed["annual"], None, "Screener.in"
                    source_name = parsed.get("name") or source_name
                    primary_cite = {"source": "Screener.in",
                                    "doc": "Screener.in financials (compiled from company filings to BSE/NSE)",
                                    "url": screener_url}
                    for y, ts in parsed["fy_end"].items():
                        fy_end[y] = ts
            else:
                warnings.append(f"Screener.in had no usable page for {sym}; using Yahoo Finance only.")
        except Exception as e:  # scraping is best-effort; never fatal
            log.warning("Screener.in failed: %s", e)
            warnings.append(f"Screener.in unavailable ({e}); using Yahoo Finance only.")

    if primary_name == "Yahoo Finance" and yahoo_error:
        raise DataUnavailable(f"No data source could provide statements for {ticker} ({yahoo_error}).")
    if primary_name == "Yahoo Finance":
        annual, prov = merge_mod.combine(ydf, dict(ycite, status="single"), None, None, None,
                                         [], tol, int(dcfg["history_years"]))
    else:
        annual, prov = merge_mod.combine(primary, primary_cite, primary_prov, ydf, ycite,
                                         compare, tol, int(dcfg["history_years"]))
    if annual.empty or all(annual.get(f, pd.Series(dtype=float)).isna().all() for f in KEY_FIELDS):
        raise DataUnavailable(f"No usable financial statements found for {ticker}.")

    yrs = int(annual["revenue"].notna().sum())
    if yrs < 4:
        warnings.append(f"Only {yrs} years of revenue history were found (4+ wanted).")
    counts = merge_mod.summary(prov)
    if counts["mismatch"]:
        warnings.append(f"{counts['mismatch']} figure(s) differ between {primary_name} and Yahoo Finance by more "
                        f"than {tol:g}%; they are shown but not used in scoring.")

    prices = yahoo.monthly_prices(raw, norm["price_divisor"])
    price = info.get("currentPrice") or info.get("regularMarketPrice")
    if price:
        price = float(price) / norm["price_divisor"]
    elif not prices.empty:
        price = float(prices.iloc[-1])
    shares = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")

    manual = (cfg.get("manual_inputs") or {}).get(ticker.upper(), {}) or {}
    if manual:
        warnings.append(f"Manual inputs from config.yaml used: {', '.join(manual)}.")

    sources = {f: by_year[max(by_year)]["source"] for f, by_year in prov.items() if by_year}
    default_cur = "USD" if sec_meta else "INR" if sym else ""
    return CompanyData(
        ticker=ticker,
        name=info.get("longName") or info.get("shortName") or display_name or source_name or ticker,
        currency=norm["price_currency"] or default_cur,
        price=float(price) if price else None,
        shares=float(shares) if shares else None,
        info=info,
        annual=annual,
        fy_end={y: fy_end[y] for y in annual.index if y in fy_end},
        prices=prices,
        splits=yahoo.splits_series(raw),
        quarterly_npa=npa,
        sources=sources,
        warnings=warnings,
        screener_url=screener_url,
        trailing_pe=float(info["trailingPE"]) if info.get("trailingPE") else None,
        manual=manual,
        provenance=prov,
        primary_source=primary_name,
        sec=sec_meta,
    )
