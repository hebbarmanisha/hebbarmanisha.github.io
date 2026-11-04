/*
  ============================================================
  ALL THE SITE'S CONTENT LIVES IN THIS FILE.
  ============================================================
  To add something new, copy an existing entry, paste it below,
  and change the text. The page builds itself from this file.

  - New paper:   add an entry to `papers` and put its PDF in /papers
  - New post:    add an entry to `writing` (newest first)
  - Anything else (internship, certification, project, award):
                 add an entry to `more`. The "More" section appears
                 as soon as it has at least one entry.

  Charts are optional. Three kinds are supported:
    { type: "bars",    title, caption, unit, rows: [{ label, value }] }
    { type: "grouped", title, caption, unit, series: ["A","B"],
                       groups: [{ label, values: [1, 2] }] }
    { type: "matrix",  title, caption, columns: ["A","B"],
                       rows: [{ label, values: [1, 2] }] }
  ============================================================
*/

window.SITE = {
  profile: {
    name: "Manisha Hebbar",
    headline: "Finance research & writing",
    roles: ["B.Com (Hons) Financial Management", "US CMA candidate"],
    institution: "MYCAS College of Professional Studies, Mysuru",
    location: "Mysuru, India",
    bio: "I study how people should invest, not just what they should buy. My research compares investment strategies across real market cycles using historical fund data, and I write a Substack that explains finance in plain language.",
    email: "hebbarmanisha@gmail.com",
    links: [
      { label: "Substack", url: "https://manishahebbar.substack.com/" }
      // { label: "LinkedIn", url: "https://www.linkedin.com/in/your-handle" },
    ],
    focus: ["Mutual funds", "Investment strategy", "Portfolio analysis", "Personal finance"]
  },

  papers: [
    {
      id: "lumpsum-vs-stp",
      title: "Mutual Fund Performance Analysis: Lump Sum vs. Monthly STP vs. Daily STP Across Time Periods",
      shortTitle: "Lump Sum vs. STP",
      kind: "Research paper",
      date: "2025",
      area: "Investments",
      authors: ["Manisha Hebbar", "Eshaan S", "Dr. Ramacharan G"],
      institution: "MYCAS College of Professional Studies, Mysuru",
      pdf: "papers/lumpsum-vs-stp.pdf",
      question: "Should an investor put ₹25,000 into an equity fund all at once, or move it in gradually through a monthly or daily Systematic Transfer Plan?",
      headline: "No strategy wins everywhere. Monthly STP won 12 of 27 scenarios, lump sum 10, and daily STP 5. The market phase decided the winner more than anything else.",
      abstract: "Mutual funds have become a leading investment medium in India, driven by retail participation and the need for diversification, liquidity and professional management. This study compares lump sum, monthly STP and daily STP investing using actual historical NAVs from HDFC, SBI and ICICI Prudential across large-, mid- and small-cap funds, in three market cycles: pre-COVID, COVID and post-COVID. No strategy performs best in every situation; results depend on fund type, market conditions and investment frequency. The paper offers evidence-based guidance on matching investment approach to market conditions.",
      stats: [
        { value: "27", label: "scenarios tested per method" },
        { value: "44.4%", label: "win rate for monthly STP, the top strategy" },
        { value: "8 of 9", label: "recovery-phase scenarios won by monthly STP" },
        { value: "23.4%", label: "average edge of the volatility-adaptive model over static strategies" }
      ],
      findings: [
        "No single method is best in all conditions. Monthly STP came first in 12 of 27 scenarios (44.4%), lump sum in 10 (37%) and daily STP in 5 (18.5%).",
        "Market phase mattered most. In the COVID crash and rebound, lump sum won 5 of 9 scenarios. In the post-COVID recovery, monthly STP won 8 of 9.",
        "The fund house changed the answer. HDFC funds favoured lump sum (6 of 9), while ICICI Prudential and SBI favoured monthly STP (5 of 9 each).",
        "Mid-cap funds suited monthly STP (5 of 9). Small-cap results were spread across all three methods, which suggests they are the most sensitive to timing.",
        "The paper proposes a volatility-adaptive model: lump sum when volatility is high, monthly STP when it is moderate, and either when it is low. Tested against static strategies, it came out ahead by an average of 23.4%."
      ],
      method: [
        { label: "Design", value: "Quantitative, comparative" },
        { label: "Data", value: "Historical daily NAVs (advisorkhoj.com)" },
        { label: "Funds", value: "HDFC, SBI, ICICI Prudential · large, mid and small cap" },
        { label: "Periods", value: "FY 2018-19 (pre-COVID), FY 2020-21 (COVID), FY 2022-23 (post-COVID)" },
        { label: "Setup", value: "₹25,000 as a lump sum on 1 April, or parked in debt and moved ₹2,083 a month or ₹100 a trading day" }
      ],
      charts: [
        {
          type: "bars",
          title: "Scenarios won, out of 27",
          caption: "Each scenario is one fund house, one fund type and one market phase.",
          unit: "",
          rows: [
            { label: "Monthly STP", value: 12 },
            { label: "Lump sum", value: 10 },
            { label: "Daily STP", value: 5 }
          ]
        },
        {
          type: "matrix",
          title: "Wins by market phase",
          caption: "Out of 9 scenarios per phase. The strongest method in each row is outlined.",
          columns: ["Lump sum", "Monthly STP", "Daily STP"],
          rows: [
            { label: "Before COVID", values: [4, 4, 1] },
            { label: "During COVID", values: [5, 0, 4] },
            { label: "After COVID", values: [1, 8, 0] }
          ]
        },
        {
          type: "matrix",
          title: "Wins by fund house",
          caption: "Out of 9 scenarios per fund house.",
          columns: ["Lump sum", "Monthly STP", "Daily STP"],
          rows: [
            { label: "HDFC", values: [6, 2, 1] },
            { label: "ICICI Prudential", values: [1, 5, 3] },
            { label: "SBI", values: [3, 5, 1] }
          ]
        }
      ],
      tags: ["Scenario analysis", "Historical NAV data", "Rupee-cost averaging", "Market cycles"]
    },

    {
      id: "multi-asset-funds",
      title: "A Comparative Study on the Portfolios of Top 10 Multi-Asset Allocation Funds in India",
      shortTitle: "Multi-Asset Allocation Funds",
      kind: "Live project",
      date: "October 2025",
      area: "Portfolio analysis",
      authors: ["Manisha Hebbar"],
      supervisors: ["Dr. Ramacharan G", "Ms. Harshitha S"],
      institution: "MYCAS College of Professional Studies, Mysuru",
      pdf: "papers/mf-live-project.pdf",
      question: "Do multi-asset allocation funds (MAAFs), which must hold at least 10% each in equity, debt and gold or commodities, earn their place against pure equity, debt, gold and silver funds?",
      headline: "MAAFs delivered steady 12–21% returns and stayed positive when pure equity fell, but could not match gold and silver at the peak of the 2024-25 rally.",
      abstract: "Multi-asset allocation funds surged in popularity in India in 2024-25 as investors looked for a safer alternative to pure equity during a volatile year. This project analyses the returns and asset allocation of the top 10 MAAFs as of September 2025, then compares MAAFs from ICICI, ABSL and HDFC against the same fund houses' standalone equity, debt, gold and silver funds over 1, 3, 5 and 10 years and since inception.",
      stats: [
        { value: "10", label: "multi-asset funds compared" },
        { value: "25.95%", label: "top 1-year return (Quant MAAF)" },
        { value: "12.68%", label: "ICICI MAAF 1-year return, while pure equity lost 2.07%" },
        { value: "12–21%", label: "typical MAAF return range across periods" }
      ],
      findings: [
        "MAAFs consistently returned 12–21%, smoothing out the extreme highs and lows of single-asset funds.",
        "In the latest year, ICICI's MAAF returned 12.68% while a pure equity fund returned −2.07%. The MAAF had cut equity and added commodities and debt.",
        "Gold and silver ETFs beat MAAFs during the 2024-25 metals rally (Nippon Gold ETF 53.54%, silver ETF 51.51% in one year), but with much higher volatility.",
        "Funds that actively rebalanced, such as raising gold exposure at the right time, outperformed funds that kept a fixed balanced mix.",
        "Recommendation: hold MAAFs as the core of a portfolio, and use smaller positions in pure equity, gold, silver or debt funds for tactical bets on clear trends."
      ],
      method: [
        { label: "Design", value: "Descriptive and analytical" },
        { label: "Data", value: "Fund factsheets, AMC disclosures, SEBI reports, financial portals" },
        { label: "Sample", value: "Top 10 MAAFs (Sept 2025), plus ICICI, ABSL and HDFC single-asset funds" },
        { label: "Period", value: "FY 2024-25, with 1, 3, 5, 10-year and since-inception returns" },
        { label: "Benchmarks", value: "Equity, corporate bond, gold ETF and silver ETF funds" }
      ],
      charts: [
        {
          type: "grouped",
          title: "ICICI Pru MAAF vs. a pure equity fund",
          caption: "Annualised returns by holding period. The MAAF held up when equity turned negative.",
          unit: "%",
          series: ["ICICI Pru MAAF", "Pure equity (Quant)"],
          groups: [
            { label: "1 year", values: [12.68, -2.07] },
            { label: "3 years", values: [20, 12] },
            { label: "5 years", values: [25, 22.86] }
          ]
        },
        {
          type: "bars",
          title: "1-year returns of funds in the study",
          caption: "Metals led the 2024-25 rally. MAAFs sat between metals and equity.",
          unit: "%",
          rows: [
            { label: "Nippon Gold ETF", value: 53.54 },
            { label: "Silver ETF", value: 51.51 },
            { label: "Quant MAAF (top MAAF)", value: 25.95 },
            { label: "ICICI Pru MAAF", value: 12.68 },
            { label: "ABSL Corporate Bond", value: 7.91 },
            { label: "Quant pure equity", value: -2.07 }
          ]
        }
      ],
      tags: ["Asset allocation", "Fund comparison", "Gold & silver ETFs", "Risk-adjusted returns"]
    }
  ],

  substack: {
    name: "Manisha Hebbar on Substack",
    url: "https://manishahebbar.substack.com/",
    tagline: "It all started with my name having the word \"money\" in it. 21, obsessed with finance and always curious about the why of things."
  },

  // Newest first. Date format: YYYY-MM-DD
  writing: [
    {
      title: "Beyond Mutual Funds: What Is an SIF, and Is It Right for You?",
      subtitle: "A simple guide to the investment options sitting between your mutual fund and the big leagues.",
      date: "2026-10-09",
      url: "https://manishahebbar.substack.com/p/beyond-mutual-funds-what-is-an-sif",
      topic: "Investing"
    },
    {
      title: "Why the Market Had Such a Rough Day Yesterday",
      subtitle: "Sensex hits a 2026 low and oil crosses $100. What's actually behind it, explained so you can explain it to others.",
      date: "2026-10-02",
      url: "https://manishahebbar.substack.com/p/why-the-market-had-such-a-rough-day",
      topic: "Markets"
    },
    {
      title: "Does CERN's Collider Actually Move the Stock Market?",
      subtitle: "The internet loves this theory. Let's test it against the facts.",
      date: "2026-08-21",
      url: "https://manishahebbar.substack.com/p/does-cerns-collider-actually-move",
      topic: "Markets"
    },
    {
      title: "Finance Isn't Complicated, It's Just Badly Explained.",
      subtitle: "Six things every twenty-something should understand about money. No jargon, just real life.",
      date: "2026-08-05",
      url: "https://manishahebbar.substack.com/p/finance-isnt-complicated-its-just",
      topic: "Personal finance"
    },
    {
      title: "What Actually Happens Inside a Mutual Fund House",
      subtitle: "It's not the numbers. It's the news, the psychology, and the people who never get credit.",
      date: "2026-07-08",
      url: "https://manishahebbar.substack.com/p/what-actually-happens-inside-a-mutual",
      topic: "Industry"
    },
    {
      title: "From KYC Forms to CMA Books to... What Next?",
      subtitle: "Finance internships, exam prep, a cake that didn't rise the first time, and one question still unanswered.",
      date: "2026-07-06",
      url: "https://manishahebbar.substack.com/p/from-kyc-forms-to-cma-books-to-what",
      topic: "Career"
    }
  ],

  // Internships, certifications, projects, awards... Example:
  // { kind: "Internship", title: "Finance Intern", org: "Company name",
  //   date: "Jun–Aug 2026", summary: "What you did, in one or two sentences.",
  //   url: "https://optional-link" }
  more: []
};
