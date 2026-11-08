"""One call from ticker to finished analysis. Used by the CLI, the library builder and the server."""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from . import data, metrics, scoring, sector
from .cache import FileCache
from .model import Assessment, CompanyData
from .report import spider_export


@dataclass
class Analysis:
    company: CompanyData
    assessment: Assessment
    extras: dict[str, Any]
    spider: dict[str, Any]          # the widget's data (spider.json)


def analyze(ticker: str, cfg: dict, cache: FileCache, display_name: str = "",
            sector_override: str = "auto", generated: str | None = None) -> Analysis:
    company = data.load_company(ticker, cfg, cache, display_name)
    profile = sector.detect_profile(company, cfg, sector_override)
    mets, extras = metrics.compute(company, cfg, profile)
    assessment = scoring.assess(company, mets, extras, cfg, profile)
    spider = spider_export.build_spider_data(company, assessment, cfg, generated or dt.date.today().isoformat())
    return Analysis(company, assessment, extras, spider)
