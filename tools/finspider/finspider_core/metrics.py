"""Turn normalised annual data into the metric set used for scoring and the report."""
from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np
import pandas as pd

from . import ratios as R
from .model import CompanyData, Metric
from .sources.merge import worst

# Which financial statement each canonical field lives on (drives the widget's statement sheet).
STATEMENT_OF = {
    "revenue": "income", "operating_income": "income", "ebit": "income", "pretax_income": "income",
    "interest_expense": "income", "depreciation": "income", "net_income": "income", "eps": "income",
    "net_income_incl_nci": "income",
    "net_interest_income": "income",
    "total_assets": "balance", "current_assets": "balance", "inventory": "balance", "cash": "balance",
    "current_liabilities": "balance", "total_debt": "balance", "total_equity": "balance", "deposits": "balance",
    "ocf": "cashflow", "capex": "cashflow", "fcf": "cashflow",
}

LABELS = {
    "current_ratio": ("Current ratio", "x"),
    "quick_ratio": ("Quick ratio", "x"),
    "debt_to_equity": ("Debt / equity", "x"),
    "interest_coverage": ("Interest coverage", "x"),
    "roe": ("Return on equity (ROE)", "%"),
    "roce": ("Return on capital employed (ROCE)", "%"),
    "net_margin": ("Net profit margin", "%"),
    "operating_margin": ("Operating margin", "%"),
    "revenue_cagr": ("Revenue CAGR", "%"),
    "profit_cagr": ("Net profit CAGR", "%"),
    "eps_cagr": ("EPS CAGR", "%"),
    "ocf_to_net_profit": ("Operating cash flow / net profit", "x"),
    "fcf_positive_years": ("Years with positive free cash flow", "count"),
    "fcf_margin": ("Free cash flow margin", "%"),
    "free_cash_flow": ("Free cash flow (latest year)", "money"),
    "pe": ("Price / earnings (P/E)", "x"),
    "pb": ("Price / book (P/B)", "x"),
    "peg": ("PEG ratio", "x"),
    "pe_vs_avg": ("P/E vs its own average", "%"),
    "pb_vs_avg": ("P/B vs its own average", "%"),
    "peg_vs_avg": ("PEG vs its own average", "%"),
    "nim": ("Net interest margin (NIM)", "%"),
    "roa": ("Return on assets (ROA)", "%"),
    "gnpa": ("Gross NPA", "%"),
    "nnpa": ("Net NPA", "%"),
    "car": ("Capital adequacy ratio (CAR)", "%"),
}


def _v(x) -> Optional[float]:
    if x is None:
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _latest(history: dict[int, Optional[float]]) -> tuple[Optional[int], Optional[float]]:
    for y in sorted(history, reverse=True):
        v = history[y]
        if v is not None and not (isinstance(v, float) and math.isnan(v)):
            return y, v
    return None, None


def _clean(history: dict[int, Optional[float]]) -> dict[int, float]:
    return {y: v for y, v in history.items() if v is not None and not math.isnan(v)}


def price_at(prices: pd.Series, when: pd.Timestamp) -> Optional[float]:
    if prices is None or prices.empty or when is None:
        return None
    # Monthly bars are dated the 1st and hold that month's closing price, so the bar
    # dated on/before the fiscal year-end is the year-end month itself.
    s = prices[prices.index <= when].dropna()
    return float(s.iloc[-1]) if not s.empty else None


def split_factor_after(splits: pd.Series, when: pd.Timestamp) -> float:
    if splits is None or splits.empty or when is None:
        return 1.0
    after = splits[splits.index > when]
    return float(np.prod(after.values)) if not after.empty else 1.0


def adjusted_shares(c: CompanyData) -> dict[int, float]:
    """Share count for each year on today's split/bonus basis.

    Implied shares (net profit / EPS) come from the filing. Some sources already restate
    EPS for later splits and some don't, so we try both and keep whichever is closer to
    today's share count.
    """
    out = {}
    a = c.annual
    for y in a.index:
        ni, eps = _v(a.at[y, "net_income"]), _v(a.at[y, "eps"])
        implied = ni / eps if ni and eps and eps > 0 and ni > 0 else None
        if implied is None:
            if c.shares:
                out[y] = c.shares
            continue
        factor = split_factor_after(c.splits, c.fy_end.get(y))
        options = [implied, implied * factor]
        if c.shares:
            out[y] = min(options, key=lambda s: abs(math.log(s / c.shares)))
        else:
            out[y] = implied * factor
    return out


def window_cagr(history: dict[int, float], years: int) -> tuple[Optional[float], int]:
    """CAGR over `years`, or over the longest shorter span available. Returns (cagr, span)."""
    h = _clean(history)
    if len(h) < 2:
        return None, 0
    end_y = max(h)
    starts = [y for y in h if end_y - years <= y < end_y]
    if not starts:
        return None, 0
    start_y = min(starts)
    span = end_y - start_y
    return R.cagr(h[start_y], h[end_y], span), span


def _trend(history: dict[int, float], higher_better: Optional[bool]) -> str:
    h = _clean(history)
    if len(h) < 3 or higher_better is None:
        return ""
    ys = sorted(h)
    last = ys[-1]
    base_years = [y for y in ys if y <= last - 3] or [ys[0]]
    base, now = h[base_years[-1]], h[last]
    if base == 0:
        return ""
    change = (now - base) / abs(base)
    if abs(change) < 0.05:
        return "stable"
    up = change > 0
    return "improving" if up == higher_better else "worsening"


def compute(c: CompanyData, cfg: dict, profile: str) -> tuple[dict[str, Metric], dict[str, Any]]:
    a = c.annual
    years = list(a.index)
    n_cagr = int(cfg["data"]["cagr_years"])
    n_val = int(cfg["data"]["valuation_avg_years"])
    col = lambda f, y: _v(a.at[y, f]) if f in a.columns else None  # noqa: E731

    def prev(y):
        return y - 1 if (y - 1) in a.index else None

    def avg_bal(field, y):
        p = prev(y)
        return R.avg_pair(col(field, p) if p else None, col(field, y))

    def ebit_of(y):
        e = col("ebit", y)
        if e is None and col("pretax_income", y) is not None and col("interest_expense", y) is not None:
            e = col("pretax_income", y) + col("interest_expense", y)
        return e if e is not None else col("operating_income", y)

    def debt_of(y):
        d = col("total_debt", y)
        if d is None and col("total_assets", y) is not None:
            return 0.0   # balance sheet present but no debt line: treat as debt-free
        return d

    shares_adj = adjusted_shares(c)
    eps_adj = {y: R.safe_div(col("net_income", y), shares_adj.get(y)) for y in years}

    hist: dict[str, dict[int, Optional[float]]] = {
        "current_ratio": {y: R.current_ratio(col("current_assets", y), col("current_liabilities", y)) for y in years},
        "quick_ratio": {y: R.quick_ratio(col("current_assets", y), col("inventory", y),
                                         col("current_liabilities", y)) for y in years},
        "debt_to_equity": {y: R.debt_to_equity(debt_of(y), col("total_equity", y)) for y in years},
        "roe": {y: R.roe(col("net_income", y), avg_bal("total_equity", y)) for y in years},
        "net_margin": {y: R.net_margin(col("net_income", y), col("revenue", y)) for y in years},
        "operating_margin": {y: R.operating_margin(col("operating_income", y), col("revenue", y)) for y in years},
        "roa": {y: R.roa(col("net_income", y), avg_bal("total_assets", y)) for y in years},
        "nim": {y: R.nim(col("net_interest_income", y), avg_bal("total_assets", y)) for y in years},
    }

    def cap_employed(y):
        e, d = col("total_equity", y), debt_of(y)
        return e + d if e is not None and d is not None else None

    hist["roce"] = {}
    for y in years:
        p = prev(y)
        ce = R.avg_pair(cap_employed(p) if p else None, cap_employed(y))
        hist["roce"][y] = R.roce(ebit_of(y), ce)

    hist["interest_coverage"] = {}
    for y in years:
        ic = R.interest_coverage(ebit_of(y), col("interest_expense", y))
        if ic is None and col("interest_expense", y) is None and debt_of(y) == 0 and (ebit_of(y) or 0) > 0:
            ic = math.inf
        hist["interest_coverage"][y] = ic

    fcf = {}
    for y in years:
        f = col("fcf", y)
        if f is None:
            f = R.free_cash_flow(col("ocf", y), col("capex", y))
        fcf[y] = f
    # Cash flow covers the whole group, so compare it with profit *including* minority interests.
    def ni_group(y):
        v = col("net_income_incl_nci", y)
        return v if v is not None else col("net_income", y)
    ni_group_field = "net_income_incl_nci" if a["net_income_incl_nci"].notna().any() else "net_income"
    hist["ocf_to_net_profit"] = {y: R.ocf_to_net_profit(col("ocf", y), ni_group(y)) for y in years}
    hist["fcf_margin"] = {y: R.margin(fcf[y], col("revenue", y)) for y in years}

    # ---- valuation history at each fiscal year-end ----
    pe_h, pb_h, peg_h = {}, {}, {}
    for y in years:
        px = price_at(c.prices, c.fy_end.get(y))
        pe_h[y] = R.pe(px, eps_adj.get(y))
        bvps = R.safe_div(col("total_equity", y), shares_adj.get(y))
        pb_h[y] = R.pb(px, bvps)
        g3, span = window_cagr({k: v for k, v in eps_adj.items() if k <= y and v}, 3)
        peg_h[y] = R.peg(pe_h[y], g3) if span >= 2 else None

    metrics: dict[str, Metric] = {}

    def add(key, value, history=None, note=""):
        label, unit = LABELS[key]
        t = cfg["thresholds"].get(key)
        hb = (t["good"] > t["bad"]) if t else None
        h = _clean(history or {})
        metrics[key] = Metric(key=key, label=label, value=_v(value) if value != math.inf else math.inf,
                              unit=unit, history=h, note=note, trend=_trend(h, hb))

    for key in ["current_ratio", "quick_ratio", "debt_to_equity", "interest_coverage", "roe", "roce",
                "net_margin", "operating_margin", "roa", "nim", "fcf_margin"]:
        y, v = _latest(hist[key])
        add(key, v, hist[key], note=f"FY{y}" if y else "")

    # growth
    for key, series in (("revenue_cagr", {y: col("revenue", y) for y in years}),
                        ("profit_cagr", {y: col("net_income", y) for y in years}),
                        ("eps_cagr", eps_adj)):
        g, span = window_cagr({k: v for k, v in series.items() if v is not None}, n_cagr)
        note = f"{span}y CAGR" if span else "not enough history"
        if g is None and span:
            note = f"{span}y: undefined (loss at start or end)"
        add(key, g, None, note)

    # cash flow quality, aggregated over the CAGR window
    recent = years[-n_cagr:]
    pairs = [(col("ocf", y), ni_group(y)) for y in recent
             if col("ocf", y) is not None and ni_group(y) is not None]
    agg = R.ocf_to_net_profit(sum(p[0] for p in pairs), sum(p[1] for p in pairs)) if pairs else None
    add("ocf_to_net_profit", agg, hist["ocf_to_net_profit"],
        note=f"sum of last {len(pairs)} years" if pairs else "")
    fcf_recent = [fcf[y] for y in recent if fcf.get(y) is not None]
    if fcf_recent:
        pos = sum(1 for f in fcf_recent if f > 0)
        add("fcf_positive_years", pos * 5 / len(fcf_recent), None, note=f"{pos} of last {len(fcf_recent)} years")
        metrics["fcf_positive_years"].value = pos * 5 / len(fcf_recent)
    else:
        add("fcf_positive_years", None)
    fy, fv = _latest(fcf)
    add("free_cash_flow", fv, fcf, note=f"FY{fy}" if fy else "")

    # valuation: current vs history
    latest_eps_y, latest_eps = _latest(eps_adj)
    pe_now = c.trailing_pe if c.trailing_pe and c.trailing_pe > 0 else R.pe(c.price, latest_eps)
    ly = years[-1] if years else None
    bvps_now = R.safe_div(col("total_equity", ly) if ly else None, c.shares or shares_adj.get(ly))
    pb_now = R.pb(c.price, bvps_now)
    eps_g, eps_span = window_cagr({k: v for k, v in eps_adj.items() if v}, n_cagr)
    peg_now = R.peg(pe_now, eps_g)

    val_years = years[-n_val:]
    for key, now, h in (("pe", pe_now, pe_h), ("pb", pb_now, pb_h), ("peg", peg_now, peg_h)):
        avg = R.average([h.get(y) for y in val_years])
        n_avail = sum(1 for y in val_years if h.get(y) is not None)
        add(key, now, h, note=f"{n_avail}y avg {avg:.1f}x" if avg is not None else "no history")
        prem = R.premium_vs_average(now, avg)
        add(f"{key}_vs_avg", prem, None,
            note=f"vs {n_avail}y avg {avg:.1f}x" if avg is not None else "no history")

    # banks / NBFCs: asset quality and capital
    npa = c.quarterly_npa
    extras: dict[str, Any] = {"gnpa_change_4q": None}
    for key, colname in (("gnpa", "gnpa_pct"), ("nnpa", "nnpa_pct")):
        manual = c.manual.get(f"{key}_pct")
        if manual is not None:
            add(key, manual, None, note="manual input")
            continue
        if npa is not None and colname in npa and npa[colname].notna().any():
            s = npa[colname].dropna()
            add(key, s.iloc[-1], None, note=f"quarter {s.index[-1]}")
            if key == "gnpa" and len(s) >= 5:
                extras["gnpa_change_4q"] = float(s.iloc[-1] - s.iloc[-5])
        else:
            add(key, None, None, note="not published by data sources")
    car = c.manual.get("car_pct")
    add("car", car, None, note="manual input" if car is not None else "add car_pct under manual_inputs in config.yaml")

    # ---- workings: exactly which statement cells built each metric ----
    def status_of(field, ys):
        return worst(c.provenance.get(field, {}).get(y, {}).get("status", "single") for y in ys)

    def cell(label, field, ys, value=None, note="", statement=None):
        ys = [ys] if isinstance(ys, (int, np.integer)) else [y for y in ys if y is not None]
        ys = [int(y) for y in ys]
        if value is None and len(ys) == 1:
            value = col(field, ys[0])
        return {"label": label, "field": field, "years": ys, "statement": statement or STATEMENT_OF.get(field, "derived"),
                "value": _v(value), "status": status_of(field, ys) if ys else "single", "note": note}

    def market(label, value, note=""):
        return {"label": label, "field": label.lower().replace(" ", "_"), "years": [], "statement": "market",
                "value": _v(value), "status": "single", "note": note or "Yahoo Finance, latest"}

    def derived(label, value, fields, ys, note=""):
        st = worst(status_of(f, ys) for f in fields) if ys else "single"
        return {"label": label, "field": "", "years": [int(y) for y in ys], "statement": "derived",
                "value": _v(value), "status": st, "note": note}

    def ebit_parts(y):
        if col("pretax_income", y) is not None and col("interest_expense", y) is not None:
            return "(Profit before tax + Interest)", [cell("Profit before tax", "pretax_income", y),
                                                      cell("Interest expense", "interest_expense", y)]
        if col("ebit", y) is not None:
            return "EBIT", [cell("EBIT", "ebit", y)]
        return "Operating income", [cell("Operating income", "operating_income", y)]

    def debt_cell(ys, avg=False):
        ys = [y for y in ys if y is not None]
        vals = [debt_of(y) for y in ys]
        none_reported = all(col("total_debt", y) is None for y in ys)
        v = (sum(x for x in vals if x is not None) / max(len(vals), 1)) if avg else (vals[0] if vals else None)
        return cell("Total debt", "total_debt", ys, value=v, note="none reported" if none_reported else "")

    def cagr_span(series, n):
        h = {k: v for k, v in series.items() if v is not None}
        if len(h) < 2:
            return None, None
        end = max(h)
        starts = [y for y in h if end - n <= y < end]
        return (min(starts), end) if starts else (None, end)

    W: dict[str, tuple[str, list]] = {}
    ly_of = {k: _latest(hist[k])[0] for k in hist}
    y = ly_of.get("current_ratio")
    if y:
        W["current_ratio"] = ("Current assets ÷ Current liabilities",
                              [cell("Current assets", "current_assets", y), cell("Current liabilities", "current_liabilities", y)])
    y = ly_of.get("quick_ratio")
    if y:
        inv = col("inventory", y)
        W["quick_ratio"] = ("(Current assets − Inventory) ÷ Current liabilities",
                            [cell("Current assets", "current_assets", y),
                             cell("Inventory", "inventory", y, value=inv if inv is not None else 0.0,
                                  note="" if inv is not None else "none reported"),
                             cell("Current liabilities", "current_liabilities", y)])
    y = ly_of.get("debt_to_equity")
    if y:
        W["debt_to_equity"] = ("Total debt ÷ Shareholders' equity",
                               [debt_cell([y]), cell("Shareholders' equity", "total_equity", y)])
    y = ly_of.get("interest_coverage")
    if y:
        name, parts = ebit_parts(y)
        if name.startswith("(Profit"):
            W["interest_coverage"] = ("(Profit before tax + Interest) ÷ Interest", parts)
        else:
            W["interest_coverage"] = (f"{name} ÷ Interest expense", parts + [cell("Interest expense", "interest_expense", y)])
    y = ly_of.get("roe")
    if y:
        p = prev(y)
        W["roe"] = ("Net income ÷ average shareholders' equity",
                    [cell("Net income", "net_income", y),
                     cell("Shareholders' equity (avg)", "total_equity", [p, y], value=avg_bal("total_equity", y))])
    y = ly_of.get("roce")
    if y:
        p = prev(y)
        name, parts = ebit_parts(y)
        eq_avg = avg_bal("total_equity", y)
        W["roce"] = (f"{name} ÷ average (equity + debt)",
                     parts + [cell("Shareholders' equity (avg)", "total_equity", [p, y], value=eq_avg),
                              debt_cell([p, y], avg=True)])
    for key, field, label in (("net_margin", "net_income", "Net income"), ("operating_margin", "operating_income", "Operating income")):
        y = ly_of.get(key)
        if y:
            W[key] = (f"{label} ÷ Revenue", [cell(label, field, y), cell("Revenue", "revenue", y)])
    y = ly_of.get("roa")
    if y:
        p = prev(y)
        W["roa"] = ("Net income ÷ average total assets",
                    [cell("Net income", "net_income", y),
                     cell("Total assets (avg)", "total_assets", [p, y], value=avg_bal("total_assets", y))])
    y = ly_of.get("nim")
    if y:
        p = prev(y)
        W["nim"] = ("Net interest income ÷ average total assets",
                    [cell("Net interest income", "net_interest_income", y),
                     cell("Total assets (avg)", "total_assets", [p, y], value=avg_bal("total_assets", y))])
    y = ly_of.get("fcf_margin")
    if y:
        if col("fcf", y) is not None:
            W["fcf_margin"] = ("Free cash flow ÷ Revenue", [cell("Free cash flow", "fcf", y), cell("Revenue", "revenue", y)])
        else:
            W["fcf_margin"] = ("(Operating cash flow − Capex) ÷ Revenue",
                               [cell("Operating cash flow", "ocf", y), cell("Capital expenditure", "capex", y),
                                cell("Revenue", "revenue", y)])
    if fy:
        if col("fcf", fy) is not None:
            W["free_cash_flow"] = ("Free cash flow, as reported", [cell("Free cash flow", "fcf", fy)])
        else:
            W["free_cash_flow"] = ("Operating cash flow − Capex",
                                   [cell("Operating cash flow", "ocf", fy), cell("Capital expenditure", "capex", fy)])

    for key, field, label, series in (("revenue_cagr", "revenue", "Revenue", {y_: col("revenue", y_) for y_ in years}),
                                      ("profit_cagr", "net_income", "Net income", {y_: col("net_income", y_) for y_ in years}),
                                      ("eps_cagr", "eps", "EPS", eps_adj)):
        s0, s1 = cagr_span(series, n_cagr)
        if s0 and s1:
            note = "split-adjusted" if key == "eps_cagr" else ""
            W[key] = (f"(End ÷ Start)^(1/{s1 - s0}) − 1",
                      [cell(f"{label} FY{s0}", field, s0, value=series[s0], note=note),
                       cell(f"{label} FY{s1}", field, s1, value=series[s1], note=note)])
    if pairs:
        ys = [y_ for y_ in recent if col("ocf", y_) is not None and ni_group(y_) is not None]
        ni_label = "Profit incl. minority interests" if ni_group_field == "net_income_incl_nci" else "Net income"
        W["ocf_to_net_profit"] = (f"Σ Operating cash flow ÷ Σ {ni_label}",
                                  [cell(f"Operating cash flow, FY{ys[0]}–{ys[-1]}", "ocf", ys, value=sum(p_[0] for p_ in pairs)),
                                   cell(f"{ni_label}, FY{ys[0]}–{ys[-1]}", ni_group_field, ys, value=sum(p_[1] for p_ in pairs))])
    if fcf_recent:
        ys = [y_ for y_ in recent if fcf.get(y_) is not None]
        if all(col("fcf", y_) is not None for y_ in ys):
            W["fcf_positive_years"] = ("Years with free cash flow > 0", [cell(f"Free cash flow, FY{ys[0]}–{ys[-1]}", "fcf", ys)])
        else:
            W["fcf_positive_years"] = ("Years with Operating cash flow − Capex > 0",
                                       [cell(f"Operating cash flow, FY{ys[0]}–{ys[-1]}", "ocf", ys),
                                        cell(f"Capital expenditure, FY{ys[0]}–{ys[-1]}", "capex", ys)])

    eps_ttm = R.safe_div(c.price, pe_now)
    if pe_now:
        W["pe"] = ("Share price ÷ EPS (trailing 12 months)",
                   [market("Share price", c.price), market("EPS (TTM)", eps_ttm)])
    if pb_now and ly:
        W["pb"] = ("Share price ÷ (Shareholders' equity ÷ Shares outstanding)",
                   [market("Share price", c.price), cell("Shareholders' equity", "total_equity", ly),
                    market("Shares outstanding", c.shares or shares_adj.get(ly))])
    if peg_now:
        s0, s1 = cagr_span(eps_adj, n_cagr)
        W["peg"] = ("P/E ÷ EPS growth rate (% a year)",
                    [derived("P/E (TTM)", pe_now, [], [], note="share price ÷ EPS"),
                     derived("EPS growth", eps_g, ["net_income", "eps"], [y_ for y_ in (s0, s1) if y_],
                             note=f"{eps_span}y CAGR")])
    for key, now, h, fields in (("pe_vs_avg", pe_now, pe_h, ["net_income", "eps"]),
                                ("pb_vs_avg", pb_now, pb_h, ["total_equity"]),
                                ("peg_vs_avg", peg_now, peg_h, ["net_income", "eps"])):
        ys = [y_ for y_ in val_years if h.get(y_) is not None]
        avg = R.average([h.get(y_) for y_ in val_years])
        if now and avg:
            base = {"pe": "P/E", "pb": "P/B", "peg": "PEG"}[key.split("_")[0]]
            W[key] = (f"Current {base} ÷ average fiscal-year-end {base} − 1",
                      [derived(f"{base} now", now, [], [], note="computed above"),
                       derived(f"{base} average, FY{ys[0]}–{ys[-1]}", avg, fields, ys,
                               note="price at each fiscal year-end")])
    for key in ("gnpa", "nnpa"):
        m = metrics.get(key)
        if m and m.value is not None:
            W[key] = ("As reported by the bank", [{"label": m.label, "field": key, "years": [], "statement": "market",
                                                   "value": m.value, "status": "single", "note": m.note}])
    if metrics.get("car") and metrics["car"].value is not None:
        W["car"] = ("Entered from the bank's filing (config.yaml)",
                    [{"label": "Capital adequacy ratio", "field": "car", "years": [], "statement": "market",
                      "value": metrics["car"].value, "status": "single", "note": "manual input"}])

    for key, (formula, inputs) in W.items():
        m = metrics.get(key)
        if not m:
            continue
        m.workings = {"formula": formula, "inputs": inputs}
        m.verified = not any(i["status"] == "mismatch" for i in inputs)

    extras.update({"eps_adj": eps_adj, "fcf": fcf, "pe_hist": pe_h, "pb_hist": pb_h,
                   "eps_cagr_span": eps_span, "hist": hist, "eps_ttm": eps_ttm})
    return metrics, extras
