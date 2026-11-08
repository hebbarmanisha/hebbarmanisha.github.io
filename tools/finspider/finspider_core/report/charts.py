"""Static PNG trend charts (matplotlib). Light theme, since they go into print/PDF."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..model import Assessment, CompanyData  # noqa: E402

log = logging.getLogger(__name__)

# Reference palette: fixed categorical order, never cycled; max 3 series per chart.
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
AXIS = "#c3c2b7"

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans", "sans-serif"],
    "font.size": 9,
    "axes.facecolor": SURFACE,
    "figure.facecolor": SURFACE,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK_2,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "axes.titlecolor": INK,
    "axes.titlesize": 11,
    "axes.titleweight": "semibold",
    "axes.titlelocation": "left",
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "legend.frameon": False,
    "legend.fontsize": 8.5,
    "legend.labelcolor": INK_2,
})


def _money_scale(currency: str, values: list[float]) -> tuple[float, str]:
    if currency == "INR":
        return 1e7, "₹ Cr"
    m = max((abs(v) for v in values if v is not None and not np.isnan(v)), default=0)
    if m >= 1e11:
        return 1e9, f"{currency} bn"
    return 1e6, f"{currency} mn"


def _legend(ax, n: int):
    """Legend above the plot, right-aligned on the subtitle line, so it never covers data."""
    if n > 1:
        ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=n, borderaxespad=0.2,
                  handlelength=1.4, columnspacing=1.2)


def _year_ticks(ax, years: list[int], x=None):
    x = years if x is None else x
    step = 1 if len(years) <= 8 else 2
    ax.set_xticks(list(x)[::-1][::step][::-1], [str(y) for y in years][::-1][::step][::-1])


_thousands = matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}")


def _new(title: str, subtitle: str = ""):
    fig, ax = plt.subplots(figsize=(7.2, 3.3), dpi=150)
    ax.set_title(title, pad=14 if subtitle else 8)
    if subtitle:
        ax.text(0, 1.02, subtitle, transform=ax.transAxes, fontsize=8.5, color=INK_2)
    ax.tick_params(length=0)
    ax.set_axisbelow(True)
    return fig, ax


def _save(fig, path: Path) -> Path:
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)
    return path


def _bars(ax, years, series: list[tuple[str, list]], scale: float):
    n = len(series)
    width = 0.8 / n
    x = np.arange(len(years))
    for i, (label, vals) in enumerate(series):
        v = np.array([np.nan if val is None else val / scale for val in vals], dtype=float)
        ax.bar(x + (i - (n - 1) / 2) * width, v, width=width * 0.92, color=SERIES[i], label=label,
               edgecolor=SURFACE, linewidth=0.8)
    ax.set_xticks(x, [str(y) for y in years])
    ax.axhline(0, color=AXIS, linewidth=0.8)
    ax.yaxis.set_major_formatter(_thousands)
    _legend(ax, n)


def _lines(ax, years, series: list[tuple[str, dict]], fmt: str = "{:.1f}%"):
    for i, (label, h) in enumerate(series):
        ys = [y for y in years if h.get(y) is not None and np.isfinite(h.get(y))]
        if not ys:
            continue
        vals = [h[y] for y in ys]
        ax.plot(ys, vals, color=SERIES[i], linewidth=2, marker="o", markersize=4.5,
                markeredgecolor=SURFACE, markeredgewidth=1.2, label=label)
        ax.annotate(fmt.format(vals[-1]), (ys[-1], vals[-1]), textcoords="offset points",
                    xytext=(6, 0), va="center", fontsize=8.5, color=INK_2)
    ax.set_xticks(years, [str(y) for y in years])
    _legend(ax, sum(1 for _, h in series if h))
    ax.margins(x=0.06)


def make_charts(c: CompanyData, a: Assessment, extras: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    charts: dict[str, Path] = {}
    df = c.annual
    years = [int(y) for y in df.index]
    hist = extras["hist"]

    def safe(name, fn):
        try:
            p = fn()
            if p:
                charts[name] = p
        except Exception as e:  # a broken chart must never break the report
            log.warning("chart %s failed: %s", name, e)

    def rev_profit():
        rev, ni = df["revenue"].tolist(), df["net_income"].tolist()
        if all(np.isnan(v) for v in rev):
            return None
        scale, unit = _money_scale(c.currency, rev)
        fig, ax = _new("Revenue and net profit", f"Fiscal years, {unit}")
        _bars(ax, years, [("Revenue", rev), ("Net profit", ni)], scale)
        return _save(fig, out_dir / "revenue_profit.png")

    def margins():
        fig, ax = _new("Margins", "% of revenue")
        _lines(ax, years, [("Operating margin", hist["operating_margin"]), ("Net margin", hist["net_margin"])])
        return _save(fig, out_dir / "margins.png")

    def returns():
        if a.profile == "financial":
            s = [("ROE", hist["roe"]), ("ROA", hist["roa"]), ("NIM", hist["nim"])]
            sub = "ROE on average equity; ROA and NIM on average total assets, %"
        else:
            s = [("ROE", hist["roe"]), ("ROCE", hist["roce"])]
            sub = "On average equity / capital employed, %"
        fig, ax = _new("Returns", sub)
        _lines(ax, years, s)
        return _save(fig, out_dir / "returns.png")

    def cash():
        if a.profile == "financial":
            return None
        ni, ocf = df["net_income"].tolist(), df["ocf"].tolist()
        fcf = [extras["fcf"].get(y) for y in years]
        if all(np.isnan(v) for v in ocf):
            return None
        scale, unit = _money_scale(c.currency, ocf)
        fig, ax = _new("Profit vs cash", f"Net profit, operating cash flow and free cash flow, {unit}")
        _bars(ax, years, [("Net profit", ni), ("Operating cash flow", ocf), ("Free cash flow", fcf)], scale)
        return _save(fig, out_dir / "cash_flow.png")

    def valuation():
        pe_h, pb_h = extras["pe_hist"], extras["pb_hist"]
        if not any(v for v in pe_h.values()) and not any(v for v in pb_h.values()):
            return None
        fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.0), dpi=150)
        for ax, (title, h, key) in zip(axes, (("P/E at fiscal year-end", pe_h, "pe"),
                                              ("P/B at fiscal year-end", pb_h, "pb"))):
            ax.set_title(title)
            ax.tick_params(length=0)
            ax.set_axisbelow(True)
            ys = [y for y in years if h.get(y)]
            if not ys:
                ax.text(0.5, 0.5, "no data", ha="center", transform=ax.transAxes, color=MUTED)
                continue
            vals = [h[y] for y in ys]
            ax.plot(ys, vals, color=SERIES[0], linewidth=2, marker="o", markersize=4.5,
                    markeredgecolor=SURFACE, markeredgewidth=1.2)
            avg = np.mean(vals[-5:])
            ax.axhline(avg, color=MUTED, linewidth=1, linestyle=(0, (4, 3)))
            ax.annotate(f"avg {avg:.1f}x", (ys[0], avg), textcoords="offset points", xytext=(0, 4),
                        fontsize=8, color=INK_2)
            now = a.metrics[key].value
            if now:
                ax.scatter([ys[-1] + 0.8], [now], color=SERIES[1], s=36, zorder=3,
                           edgecolors=SURFACE, linewidths=1.2)
                ax.annotate(f"now\n{now:.1f}x", (ys[-1] + 0.8, now), textcoords="offset points",
                            xytext=(7, 0), ha="left", va="center", fontsize=8, color=INK_2)
            _year_ticks(ax, ys)
            ax.set_xlim(ys[0] - 0.5, ys[-1] + 2.6)
            ax.set_ylim(bottom=0)
        fig.tight_layout()
        fig.savefig(out_dir / "valuation.png", facecolor=SURFACE)
        plt.close(fig)
        return out_dir / "valuation.png"

    def npa():
        q = c.quarterly_npa
        if a.profile != "financial" or q is None or q.empty:
            return None
        fig, ax = _new("Bad loans", "Gross and net NPA, % of loans, by quarter")
        labels = list(q.index)
        x = np.arange(len(labels))
        for i, (col, label) in enumerate((("gnpa_pct", "Gross NPA"), ("nnpa_pct", "Net NPA"))):
            v = q[col].astype(float).values
            if np.all(np.isnan(v)):
                continue
            ax.plot(x, v, color=SERIES[i], linewidth=2, marker="o", markersize=4.5,
                    markeredgecolor=SURFACE, markeredgewidth=1.2, label=label)
            last = np.where(~np.isnan(v))[0][-1]
            ax.annotate(f"{v[last]:.2f}%", (x[last], v[last]), textcoords="offset points", xytext=(6, 0),
                        va="center", fontsize=8.5, color=INK_2)
        step = max(1, len(labels) // 6)
        ax.set_xticks(x[::step], labels[::step])
        ax.set_ylim(bottom=0)
        _legend(ax, 2)
        ax.margins(x=0.06)
        return _save(fig, out_dir / "npa.png")

    for name, fn in (("revenue_profit", rev_profit), ("margins", margins), ("returns", returns),
                     ("cash_flow", cash), ("valuation", valuation), ("npa", npa)):
        safe(name, fn)
    return charts
