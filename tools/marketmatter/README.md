# Inverika Market Matter

A daily sweep of the Indian stock market, built by Manisha Hebbar for Inverika.

Every weekday after the NSE close, a GitHub Action runs `sweep.py`, which:

1. **Collects the day's numbers** from Yahoo Finance: Nifty 50, Sensex, Nifty Bank, Midcap and India VIX;
   11 sector indices; all 50 Nifty stocks; the previous US session (S&P 500, Nasdaq); Asia and Europe;
   Brent crude, gold, silver, USD/INR, the US 10-year yield and the dollar index.
2. **Reads the day's market headlines** from Economic Times, Mint, Business Standard, Hindu BusinessLine
   and a Google News search for Sensex/Nifty.
3. **Explains the move.** Each signal that moved beyond a set threshold becomes a "driver": sector leaders,
   market breadth (broad or narrow), big single-stock moves, global cues, crude, gold, the rupee, US yields,
   volatility and foreign-flow news. Each driver states its numbers, why it matters for Indian stocks, and
   links the headlines (published around the session) that mention it.
4. **Publishes** `library/marketmatter/latest.json`, one file per trading day under `sweeps/`, and an
   `index.json` archive list. The website reads these files directly.

The thresholds are fixed in code (for example, crude counts when Brent moves 1% or more), so every
explanation can be traced to a rule and a number. Drivers describe what moved alongside the market;
they are not proof of cause. Not investment advice.

## Run it yourself

```bash
pip install -r tools/marketmatter/requirements.txt
python tools/marketmatter/sweep.py --out library/marketmatter
```

The Nifty 50 member list comes from `tools/finspider/constituents.json`, which finspider refreshes weekly.
