"""Data for the animated spider widget: which metrics the spider "picks" and in what order."""
from __future__ import annotations

import json
import math
from html import escape as html_escape
from pathlib import Path
from typing import Any

from typing import Optional

from .. import explain
from ..explain import fmt_value
from ..model import Assessment, CompanyData, Metric
from ..sources.merge import summary as merge_summary

WIDGET_JS = Path(__file__).resolve().parents[2] / "web" / "finspider-spider.js"

SHORT = {
    "current_ratio": "Current ratio", "quick_ratio": "Quick ratio", "debt_to_equity": "Debt/Equity",
    "interest_coverage": "Interest cover", "roe": "ROE", "roce": "ROCE", "net_margin": "Net margin",
    "operating_margin": "Op. margin", "revenue_cagr": "Revenue CAGR", "profit_cagr": "Profit CAGR",
    "eps_cagr": "EPS CAGR", "ocf_to_net_profit": "Cash conversion", "fcf_positive_years": "FCF years",
    "fcf_margin": "FCF margin", "pe": "P/E", "pb": "P/B", "peg": "PEG", "pe_vs_avg": "P/E vs history",
    "pb_vs_avg": "P/B vs history", "peg_vs_avg": "PEG vs history", "nim": "NIM", "roa": "ROA",
    "gnpa": "Gross NPA", "nnpa": "Net NPA", "car": "CAR",
}

# Which metric a red flag "lives on", so the spider can point at it.
FLAG_METRIC = {
    "net_loss_latest_year": "net_margin", "negative_equity": "debt_to_equity",
    "negative_ocf_years": "ocf_to_net_profit", "low_cash_conversion": "ocf_to_net_profit",
    "high_debt_to_equity": "debt_to_equity", "low_interest_coverage": "interest_coverage",
    "revenue_decline": "revenue_cagr", "profit_decline": "profit_cagr", "expensive_vs_history": "pe_vs_avg",
    "high_gnpa": "gnpa", "rising_gnpa": "gnpa", "high_nnpa": "nnpa", "low_car": "car",
}


def _num(v):
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        return None
    return round(float(v), 4)


def importance(a: Assessment, cfg: dict) -> dict[str, float]:
    """How much each metric matters to the verdict: its effective weight times how far
    its score is from neutral (5). A red flag on the metric dominates everything."""
    prof = cfg["profiles"][a.profile]
    total_cat = sum(float(c["weight"]) for c in prof.values()) or 1
    flagged = {FLAG_METRIC.get(f.key) for f in a.red_flags}
    out = {}
    for cname, cat in prof.items():
        msum = sum(float(w) for w in cat["metrics"].values()) or 1
        for key, w in cat["metrics"].items():
            m = a.metrics.get(key)
            if not m or m.score is None:
                continue
            eff = float(cat["weight"]) / total_cat * float(w) / msum
            out[key] = eff * (abs(m.score - 5) + 1) + (1.0 if key in flagged else 0.0)
    return out


def choose_picks(a: Assessment, cfg: dict, n: int = 7) -> list[str]:
    imp = importance(a, cfg)
    by_cat: dict[str, list[str]] = {}
    for key in sorted(imp, key=lambda k: -imp[k]):
        by_cat.setdefault(a.metrics[key].category, []).append(key)
    # one per category (most important categories first), then the next most important overall
    picks = [keys[0] for _, keys in sorted(by_cat.items(), key=lambda kv: -imp[kv[1][0]])][:n]
    for key in sorted(imp, key=lambda k: -imp[k]):
        if len(picks) >= n:
            break
        if key not in picks:
            picks.append(key)
    flagged = {FLAG_METRIC.get(f.key) for f in a.red_flags}
    # Tour order: strengths first, then weak spots, red flags last.
    return sorted(picks, key=lambda k: (k in flagged, a.metrics[k].score < 5, -imp[k]))


STATEMENT_ROWS = {
    "income": ("Income statement", [("revenue", "Revenue"), ("operating_income", "Operating income"),
                                    ("interest_expense", "Interest expense"), ("depreciation", "Depreciation"),
                                    ("pretax_income", "Profit before tax"),
                                    ("net_income_incl_nci", "Profit incl. minority"),
                                    ("net_income", "Net income (shareholders)"),
                                    ("net_interest_income", "Net interest income"), ("eps", "EPS (diluted)")]),
    "balance": ("Balance sheet", [("total_assets", "Total assets"), ("current_assets", "Current assets"),
                                  ("inventory", "Inventory"), ("cash", "Cash"),
                                  ("current_liabilities", "Current liabilities"), ("deposits", "Deposits"),
                                  ("total_debt", "Total debt"), ("total_equity", "Shareholders' equity")]),
    "cashflow": ("Cash flow", [("ocf", "Operating cash flow"), ("capex", "Capital expenditure"),
                               ("fcf", "Free cash flow")]),
}
PER_SHARE = {"eps"}
SHEET_YEARS = 6          # enough columns for a 5-year CAGR


def _scale(c: CompanyData) -> tuple[float, str, str]:
    """(divisor, unit label, number format) for money cells."""
    if c.currency == "INR":
        return 1e7, "₹ crore", "{:,.0f}"
    rev = c.annual["revenue"].dropna()
    big = not rev.empty and rev.abs().max() >= 1e10
    sym = {"USD": "US$"}.get(c.currency, c.currency)
    return (1e9, f"{sym} billion", "{:,.2f}") if big else (1e6, f"{sym} million", "{:,.0f}")


def _input_display(i: dict, currency: str) -> str:
    v = i.get("value")
    ys = i.get("years") or []
    if v is None:
        return f"FY{min(ys)}–FY{max(ys)}" if len(ys) > 1 else "n/a"
    label, field, st = i.get("label", ""), i.get("field", ""), i.get("statement")
    sym = {"USD": "$", "INR": "₹", "EUR": "€", "GBP": "£"}.get(currency, "")
    if label == "EPS growth":
        return f"{v:.1f}% a year"
    if field in PER_SHARE or label.startswith("EPS") or label == "Share price":
        return f"{sym}{v:,.2f}"
    if label == "Shares outstanding":
        return f"{v / 1e9:,.2f}B" if v >= 1e9 else f"{v / 1e6:,.1f}M"
    if label.startswith(("P/E", "P/B", "PEG")) or "average" in label:
        return f"{v:.2f}x" if label.startswith("PEG") else f"{v:.1f}x"
    if "%" in label or field in ("gnpa", "nnpa", "car") or "NPA" in label or "adequacy" in label:
        return f"{v:.2f}%"
    if st in ("income", "balance", "cashflow"):
        return explain.fmt_money(v, currency)
    return f"{v:,.2f}"


def _workings(m: Metric, currency: str) -> Optional[dict]:
    if not m.workings:
        return None
    return {
        "formula": m.workings["formula"],
        "inputs": [{k: i.get(k) for k in ("label", "statement", "field", "years", "status", "note")}
                   | {"display": _input_display(i, currency)} for i in m.workings["inputs"]],
        "verified": m.verified,
    }


def build_statements(c: CompanyData, metrics: list[dict]) -> tuple[dict, list[dict]]:
    """The statement sheet the spider reads from: last few fiscal years, each cell cited."""
    years = [int(y) for y in c.annual.index][-SHEET_YEARS:]
    div, unit, numfmt = _scale(c)
    sources: list[dict] = []
    src_index: dict[tuple, int] = {}

    def src_id(cite: dict) -> int:
        key = (cite.get("doc"), cite.get("url"))
        if key not in src_index:
            src_index[key] = len(sources)
            sources.append({"source": cite.get("source"), "doc": cite.get("doc"), "url": cite.get("url")})
        return src_index[key]

    lender_only = {"net_interest_income", "deposits"}
    is_lender = any(m["key"] in ("nim", "gnpa") and m.get("value") is not None for m in metrics)
    tabs = []
    for key, (name, rows) in STATEMENT_ROWS.items():
        out_rows = []
        for field, label in rows:
            if field in lender_only and not is_lender:
                continue
            if field == "net_income_incl_nci":     # only worth a row if minority interests matter
                both = c.annual[["net_income", "net_income_incl_nci"]].loc[years].dropna()
                if both.empty or ((both["net_income_incl_nci"] - both["net_income"]).abs()
                                  <= both["net_income"].abs() * 0.005).all():
                    continue
            cells = {}
            for y in years:
                v = c.annual.at[y, field] if field in c.annual else None
                if v is None or v != v:
                    continue
                cite = c.provenance.get(field, {}).get(y, {})
                v = float(v)
                shown = v if field in PER_SHARE else v / div
                cells[str(y)] = {"v": round(shown, 4), "d": f"{shown:,.2f}" if field in PER_SHARE else numfmt.format(shown),
                                 "s": cite.get("status", "single"), "src": src_id(cite) if cite else None,
                                 "check": cite.get("check")}
            if cells:
                out_rows.append({"field": field, "label": label, "per_share": field in PER_SHARE, "cells": cells})
        tabs.append({"key": key, "name": name, "rows": out_rows})

    # Market tab: every market input any metric uses (price, TTM EPS, shares, NPA...)
    market_rows, seen = [], set()
    for m in metrics:
        for i in (m.get("workings") or {}).get("inputs", []):
            if i["statement"] == "market" and i["label"] not in seen:
                seen.add(i["label"])
                market_rows.append({"field": i["field"], "label": i["label"], "display": i["display"],
                                    "note": i.get("note") or "", "s": i["status"]})
    tabs.append({"key": "market", "name": "Market data", "rows": market_rows})
    return {"years": years, "unit": unit, "tabs": tabs}, sources


def build_spider_data(c: CompanyData, a: Assessment, cfg: dict, generated: str) -> dict[str, Any]:
    prof = cfg["profiles"][a.profile]
    total_w = sum(a.category_weights.values()) or 1
    flags_by_metric: dict[str, list[dict]] = {}
    for f in a.red_flags:
        flags_by_metric.setdefault(FLAG_METRIC.get(f.key, ""), []).append({"severity": f.severity, "text": f.text})

    categories = [{
        "key": k, "name": explain.CATEGORY_NAMES.get(k, k),
        "score": _num(a.category_scores.get(k)), "weight": round(a.category_weights[k] / total_w, 4),
        "rating": explain.rating_word(a.category_scores.get(k)),
    } for k in prof]

    metrics = []
    for cat in prof:
        for key in prof[cat]["metrics"]:
            m = a.metrics.get(key)
            if not m:
                continue
            metrics.append({
                "key": key, "label": m.label, "short": SHORT.get(key, m.label), "category": cat,
                "value": _num(m.value), "display": fmt_value(m, c.currency), "note": m.note, "trend": m.trend,
                "score": _num(m.score), "flag": m.flag, "sentence": explain.sentence(m, c.currency),
                "red_flags": flags_by_metric.get(key, []),
                "workings": _workings(m, c.currency),
            })

    statements, sources = build_statements(c, metrics)
    return {
        "schema": "finspider.spider/2",
        "statements": statements,
        "sources": sources,
        "verification": {**merge_summary(c.provenance, years=statements["years"]),
                         "primary": c.primary_source,
                         "tolerance_pct": float(cfg.get("verification", {}).get("tolerance_pct", 2.0))},
        "company": {"name": c.name, "ticker": c.ticker, "currency": c.currency, "price": _num(c.price),
                    "sector": (c.info or {}).get("sector"), "industry": (c.info or {}).get("industry")},
        "profile": a.profile,
        "verdict": a.verdict, "overall": _num(a.overall), "verdict_note": a.verdict_note,
        "generated": generated,
        "categories": categories,
        "metrics": metrics,
        "picks": choose_picks(a, cfg),
        "red_flags": [{"severity": f.severity, "text": f.text, "metric": FLAG_METRIC.get(f.key)} for f in a.red_flags],
        "notes": list(c.warnings),        # data caveats shown to the reader (e.g. cross-check unavailable)
        "disclaimer": "Automated analysis of public data. Not investment advice.",
    }


def write(out_dir: Path, data: dict[str, Any]) -> tuple[Path, Path]:
    """Write spider.json (for dashboards) and spider.html (standalone, works offline)."""
    json_path = out_dir / "spider.json"
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    # A literal "</script" inside inline JS would end the script tag early.
    js = WIDGET_JS.read_text(encoding="utf-8").replace("</script", "<\\/script")
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = html_escape(f"{data['company']['name']} - finspider")
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  html,body{{margin:0;min-height:100%;background:#eef4fc;font-family:system-ui,-apple-system,"Segoe UI",sans-serif}}
  @media (prefers-color-scheme: dark){{html,body{{background:#06101f}}}}
  main{{max-width:1100px;margin:0 auto;padding:24px 16px}}
</style>
</head>
<body>
<main>
<fin-spider>
<script type="application/json">{payload}</script>
</fin-spider>
</main>
<script>
{js}
</script>
</body>
</html>
"""
    html_path = out_dir / "spider.html"
    html_path.write_text(html, encoding="utf-8")
    return json_path, html_path
