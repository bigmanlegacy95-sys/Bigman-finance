"""StockScope - single-file version (research support, not financial advice)."""
import os
import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="StockScope", page_icon="📊", layout="centered")

# ---- src/data.py ----


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

# ---- src/ratios.py ----


def _num(x):
    return x if isinstance(x, (int, float)) and x == x else None


def _row(df, names):
    if df is None or getattr(df, "empty", True):
        return None
    for n in names:
        if n in df.index:
            s = df.loc[n].dropna()
            if len(s):
                return s.sort_index()
    return None


def _growth(series):
    if series is None or len(series) < 2:
        return None
    old, new = float(series.iloc[-2]), float(series.iloc[-1])
    if old <= 0:
        return None
    return (new - old) / old


def compute(data: dict) -> dict:
    i = data["info"]
    price = _num(i.get("currentPrice") or i.get("regularMarketPrice"))
    eps = _num(i.get("trailingEps"))
    bv = _num(i.get("bookValue"))
    div_rate = _num(i.get("dividendRate"))
    de = _num(i.get("debtToEquity"))

    net_income = _row(data["income"], ["Net Income", "Net Income Common Stockholders"])
    revenue = _row(data["income"], ["Total Revenue", "Operating Revenue"])

    return {
        "name": i.get("longName") or data["ticker"],
        "sector": i.get("sector"),
        "currency": i.get("currency"),
        "is_bank": "bank" in (i.get("industry") or "").lower(),
        "price": price,
        "market_cap": _num(i.get("marketCap")),
        "eps": eps,
        "pe": price / eps if price and eps and eps > 0 else None,
        "book_value_ps": bv,
        "pb": price / bv if price and bv and bv > 0 else None,
        "dividend_ps": div_rate,
        "dividend_yield": div_rate / price if price and div_rate else None,
        "payout_ratio": div_rate / eps if div_rate and eps and eps > 0 else None,
        "roe": _num(i.get("returnOnEquity")),
        "debt_to_equity": de / 100 if de is not None else None,
        "profit_margin": _num(i.get("profitMargins")),
        "profit_growth": _growth(net_income),
        "revenue_growth": _growth(revenue),
        "net_income_series": net_income,
        "revenue_series": revenue,
    }

# ---- src/redflags.py ----


def detect(m: dict) -> list[dict]:
    flags = []

    def add(level, text):
        flags.append({"level": level, "text": text})

    if m["price"] is None:
        add("high", "No price found. The ticker may be wrong or not covered by the data source.")
    if m["eps"] is not None and m["eps"] <= 0:
        add("high", "The company is losing money (negative earnings per share).")
    if m["pe"] is not None and m["pe"] < 2:
        add("medium", f"P/E of {m['pe']:.1f} is unusually low. The data may be stale or the market sees serious risk.")
    if m["pe"] is not None and m["pe"] > 40:
        add("medium", f"P/E of {m['pe']:.1f} is very high. You are paying a lot for each shilling of profit.")
    if m["pb"] is not None and m["pb"] < 0.5:
        add("medium", f"P/B of {m['pb']:.2f}: the market values it at under half its book value. Check for bad assets or loans.")
    if m["pb"] is not None and m["pb"] > 5:
        add("medium", f"P/B of {m['pb']:.1f} is a big premium over book value.")
    if m["payout_ratio"] is not None and m["payout_ratio"] > 1:
        add("high", "Dividends exceed profit. The company is paying out more than it earns, which is unsustainable.")
    if m["roe"] is not None and m["roe"] < 0.05:
        add("medium", f"Low return on equity ({m['roe']:.1%}). Shareholder money is not working hard.")
    if not m["is_bank"] and m["debt_to_equity"] is not None and m["debt_to_equity"] > 2:
        add("high", f"Debt is {m['debt_to_equity']:.1f}x equity. Heavy borrowing raises risk.")
    if m["profit_growth"] is not None and m["profit_growth"] < -0.2:
        add("high", f"Profit fell {abs(m['profit_growth']):.0%} versus the previous year.")
    if m["revenue_growth"] is not None and m["revenue_growth"] < -0.1:
        add("medium", f"Revenue fell {abs(m['revenue_growth']):.0%} versus the previous year.")
    if m["dividend_yield"] is not None and m["dividend_yield"] > 0.12:
        add("medium", "A dividend yield above 12% is often a warning sign, not a bargain.")

    # Consistency checks: numbers that contradict each other
    if m["roe"] is not None and m["roe"] > 0.15 and m["profit_growth"] is not None and m["profit_growth"] < -0.3:
        add("medium", "High ROE but sharply falling profit. The figures may not agree with each other.")
    if m["is_bank"]:
        add("info", "Banks need extra checks this tool cannot yet see: non-performing loans, net interest margin, capital adequacy. Check the bank's latest results.")

    return flags

# ---- src/scoring.py ----

KEY_METRICS = ["pe", "pb", "dividend_yield", "roe", "profit_growth", "revenue_growth"]


def score(m: dict, flags: list[dict]) -> dict:
    s = 50
    why = []

    def adj(points, text):
        nonlocal s
        s += points
        why.append((points, text))

    if m["pe"] is not None:
        if 4 <= m["pe"] <= 15: adj(+8, "Reasonable P/E")
        elif m["pe"] > 30: adj(-8, "Expensive P/E")
    if m["pb"] is not None:
        if 0.7 <= m["pb"] <= 2: adj(+6, "Fair P/B")
        elif m["pb"] > 4: adj(-6, "High P/B")
    if m["roe"] is not None:
        if m["roe"] >= 0.15: adj(+10, "Strong ROE")
        elif m["roe"] < 0.05: adj(-8, "Weak ROE")
    if m["dividend_yield"] is not None and 0.02 <= m["dividend_yield"] <= 0.09:
        adj(+5, "Healthy dividend yield")
    if m["payout_ratio"] is not None and 0 < m["payout_ratio"] <= 0.7:
        adj(+4, "Sustainable payout")
    if m["profit_growth"] is not None:
        if m["profit_growth"] > 0.05: adj(+8, "Growing profit")
        elif m["profit_growth"] < -0.1: adj(-10, "Falling profit")
    if m["revenue_growth"] is not None and m["revenue_growth"] > 0.05:
        adj(+4, "Growing revenue")

    for f in flags:
        if f["level"] == "high": adj(-12, "High-severity flag")
        elif f["level"] == "medium": adj(-5, "Medium-severity flag")

    available = sum(m[k] is not None for k in KEY_METRICS)
    coverage = available / len(KEY_METRICS)

    # If key data is missing or something makes no sense, do not reward it
    if m["price"] is None or coverage < 0.34:
        s = min(s, 35)
        why.append((0, "Too little data: rating capped"))

    s = max(0, min(100, s))
    rating = "Good" if s >= 70 else "Fair" if s >= 50 else "Weak" if s >= 35 else "Poor"

    n_issues = sum(f["level"] in ("high", "medium") for f in flags)
    conf_score = coverage - 0.1 * n_issues
    confidence = "High" if conf_score >= 0.8 else "Medium" if conf_score >= 0.5 else "Low"

    return {"score": s, "rating": rating, "confidence": confidence, "why": why, "coverage": coverage}

# ---- src/ai_summary.py ----

DISCLAIMER = ("This is research support, not financial advice. Prices can fall and you can lose money. "
              "Do your own checks before investing.")


def _fmt(v, pct=False):
    if v is None:
        return "n/a"
    return f"{v:.1%}" if pct else f"{v:,.2f}"


def _facts(m, flags, res):
    lines = [
        f"Company: {m['name']} ({m['sector']})",
        f"Price {_fmt(m['price'])} {m['currency']}, P/E {_fmt(m['pe'])}, P/B {_fmt(m['pb'])}, EPS {_fmt(m['eps'])}",
        f"Dividend yield {_fmt(m['dividend_yield'], True)}, payout {_fmt(m['payout_ratio'], True)}, ROE {_fmt(m['roe'], True)}",
        f"Profit growth {_fmt(m['profit_growth'], True)}, revenue growth {_fmt(m['revenue_growth'], True)}, debt/equity {_fmt(m['debt_to_equity'])}",
        f"Rating {res['rating']} (score {res['score']}/100), confidence {res['confidence']}",
        "Red flags: " + ("; ".join(f["text"] for f in flags) or "none found"),
    ]
    return "\n".join(lines)


def _template(m, flags, res):
    out = [f"**{m['name']}** gets a **{res['rating']}** rating ({res['score']}/100) with **{res['confidence']}** confidence."]
    if flags:
        out.append("Main concerns: " + " ".join(f["text"] for f in flags[:3]))
    else:
        out.append("No major red flags were detected in the available data.")
    out.append("Add a GEMINI_API_KEY to get a fuller AI explanation.")
    return "\n\n".join(out)


def explain(m, flags, res) -> str:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return _template(m, flags, res)

    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    prompt = (
        "You are a cautious investment research assistant explaining to a beginner. "
        "Using ONLY the facts below, write: 1) a 3-sentence verdict, 2) 'Strengths', "
        "3) 'Red flags and cautions', 4) 'What the numbers say', 5) 'Key risks'. "
        "Use simple words, short bullets, and never promise returns. Say clearly when data is missing. "
        "Never invent numbers.\n\n" + _facts(m, flags, res)
    )
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            params={"key": key},
            json={"contents": [{"parts": [{"text": prompt}]}]},
            timeout=40,
        )
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        return _template(m, flags, res) + f"\n\n(AI unavailable: {e})"

# ---- src/glossary.py ----
GLOSSARY = {
    "Share price": "What one share costs right now. Example: 50 shillings for one share of a bakery.",
    "Market cap": "Share price x all issued shares. A 50-shilling price with 100 shares = 5,000.",
    "EPS": "Yearly profit divided by number of shares. 1,000 profit / 100 shares = 10 per share.",
    "P/E": "Price divided by EPS: shillings paid per shilling of yearly profit. 50 / 10 = 5.",
    "P/B": "Price divided by book value per share. Below 1 = discount, above 1 = premium.",
    "Dividend yield": "Yearly dividend divided by price. 5 / 50 = 10%.",
    "Payout ratio": "Share of profit paid as dividends. Above 100% is a warning.",
    "ROE": "Profit divided by shareholders' equity. Shows how well money is put to work.",
    "Debt-to-equity": "Borrowed money compared to shareholders' money. High = riskier.",
}

# ---- app.py ----




@st.cache_data(ttl=3600, show_spinner=False)
def analyse(ticker: str):
    data = fetch(ticker)
    m = compute(data)
    flags = detect(m)
    res = score(m, flags)
    return m, flags, res


def f(v, kind="num"):
    if v is None:
        return "n/a"
    return f"{v:.1%}" if kind == "pct" else f"{v:,.2f}"


st.title("📊 StockScope")
st.caption("Type a ticker. Get the checks big investors run, explained simply.")
st.warning(DISCLAIMER)

ticker = st.text_input("Ticker", placeholder="DTK.NR, KCB.NR, AAPL, BP.L")
st.caption("Use the Yahoo Finance symbol. Nairobi stocks end in .NR")

if st.button("Analyse", type="primary") and ticker.strip():
    with st.spinner("Researching..."):
        m, flags, res = analyse(ticker.strip())

    st.header(m["name"])
    c1, c2, c3 = st.columns(3)
    c1.metric("Rating", res["rating"])
    c2.metric("Score", f"{res['score']}/100")
    c3.metric("Confidence", res["confidence"])
    st.progress(res["score"] / 100)

    st.subheader("Key numbers")
    rows = [
        ("Price", f(m["price"])), ("Market cap", f"{m['market_cap']:,.0f}" if m["market_cap"] else "n/a"),
        ("EPS", f(m["eps"])), ("P/E", f(m["pe"])), ("P/B", f(m["pb"])),
        ("Dividend yield", f(m["dividend_yield"], "pct")), ("Payout ratio", f(m["payout_ratio"], "pct")),
        ("ROE", f(m["roe"], "pct")), ("Debt/Equity", f(m["debt_to_equity"])),
        ("Profit growth", f(m["profit_growth"], "pct")), ("Revenue growth", f(m["revenue_growth"], "pct")),
    ]
    st.dataframe(pd.DataFrame(rows, columns=["Metric", "Value"]), hide_index=True, use_container_width=True)

    st.subheader("Red flags")
    if not flags:
        st.success("None detected in the available data.")
    icons = {"high": "🔴", "medium": "🟠", "info": "ℹ️"}
    for fl in flags:
        st.write(f"{icons[fl['level']]} {fl['text']}")

    if m["net_income_series"] is not None:
        st.subheader("Profit trend")
        s = m["net_income_series"].copy()
        s.index = [str(d.year) for d in s.index]
        st.bar_chart(s)

    st.subheader("AI analysis")
    with st.spinner("Writing analysis..."):
        st.markdown(explain(m, flags, res))

    with st.expander("Why this score?"):
        for pts, why in res["why"]:
            st.write(f"{pts:+d}  {why}")
    st.caption("Source: Yahoo Finance via yfinance. Data may be delayed or incomplete.")

with st.expander("📖 Learn the terms"):
    for k, v in GLOSSARY.items():
        st.markdown(f"**{k}**: {v}")

