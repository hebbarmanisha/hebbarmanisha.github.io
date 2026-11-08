"""Pure ratio functions.

Conventions:
- Inputs may be None or NaN; any missing input returns None.
- Percent-style results (ROE, margins, CAGR, ...) are returned as percents (23.5 means 23.5%).
- A ratio that is meaningless for the inputs (e.g. ROE with negative equity) returns None.
"""
from __future__ import annotations

import math
from typing import Iterable, Optional

Num = Optional[float]


def _ok(*xs) -> bool:
    for x in xs:
        if x is None:
            return False
        try:
            if math.isnan(x):
                return False
        except TypeError:
            return False
    return True


def safe_div(a: Num, b: Num) -> Num:
    if not _ok(a, b) or b == 0:
        return None
    return a / b


# ---------- liquidity ----------
def current_ratio(current_assets: Num, current_liabilities: Num) -> Num:
    if not _ok(current_assets, current_liabilities) or current_liabilities <= 0:
        return None
    return current_assets / current_liabilities


def quick_ratio(current_assets: Num, inventory: Num, current_liabilities: Num) -> Num:
    """(Current assets - inventory) / current liabilities. Missing inventory counts as 0."""
    if not _ok(inventory):
        inventory = 0.0
    if not _ok(current_assets, current_liabilities) or current_liabilities <= 0:
        return None
    return (current_assets - inventory) / current_liabilities


# ---------- leverage ----------
def debt_to_equity(total_debt: Num, total_equity: Num) -> Num:
    if not _ok(total_debt, total_equity) or total_equity <= 0:
        return None
    return total_debt / total_equity


def interest_coverage(ebit: Num, interest_expense: Num) -> Num:
    """EBIT / interest. Zero interest with positive EBIT means no debt burden -> inf."""
    if not _ok(ebit, interest_expense):
        return None
    interest = abs(interest_expense)
    if interest == 0:
        return math.inf if ebit > 0 else None
    return ebit / interest


# ---------- returns & margins ----------
def roe(net_income: Num, equity: Num) -> Num:
    if not _ok(net_income, equity) or equity <= 0:
        return None
    return net_income / equity * 100


def roce(ebit: Num, capital_employed: Num) -> Num:
    if not _ok(ebit, capital_employed) or capital_employed <= 0:
        return None
    return ebit / capital_employed * 100


def roa(net_income: Num, total_assets: Num) -> Num:
    if not _ok(net_income, total_assets) or total_assets <= 0:
        return None
    return net_income / total_assets * 100


def nim(net_interest_income: Num, earning_assets: Num) -> Num:
    """Net interest margin, %. finspider passes average total assets as a proxy."""
    if not _ok(net_interest_income, earning_assets) or earning_assets <= 0:
        return None
    return net_interest_income / earning_assets * 100


def margin(numerator: Num, revenue: Num) -> Num:
    if not _ok(numerator, revenue) or revenue <= 0:
        return None
    return numerator / revenue * 100


def net_margin(net_income: Num, revenue: Num) -> Num:
    return margin(net_income, revenue)


def operating_margin(operating_income: Num, revenue: Num) -> Num:
    return margin(operating_income, revenue)


# ---------- growth ----------
def cagr(start: Num, end: Num, years: Num) -> Num:
    """Compound annual growth rate, %. Undefined when either end is <= 0."""
    if not _ok(start, end, years) or years <= 0 or start <= 0 or end <= 0:
        return None
    return ((end / start) ** (1 / years) - 1) * 100


# ---------- cash flow ----------
def ocf_to_net_profit(ocf: Num, net_income: Num) -> Num:
    if not _ok(ocf, net_income) or net_income <= 0:
        return None
    return ocf / net_income


def free_cash_flow(ocf: Num, capex: Num) -> Num:
    """OCF minus capital expenditure. Capex sign is ignored (filings report it either way)."""
    if not _ok(ocf, capex):
        return None
    return ocf - abs(capex)


# ---------- valuation ----------
def pe(price: Num, eps: Num) -> Num:
    if not _ok(price, eps) or eps <= 0 or price <= 0:
        return None
    return price / eps


def pb(price: Num, book_value_per_share: Num) -> Num:
    if not _ok(price, book_value_per_share) or book_value_per_share <= 0 or price <= 0:
        return None
    return price / book_value_per_share


def peg(pe_ratio: Num, eps_growth_pct: Num) -> Num:
    if not _ok(pe_ratio, eps_growth_pct) or eps_growth_pct <= 0 or pe_ratio <= 0:
        return None
    return pe_ratio / eps_growth_pct


def average(values: Iterable[Num]) -> Num:
    vals = [v for v in values if _ok(v) and not math.isinf(v)]
    if not vals:
        return None
    return sum(vals) / len(vals)


def premium_vs_average(current: Num, avg: Num) -> Num:
    """% premium (+) or discount (-) of current vs its average."""
    if not _ok(current, avg) or avg <= 0:
        return None
    return (current / avg - 1) * 100


def avg_pair(a: Num, b: Num) -> Num:
    """Average of opening and closing balances; falls back to whichever exists."""
    if _ok(a) and _ok(b):
        return (a + b) / 2
    if _ok(b):
        return b
    if _ok(a):
        return a
    return None
