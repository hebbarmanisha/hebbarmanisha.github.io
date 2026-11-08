"""Decide which scoring profile applies."""
from __future__ import annotations

from .model import CompanyData


def is_financial(sector: str, industry: str, financial_industries: list[str]) -> bool:
    if (sector or "").lower() not in ("financial services", "financials", "financial"):
        return False
    ind = (industry or "").lower()
    return any(p.lower() in ind for p in financial_industries)


def detect_profile(company: CompanyData, cfg: dict, override: str = "auto") -> str:
    if override and override != "auto":
        return override
    info = company.info or {}
    if is_financial(info.get("sector", ""), info.get("industry", ""), cfg["sector"]["financial_industries"]):
        return "financial"
    # Screener structure is a strong hint too (deposits / NPA rows only exist for lenders)
    if company.quarterly_npa is not None and not company.quarterly_npa.empty:
        return "financial"
    if company.annual["deposits"].notna().any():
        return "financial"
    return "default"
