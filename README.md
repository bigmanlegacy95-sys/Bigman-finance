# StockScope

Enter a ticker, get ratios, red flags, a strict rating with confidence level, and a plain-language AI analysis.
Zero budget stack: Python, Streamlit, Yahoo Finance (yfinance), Gemini free tier.

## Run
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # add your free Gemini key
streamlit run app.py
```

## Deploy free
Push to GitHub, then deploy on Streamlit Community Cloud. Add GEMINI_API_KEY under Secrets.

## Structure
- `src/data.py` fetch data
- `src/ratios.py` P/E, P/B, EPS, yield, ROE, growth
- `src/redflags.py` red flags and consistency checks
- `src/scoring.py` score, rating, confidence
- `src/ai_summary.py` AI explanation
- `src/glossary.py` beginner definitions

## Roadmap
1. Bank metrics (NPLs, net interest margin) from manual input or PDFs
2. Peer comparison
3. Fair value range with best/worst case
4. Watchlist and PDF export

## Caveat
Yahoo coverage of Nairobi (.NR) stocks can be patchy. The tool lowers confidence when data is missing.
Not financial advice.
