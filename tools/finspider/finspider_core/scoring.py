"""0-10 scoring, red flags and the long-term verdict. All cut-offs come from config.yaml."""
from __future__ import annotations

import math
from typing import Any, Optional

from . import explain
from .model import Assessment, CompanyData, Metric, RedFlag

VERDICTS = ["Avoid", "Hold", "Accumulate", "Strong Accumulate"]


def score_value(value: Optional[float], good: float, bad: float) -> Optional[float]:
    """Linear 0-10 between `bad` (0) and `good` (10), clamped. Works in either direction."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if math.isinf(value):
        higher_better = good > bad
        return 10.0 if (value > 0) == higher_better else 0.0
    s = (value - bad) / (good - bad) * 10
    return max(0.0, min(10.0, s))


def flag_for(score: Optional[float], good_at: float, bad_below: float) -> str:
    if score is None:
        return "n/a"
    if score >= good_at:
        return "good"
    if score < bad_below:
        return "bad"
    return "ok"


def weighted_mean(pairs: list[tuple[Optional[float], float]]) -> Optional[float]:
    """Mean of (value, weight) pairs, skipping missing values and re-normalising weights."""
    usable = [(v, w) for v, w in pairs if v is not None and w > 0]
    total = sum(w for _, w in usable)
    if total == 0:
        return None
    return sum(v * w for v, w in usable) / total


def score_metrics(metrics: dict[str, Metric], cfg: dict, profile: str) -> None:
    th, fl = cfg["thresholds"], cfg["flags"]
    for cname, cat in cfg["profiles"][profile].items():
        for key in cat["metrics"]:
            m = metrics.get(key)
            if m is None:
                continue
            m.category = cname
            if not m.verified:          # sources disagree on an input: show it, never score it
                m.score, m.flag = None, "unverified"
                continue
            m.score = score_value(m.value, th[key]["good"], th[key]["bad"])
            m.flag = flag_for(m.score, fl["good_at_or_above"], fl["bad_below"])


def category_scores(metrics: dict[str, Metric], cfg: dict, profile: str) -> dict[str, Optional[float]]:
    out = {}
    for cname, cat in cfg["profiles"][profile].items():
        pairs = [(metrics[k].score if k in metrics else None, float(w)) for k, w in cat["metrics"].items()]
        out[cname] = weighted_mean(pairs)
    return out


def coverage(metrics: dict[str, Metric], cfg: dict, profile: str) -> float:
    keys = [k for cat in cfg["profiles"][profile].values() for k in cat["metrics"]]
    have = sum(1 for k in keys if k in metrics and metrics[k].score is not None)
    return have / len(keys) if keys else 0.0


def find_red_flags(c: CompanyData, metrics: dict[str, Metric], extras: dict[str, Any],
                   cfg: dict, profile: str) -> list[RedFlag]:
    rf = cfg["red_flags"]
    flags: list[RedFlag] = []
    a = c.annual
    n = int(cfg["data"]["cagr_years"])

    def val(k):
        m = metrics.get(k)
        return m.value if m else None

    def add(key, text):
        if key in rf:
            flags.append(RedFlag(key, rf[key].get("severity", "warning"), text))

    ni = a["net_income"].dropna()
    if not ni.empty and ni.iloc[-1] < 0:
        add("net_loss_latest_year", f"Made a net loss in FY{ni.index[-1]}.")
    eq = a["total_equity"].dropna()
    if not eq.empty and eq.iloc[-1] <= 0:
        add("negative_equity", "Shareholders' equity is negative (liabilities exceed assets).")

    if profile != "financial":
        ocf = a["ocf"].dropna().tail(n)
        neg = int((ocf < 0).sum())
        if "negative_ocf_years" in rf and neg >= rf["negative_ocf_years"].get("min_years", 2):
            add("negative_ocf_years", f"Operating cash flow was negative in {neg} of the last {len(ocf)} years.")
        v = val("ocf_to_net_profit")
        if v is not None and "low_cash_conversion" in rf and v < rf["low_cash_conversion"]["below"]:
            add("low_cash_conversion", f"Only {v:.2f}x of reported profit turned into operating cash "
                                       f"over recent years - earnings quality is questionable.")
        v = val("debt_to_equity")
        if v is not None and "high_debt_to_equity" in rf and v > rf["high_debt_to_equity"]["above"]:
            add("high_debt_to_equity", f"Debt is {v:.1f}x equity - heavily leveraged.")
        v = val("interest_coverage")
        if v is not None and "low_interest_coverage" in rf and v < rf["low_interest_coverage"]["below"]:
            add("low_interest_coverage", f"Operating profit covers interest only {v:.1f}x.")

    for key, metric, what in (("revenue_decline", "revenue_cagr", "Revenue"),
                              ("profit_decline", "profit_cagr", "Net profit")):
        v = val(metric)
        if v is not None and key in rf and v < rf[key]["below"]:
            add(key, f"{what} has shrunk {abs(v):.1f}% a year ({metrics[metric].note}).")
    v = val("pe_vs_avg")
    if v is not None and "expensive_vs_history" in rf and v > rf["expensive_vs_history"]["above"]:
        add("expensive_vs_history", f"P/E is {v:.0f}% above its own recent average.")

    if profile == "financial":
        v = val("gnpa")
        if v is not None and "high_gnpa" in rf and v > rf["high_gnpa"]["above"]:
            add("high_gnpa", f"Gross NPAs are high at {v:.2f}% of loans.")
        v = val("nnpa")
        if v is not None and "high_nnpa" in rf and v > rf["high_nnpa"]["above"]:
            add("high_nnpa", f"Net NPAs are high at {v:.2f}% of loans.")
        d = extras.get("gnpa_change_4q")
        if d is not None and "rising_gnpa" in rf and d > rf["rising_gnpa"]["above"]:
            add("rising_gnpa", f"Gross NPA rose {d:.2f} percentage points over the last 4 quarters.")
        v = val("car")
        if v is not None and "low_car" in rf and v < rf["low_car"]["below"]:
            add("low_car", f"Capital adequacy is thin at {v:.1f}%.")
    return flags


def decide_verdict(overall: Optional[float], flags: list[RedFlag], cov: float, cfg: dict,
                   missing_major: Optional[list[str]] = None) -> tuple[str, str]:
    v = cfg["verdict"]
    if overall is None:
        return "Hold", "Not enough data to score; treat as unrated."
    if overall >= v["strong_accumulate"]:
        verdict = "Strong Accumulate"
    elif overall >= v["accumulate"]:
        verdict = "Accumulate"
    elif overall >= v["hold"]:
        verdict = "Hold"
    else:
        verdict = "Avoid"
    notes = []
    crit = sum(1 for f in flags if f.severity == "critical")
    cap = None
    if crit >= 2:
        cap = v.get("cap_two_critical")
    elif crit == 1:
        cap = v.get("cap_one_critical")
    if cap in VERDICTS and VERDICTS.index(verdict) > VERDICTS.index(cap):
        notes.append(f"capped from {verdict} to {cap} because of {crit} critical red flag(s)")
        verdict = cap
    cap = v.get("cap_missing_major_category")
    if missing_major and cap in VERDICTS and VERDICTS.index(verdict) > VERDICTS.index(cap):
        notes.append(f"capped from {verdict} to {cap} because {', '.join(missing_major)} could not be rated")
        verdict = cap
    if cov < v.get("min_coverage", 0.5):
        notes.append(f"low confidence: only {cov:.0%} of scored metrics had data")
    return verdict, "; ".join(notes)


def _spread(ms: list[Metric], cats: dict, weights: dict, best: bool, n: int = 4) -> list[Metric]:
    """Pick up to n metrics, one per category first (heaviest categories first), so the
    reasons cover different aspects of the business rather than two near-identical ratios."""
    key = (lambda m: (-m.score, -weights.get(m.category, 0))) if best else \
          (lambda m: (m.score, -weights.get(m.category, 0)))
    ms = sorted(ms, key=key)
    picked, seen = [], set()
    for m in ms:
        if m.category not in seen:
            picked.append(m)
            seen.add(m.category)
    for m in ms:
        if m not in picked:
            picked.append(m)
    return picked[:n]


def assess(c: CompanyData, metrics: dict[str, Metric], extras: dict[str, Any], cfg: dict,
           profile: str) -> Assessment:
    score_metrics(metrics, cfg, profile)
    cats = category_scores(metrics, cfg, profile)
    weights = {k: float(v["weight"]) for k, v in cfg["profiles"][profile].items()}
    overall = weighted_mean([(cats[k], weights[k]) for k in cats])
    cov = coverage(metrics, cfg, profile)
    flags = find_red_flags(c, metrics, extras, cfg, profile)
    total_w = sum(weights.values()) or 1
    major = float(cfg["verdict"].get("major_category_weight", 0.2))
    missing_major = [explain.CATEGORY_NAMES.get(k, k).lower() for k, s in cats.items()
                     if s is None and weights[k] / total_w >= major]
    verdict, note = decide_verdict(overall, flags, cov, cfg, missing_major)

    scored = [m for m in metrics.values() if m.score is not None and m.category]
    best = _spread([m for m in scored if m.flag == "good"], cats, weights, best=True)
    worst = _spread([m for m in scored if m.flag == "bad"], cats, weights, best=False)
    return Assessment(
        profile=profile, metrics=metrics, category_scores=cats, category_weights=weights,
        overall=overall, coverage=cov, verdict=verdict, verdict_note=note,
        strengths=[explain.sentence(m, c.currency) for m in best],
        weaknesses=[explain.sentence(m, c.currency) for m in worst],
        red_flags=flags,
    )
