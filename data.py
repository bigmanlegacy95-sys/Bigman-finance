"""Fetch raw company data from Yahoo Finance (free)."""
import yfinance as yf


def fetch(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    info = {}
    try:
        info = t.info or {}
    except Exception:
        pass

    def safe(attr):
        try:
            return getattr(t, attr)
        except Exception:
            return None

    return {
        "ticker": ticker.upper(),
        "info": info,
        "income": safe("financials"),
        "balance": safe("balance_sheet"),
        "dividends": safe("dividends"),
        "history": t.history(period="1y") if info else None,
    }
