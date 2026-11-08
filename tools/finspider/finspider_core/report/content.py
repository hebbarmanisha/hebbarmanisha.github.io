"""Build renderer-neutral report content shared by the Markdown and PDF outputs."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .. import explain
from ..explain import fmt_money, fmt_value
from ..model import Assessment, CompanyData

DISCLAIMER = (
    "This report is generated automatically from public data (Yahoo Finance via yfinance, and "
    "Screener.in where noted) using fixed rules in config.yaml. It is for education and research "
    "only and is NOT investment advice or a recommendation to buy or sell any security. The data "
    "may be incomplete, delayed or wrong, and the scoring ignores many things that matter "
    "(management, competition, governance, macro conditions, news). The author is not a "
    "registered investment adviser. Do your own research and consult a SEBI-registered (or your "
    "country's equivalent) adviser before making investment decisions."
)

METHOD_NOTES = [
    "Money values are in the share's trading currency. Indian figures are shown in crores (1 Cr = 10 million).",
    "ROE and ROCE use the average of opening and closing balances; capital employed = equity + total debt.",
    "Interest coverage = EBIT / interest expense, where EBIT = profit before tax + interest.",
    "OCF / net profit is summed over the CAGR window so one unusual year doesn't dominate.",
    "Historical P/E and P/B use the month-end share price at each fiscal year-end and EPS/book value "
    "restated to today's share count (splits and bonus issues).",
    "Current P/E is the trailing-twelve-month figure from Yahoo when available.",
    "PEG = P/E / EPS CAGR. Historical PEG uses the 3-year EPS CAGR ending that year.",
    "For banks/NBFCs, NIM is net interest income / average total assets - a proxy, since interest-earning "
    "assets are not published by these sources. Debt/equity, current ratio and cash-flow metrics are "
    "not used for lenders.",
    "Each metric scores 0-10 on a straight line between the 'bad' and 'good' thresholds in config.yaml; "
    "categories and the overall score are weighted averages of whatever data is available.",
]

FLAG_ICON = {"good": "\U0001F7E2 good", "ok": "\U0001F7E1 ok", "bad": "\U0001F534 bad", "n/a": "—",
             "unverified": "⚠️ unverified"}


@dataclass
class ReportContent:
    title: str
    subtitle: str
    generated: str
    verdict: str
    overall: str
    verdict_note: str
    strengths: list[str]
    weaknesses: list[str]
    red_flags: list[tuple[str, str]]
    overview_text: str
    facts: list[tuple[str, str]]
    health: list[str]
    scorecard: list[list[str]]
    ratio_rows: list[dict[str, str]]
    history_header: list[str]
    history_rows: list[list[str]]
    charts: list[tuple[str, Path]]
    sources: list[tuple[str, str]]
    warnings: list[str]
    method_notes: list[str] = field(default_factory=lambda: list(METHOD_NOTES))
    disclaimer: str = DISCLAIMER


CHART_TITLES = {
    "revenue_profit": "Revenue and net profit", "margins": "Margins", "returns": "Returns",
    "cash_flow": "Profit vs cash", "valuation": "Valuation history", "npa": "Asset quality (NPA)",
}


def build(c: CompanyData, a: Assessment, extras: dict[str, Any], charts: dict[str, Path], cfg: dict) -> ReportContent:
    info = c.info or {}
    cur = c.currency
    profile_name = "Bank / NBFC" if a.profile == "financial" else "General (non-financial)"

    facts = [
        ("Ticker", c.ticker),
        ("Sector / industry", f"{info.get('sector', 'n/a')} / {info.get('industry', 'n/a')}"),
        ("Country", info.get("country", "n/a")),
        ("Share price", f"{c.price:,.2f} {cur}" if c.price else "n/a"),
        ("Market cap", fmt_money(info.get("marketCap"), cur)),
        ("Employees", f"{info['fullTimeEmployees']:,}" if info.get("fullTimeEmployees") else "n/a"),
        ("Website", info.get("website", "n/a")),
        ("Scoring profile", profile_name),
        ("Years of history", f"{c.annual['revenue'].notna().sum()} (FY{c.annual.index.min()}-FY{c.annual.index.max()})"),
    ]

    order = list(cfg["profiles"][a.profile].keys())
    total_w = sum(a.category_weights.values())
    scorecard = []
    for cat in order:
        s = a.category_scores.get(cat)
        scorecard.append([explain.CATEGORY_NAMES.get(cat, cat), f"{a.category_weights[cat] / total_w:.0%}",
                          f"{s:.1f}" if s is not None else "n/a", explain.rating_word(s)])

    ratio_rows = []
    shown = [k for cat in order for k in cfg["profiles"][a.profile][cat]["metrics"]]
    if "fcf_margin" in shown:   # show the absolute FCF (unscored) next to FCF margin
        shown.insert(shown.index("fcf_margin") + 1, "free_cash_flow")
    for k in shown:
        m = a.metrics.get(k)
        if not m:
            continue
        ratio_rows.append({
            "category": explain.CATEGORY_NAMES.get(m.category or "", "") if m.category else "",
            "metric": m.label, "value": fmt_value(m, cur), "note": m.note, "trend": m.trend or "",
            "flag": m.flag, "score": f"{m.score:.1f}" if m.score is not None else "",
        })

    df = c.annual.tail(10)
    years = list(df.index)
    hist_header = ["", *[f"FY{y}" for y in years]]
    money_rows = [("Revenue", "revenue"), ("Net profit", "net_income"), ("Operating cash flow", "ocf"),
                  ("Shareholders' equity", "total_equity")]
    if a.profile == "financial":
        money_rows += [("Net interest income", "net_interest_income"), ("Total assets", "total_assets")]
    else:
        money_rows += [("Total debt", "total_debt")]
    hist_rows = []
    for label, f in money_rows:
        hist_rows.append([label, *[_short_money(df.at[y, f], cur) for y in years]])
    if a.profile != "financial":
        hist_rows.append(["Free cash flow", *[_short_money(extras["fcf"].get(y), cur) for y in years]])
    hist_rows.append(["EPS (adj.)", *[f"{extras['eps_adj'][y]:.1f}" if extras["eps_adj"].get(y) else "n/a"
                                     for y in years]])
    for key, label in (("roe", "ROE %"), ("net_margin", "Net margin %")):
        h = extras["hist"][key]
        hist_rows.append([label, *[f"{h[y]:.1f}" if h.get(y) is not None else "n/a" for y in years]])

    src_rows = []
    by_src: dict[str, list[str]] = {}
    for f, s in sorted(c.sources.items()):
        by_src.setdefault(s, []).append(f)
    for s, fs in by_src.items():
        src_rows.append((s, ", ".join(fs)))
    if c.screener_url:
        src_rows.append(("screener page", c.screener_url))

    return ReportContent(
        title=f"{c.name} ({c.ticker})",
        subtitle=f"Long-term fundamental health check · {profile_name} profile",
        generated=dt.date.today().isoformat(),
        verdict=a.verdict,
        overall=f"{a.overall:.1f}/10" if a.overall is not None else "n/a",
        verdict_note=a.verdict_note,
        strengths=a.strengths, weaknesses=a.weaknesses,
        red_flags=[(f.severity, f.text) for f in a.red_flags],
        overview_text=_trim(info.get("longBusinessSummary") or "No business description available."),
        facts=facts,
        health=[explain.category_summary(cat, a, cur) for cat in order],
        scorecard=scorecard,
        ratio_rows=ratio_rows,
        history_header=hist_header,
        history_rows=hist_rows,
        charts=[(CHART_TITLES.get(k, k), p) for k, p in charts.items()],
        sources=src_rows,
        warnings=c.warnings,
    )


def _trim(text: str, limit: int = 900) -> str:
    """Cut a long description at a sentence boundary."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = cut.rfind(". ")
    return cut[: end + 1] if end > 200 else cut.rstrip() + "..."


def _short_money(v, cur: str) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "n/a"
    if f != f:
        return "n/a"
    if cur == "INR":
        return f"{f / 1e7:,.0f}"
    return f"{f / 1e6:,.0f}"


def money_unit(cur: str) -> str:
    return "₹ crore" if cur == "INR" else f"{cur} million"
