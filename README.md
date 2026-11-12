# hebbarmanisha.github.io

Personal research site of Manisha Hebbar: finance papers, writing and projects.
Live at https://hebbarmanisha.github.io/

## Folder layout

```
hebbarmanisha.github.io/
├── index.html                  The site (layout, styles, rendering)
├── content.js                  ALL site content: profile, papers, projects, writing
├── serve.ps1                   Local preview server: powershell -File serve.ps1
├── papers/                     Paper PDFs linked from content.js
├── projects/
│   └── finspider/              FinSpider web component shown on the project page
├── library/                    FinSpider company library (generated weekly)
│   ├── index.json              List of every covered company
│   └── reports/*.json          One report per company (Nifty 50 + S&P 100)
├── tools/
│   └── finspider/              FinSpider Python tool (see its README)
└── .github/workflows/
    └── finspider-library.yml   Rebuilds library/ every Monday and commits it
```

## Editing the site

Everything you see on the site comes from `content.js`. The instructions at the top of that file
explain how to add a paper, post or project.

## Preview locally

```powershell
powershell -File serve.ps1    # then open http://localhost:8765/
```

## Related repositories

- **Inverika Market Matter** (daily Indian market sweep built for Inverika):
  https://github.com/inverikacapital/market-matter. The Market Matter project page loads its live panel
  from that repository's GitHub Pages site (https://inverikacapital.github.io/market-matter/), so the panel
  only works while Pages is turned on for that repository.
