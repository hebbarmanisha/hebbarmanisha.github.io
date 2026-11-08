"""Markdown renderer."""
from __future__ import annotations

from pathlib import Path

from .content import FLAG_ICON, ReportContent, money_unit


def _table(header: list[str], rows: list[list[str]], align: str = "") -> str:
    def esc(s):
        return str(s).replace("|", "\\|")
    out = ["| " + " | ".join(esc(h) for h in header) + " |"]
    out.append("|" + "|".join((":---" if i == 0 else "---:") if not align else align[i] for i in range(len(header))) + "|")
    out += ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def render(rc: ReportContent, out_path: Path, currency: str) -> Path:
    L: list[str] = []
    L.append(f"# {rc.title}")
    L.append(f"*{rc.subtitle} · generated {rc.generated}*\n")
    L.append("> **Not investment advice.** Automated analysis of public data - see the disclaimer at the end.\n")
    L.append("\U0001F577️ **[Watch the spider pick the key signals](spider.html)** (animated, opens in a browser)\n")

    L.append("## Verdict")
    L.append(f"### {rc.verdict} — overall score {rc.overall}")
    if rc.verdict_note:
        L.append(f"*Note: {rc.verdict_note}.*")
    L.append("\n**Top reasons**")
    L += [f"- {s}" for s in rc.strengths] or ["- No metric scored in the 'good' band."]
    L.append("\n**Red flags**")
    if rc.red_flags:
        badge = {"critical": "⛔ critical", "warning": "⚠️ warning"}
        L += [f"- {badge.get(sev, sev)}: {t}" for sev, t in rc.red_flags]
    else:
        L.append("- None triggered.")
    if rc.weaknesses:
        L.append("\n**Weak spots**")
        L += [f"- {s}" for s in rc.weaknesses]

    L.append("\n## Business overview")
    L.append(rc.overview_text + "\n")
    L.append(_table(["", ""], [[k, v] for k, v in rc.facts], align=[":---", ":---"]))

    L.append("\n## Health summary")
    L += [f"- {p}" for p in rc.health]

    L.append("\n## Scorecard")
    L.append(_table(["Category", "Weight", "Score /10", "Rating"], rc.scorecard))

    L.append("\n## Key ratios")
    rows = [[r["category"], r["metric"], r["value"], r["note"], r["trend"], FLAG_ICON.get(r["flag"], r["flag"]),
             r["score"]] for r in rc.ratio_rows]
    L.append(_table(["Category", "Metric", "Value", "Detail", "3y trend", "Flag", "Score"], rows,
                    align=[":---", ":---", "---:", ":---", ":---", ":---", "---:"]))

    L.append("\n## Trends")
    for title, p in rc.charts:
        L.append(f"![{title}](charts/{p.name})\n")

    L.append(f"\n## Financial history ({money_unit(currency)} unless stated)")
    L.append(_table(rc.history_header, rc.history_rows))

    L.append("\n## Data & method notes")
    L.append("**Sources by field**")
    L += [f"- *{s}*: {f}" for s, f in rc.sources]
    if rc.warnings:
        L.append("\n**Data warnings**")
        L += [f"- {w}" for w in rc.warnings]
    L.append("\n**Method**")
    L += [f"- {n}" for n in rc.method_notes]

    L.append("\n## Disclaimer")
    L.append(rc.disclaimer)
    out_path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return out_path
