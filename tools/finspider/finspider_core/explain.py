"""Plain-English wording and number formatting."""
from __future__ import annotations

import math
from typing import Optional

from .model import Assessment, Metric

CATEGORY_NAMES = {
    "liquidity": "Liquidity", "leverage": "Debt & solvency", "profitability": "Profitability",
    "growth": "Growth", "cash_flow": "Cash-flow quality", "valuation": "Valuation",
    "asset_quality": "Asset quality", "capital": "Capital strength",
}

CATEGORY_WHAT = {
    "liquidity": "can it pay its bills over the next year",
    "leverage": "how much it relies on borrowed money",
    "profitability": "how much profit it earns on sales and capital",
    "growth": "how fast sales and earnings have grown",
    "cash_flow": "whether reported profits turn into real cash",
    "valuation": "how expensive the share is today, vs itself and vs growth",
    "asset_quality": "how many loans have gone bad",
    "capital": "the cushion of capital against losses",
}

# (good, ok, bad) templates. {v} is the formatted value, {n} the metric note.
TEMPLATES = {
    "current_ratio": ("Short-term assets cover short-term liabilities a comfortable {v}.",
                      "Short-term assets cover short-term liabilities {v} - adequate.",
                      "Short-term assets cover short-term liabilities only {v} - liquidity is tight."),
    "quick_ratio": ("Even excluding inventory, liquid assets cover current liabilities {v}.",
                    "Liquid assets excluding inventory cover current liabilities {v}.",
                    "Excluding inventory, liquid assets cover just {v} of current liabilities."),
    "debt_to_equity": ("Very little debt: {v} of debt per unit of equity.",
                       "Moderate debt at {v} of equity.",
                       "Heavy borrowing: debt is {v} of equity."),
    "interest_coverage": ("Operating profit covers interest {v} - debt costs are no concern.",
                          "Operating profit covers interest {v}.",
                          "Operating profit covers interest only {v} - a squeeze if profits dip."),
    "roe": ("Earns a strong {v} return on shareholders' equity.",
            "Earns a reasonable {v} return on shareholders' equity.",
            "Earns a weak {v} return on shareholders' equity."),
    "roce": ("Earns {v} on all capital employed - a sign of a strong business.",
             "Earns {v} on capital employed - acceptable.",
             "Earns only {v} on capital employed."),
    "net_margin": ("Keeps {v} of revenue as net profit - high margins.",
                   "Keeps {v} of revenue as net profit.",
                   "Keeps only {v} of revenue as net profit - thin margins."),
    "operating_margin": ("Operating margin of {v} shows pricing power.",
                         "Operating margin of {v}.",
                         "Operating margin is thin at {v}."),
    "revenue_cagr": ("Revenue has grown {v} a year ({n}).",
                     "Revenue has grown {v} a year ({n}) - moderate.",
                     "Revenue growth is weak at {v} a year ({n})."),
    "profit_cagr": ("Net profit has compounded {v} a year ({n}).",
                    "Net profit has grown {v} a year ({n}).",
                    "Net profit growth is weak at {v} a year ({n})."),
    "eps_cagr": ("Earnings per share have compounded {v} a year ({n}).",
                 "EPS has grown {v} a year ({n}).",
                 "EPS growth is weak at {v} a year ({n})."),
    "ocf_to_net_profit": ("Profits are backed by cash: operating cash flow is {v} net profit ({n}).",
                          "Most profit converts to cash: operating cash flow is {v} net profit ({n}).",
                          "Profits are not turning into cash: operating cash flow is only {v} net profit ({n})."),
    "fcf_positive_years": ("Generated free cash flow in {n}.",
                           "Free cash flow was positive in {n}.",
                           "Free cash flow was positive in only {n}."),
    "fcf_margin": ("Turns {v} of revenue into free cash flow.",
                   "Free cash flow margin of {v}.",
                   "Free cash flow margin is low at {v}."),
    "pe": ("P/E of {v} is undemanding ({n}).",
           "P/E of {v} is fair ({n}).",
           "P/E of {v} is expensive ({n})."),
    "pb": ("Trades at {v} book value - inexpensive.",
           "Trades at {v} book value.",
           "Trades at a rich {v} book value."),
    "peg": ("PEG of {v}: the price looks cheap relative to earnings growth.",
            "PEG of {v}: price roughly in line with growth.",
            "PEG of {v}: the price runs well ahead of earnings growth."),
    "pe_vs_avg": ("P/E is {v} versus its own history ({n}) - cheaper than usual.",
                  "P/E is {v} versus its own history ({n}).",
                  "P/E is {v} versus its own history ({n}) - pricier than usual."),
    "pb_vs_avg": ("P/B is {v} versus its own history ({n}).",
                  "P/B is {v} versus its own history ({n}).",
                  "P/B is {v} versus its own history ({n}) - pricier than usual."),
    "peg_vs_avg": ("PEG is {v} versus its own history ({n}).",
                   "PEG is {v} versus its own history ({n}).",
                   "PEG is {v} versus its own history ({n}) - growth is getting pricier."),
    "nim": ("Healthy net interest margin of {v} (on average assets).",
            "Net interest margin of {v} (on average assets).",
            "Thin net interest margin of {v} (on average assets)."),
    "roa": ("Return on assets of {v} - strong for a lender.",
            "Return on assets of {v}.",
            "Return on assets is weak at {v}."),
    "gnpa": ("Gross bad loans are low at {v} ({n}).",
             "Gross bad loans are {v} ({n}).",
             "Gross bad loans are high at {v} ({n})."),
    "nnpa": ("Net bad loans after provisions are just {v}.",
             "Net bad loans after provisions are {v}.",
             "Net bad loans after provisions are high at {v}."),
    "car": ("Well capitalised with CAR of {v}.",
            "Capital adequacy of {v} - adequate.",
            "Capital adequacy is thin at {v}."),
}


def fmt_money(v: Optional[float], currency: str) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "n/a"
    sign = "-" if v < 0 else ""
    a = abs(v)
    if currency == "INR":
        cr = a / 1e7
        return f"{sign}₹{cr:,.0f} Cr" if cr >= 100 else f"{sign}₹{cr:,.1f} Cr"
    sym = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}.get(currency, currency + " ")
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if a >= div:
            return f"{sign}{sym}{a / div:,.2f}{suf}"
    return f"{sign}{sym}{a:,.0f}"


def fmt_value(m: Metric, currency: str = "") -> str:
    v = m.value
    if v is None:
        return "n/a"
    if isinstance(v, float) and math.isinf(v):
        return "no interest cost" if m.key == "interest_coverage" else "n/a"
    if m.unit == "%":
        if m.key.endswith("_vs_avg"):
            return f"{v:+.0f}%"
        return f"{v:.1f}%"
    if m.unit == "x":
        return f"{v:.2f}x"
    if m.unit == "count":
        return f"{v:.1f}/5"
    if m.unit == "money":
        return fmt_money(v, currency)
    return f"{v:.2f}"


def sentence(m: Metric, currency: str = "") -> str:
    t = TEMPLATES.get(m.key)
    if m.flag == "unverified":
        return (f"{m.label} works out to {fmt_value(m, currency)}, but the data sources disagree on an input, "
                "so it is not scored.")
    if not t:
        return f"{m.label}: {fmt_value(m, currency)}."
    idx = {"good": 0, "ok": 1, "bad": 2}.get(m.flag, 1)
    v = fmt_value(m, currency)
    if m.key.endswith("_vs_avg") and m.value is not None:
        v = f"{abs(m.value):.0f}% {'above' if m.value > 0 else 'below'}"
        t = tuple(s.replace("is {v} versus", "is {v}") for s in t)
    return t[idx].format(v=v, n=m.note)


def rating_word(score: Optional[float]) -> str:
    if score is None:
        return "Not rated"
    if score >= 8:
        return "Strong"
    if score >= 6.5:
        return "Good"
    if score >= 4.5:
        return "Average"
    if score >= 3:
        return "Weak"
    return "Poor"


def category_summary(cat: str, a: Assessment, currency: str) -> str:
    score = a.category_scores.get(cat)
    name = CATEGORY_NAMES.get(cat, cat)
    members = [m for m in a.metrics.values() if m.category == cat and m.score is not None]
    if score is None or not members:
        return f"**{name}** - not rated (no data). This looks at {CATEGORY_WHAT.get(cat, '')}."
    members.sort(key=lambda m: -abs(m.score - 5))   # most decisive metrics first
    detail = " ".join(sentence(m, currency) for m in members[:2])
    return f"**{name}: {rating_word(score)} ({score:.1f}/10).** {detail}"
