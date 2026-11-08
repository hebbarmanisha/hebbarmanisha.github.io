# finspider library builder

Run weekly by `.github/workflows/finspider-library.yml` to refresh `library/` (Nifty 50 + S&P 100 reports for the dashboard search).

    pip install -r tools/finspider/requirements.txt
    python tools/finspider/build_library.py --out library
