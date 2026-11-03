"""StockScope v2 - Kenya-first web research. Research support, not financial advice."""
import json
import os
import re

import pandas as pd
import requests
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="StockScope", page_icon="📊", layout="centered")

DISCLAIMER = ("Research support, not financial advice. Prices can fall and you can lose money. "
              "Web-found numbers can be wrong or old, so check the sources.")

GLOSSARY = {
    "Share price": "What one share costs now. Example: 50 shillings for one bakery share.",
    "Market cap": "Price x all issued shares. 50 x 100 shares = 5,000.",
    "EPS": "Yearly profit / number of shares. 1,000 / 100 = 10 per share.",
    "P/E": "Price / EPS: shillings paid per shilling of yearly profit. 50 / 10 = 5.",
    "P/B": "Price / book value per share. Below 1 = discount, above 1 = premium.",
    "Dividend yield": "Yearly dividend / price. 5 / 50 = 10%.",
    "Payout ratio": "Share of profit paid as dividend. Above 100% is a warning.",
    "ROE": "Profit / shareholders' equity. How well money is put to work.",
    "Debt-to-equity": "Borrowed money vs shareholders' money. High = riskier.",
    "NPL ratio": "Bank loans not being repaid. High = the bank may lose money.",
    "Net interest margin": "What a bank earns on loans minus what it pays on deposits.",
    "Cost-to-income": "How much of a bank's income is eaten by costs. Lower is better.",
    "Capital ratio": "A bank's safety cushion. CBK sets minimums banks must meet.",
}

NUM_FIELDS = [
    ("price", "Share price"), ("eps", "EPS (latest full year)"),
    ("book_value_ps", "Book value per share"), ("dividend_ps", "Dividend per share"),
    ("net_profit", "Net profit (latest)"), ("net_profit_prior", "Net profit (previous year)"),
    ("revenue", "Revenue / total income (latest)"), ("revenue_prior", "Revenue (previous year)"),
    ("total_equity", "Shareholders' equity"), ("roe_pct", "ROE %"),
    ("debt_to_equity", "Debt-to-equity (x)"), ("market_cap_bn", "Market cap (billions)"),
    ("npl_ratio_pct", "NPL ratio % (banks)"), ("nim_pct", "Net interest margin % (banks)"),
    ("cost_income_pct", "Cost-to-income % (banks)"), ("capital_ratio_pct", "Total capital ratio % (banks)"),
]


# ---------------- helpers ----------------
def num(x):
    try:
        if x is None or isinstance(x, bool):
            return None
        if isinstance(x, str):
            x = x.replace(",", "").replace("%", "").strip()
        x = float(x)
        return x if x == x else None
    except Exception:
        return None


def frac(v):
    return v / 100 if v is not None else None


def growth(new, old):
    if new is None or old is None or old <= 0:
        return None
    return (new - old) / old


def secret(name, default=None):
    v = os.getenv(name)
    if v:
        return v
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default


# ---------------- AI + web research ----------------
API = "https://generativelanguage.googleapis.com/v1beta"


@st.cache_data(ttl=3600, show_spinner=False)
def pick_model(key):
    """Ask Google which models this key can use, and pick the newest stable Flash."""
    r = requests.get(f"{API}/models", headers={"x-goog-api-key": key}, params={"pageSize": 200}, timeout=30)
    r.raise_for_status()
    names = [m["name"].split("/")[-1] for m in r.json().get("models", [])
             if "generateContent" in m.get("supportedGenerationMethods", [])]
    bad = ("lite", "image", "tts", "live", "audio", "exp", "preview", "latest", "embed", "thinking", "robotics")
    flash = [n for n in names if "flash" in n and not any(b in n for b in bad)]

    def ver(n):
        mt = re.search(r"gemini-(\d+(?:\.\d+)?)", n)
        return float(mt.group(1)) if mt else 0.0

    pool = sorted(flash, key=ver, reverse=True) or [n for n in names if "flash" in n] or names
    if not pool:
        raise RuntimeError("This API key has no models available. Create a new key at aistudio.google.com.")
    return pool[0]


def gemini(prompt, search=False):
    key = secret("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("No GEMINI_API_KEY found. Add it under the app's Secrets.")
    model = secret("GEMINI_MODEL") or pick_model(key)
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    if search:
        body["tools"] = [{"google_search": {}}]
    r = requests.post(f"{API}/models/{model}:generateContent",
                      headers={"x-goog-api-key": key}, json=body, timeout=120)
    if r.status_code == 429:
        raise RuntimeError("Free AI limit reached. Wait a minute and try again.")
    if r.status_code >= 400:
        try:
            detail = r.json()["error"]["message"][:200]
        except Exception:
            detail = ""
        raise RuntimeError(f"AI service error {r.status_code} (model: {model}). {detail}")
    cand = r.json()["candidates"][0]
    text = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []))
    chunks = cand.get("groundingMetadata", {}).get("groundingChunks", [])
    sources = [{"title": c["web"].get("title", ""), "url": c["web"].get("uri", "")}
               for c in chunks if "web" in c]
    return text, sources


RESEARCH_PROMPT = """Research the listed company: "{q}". It is probably listed on the Nairobi Securities Exchange (NSE), Kenya, but if not, find the right exchange.
Use Google Search. Prefer official sources first (NSE, the company's investor/results pages, CBK for banks), then Kenyan business media (Business Daily, Nation, The Star, Mansa, AfricanFinancials, Kenyan Wall Street).
Find the LATEST figures. Return ONLY one JSON object, no other text, with these keys:
name, ticker, sector, is_bank (true/false), currency,
price, price_date,
eps (latest full-year or trailing-12-month earnings per share),
book_value_ps, dividend_ps (latest full-year dividend per share),
net_profit, net_profit_prior (same period type, previous year, same units),
revenue, revenue_prior (banks: total operating income; same units),
total_equity (same units as net_profit), roe_pct, debt_to_equity (ratio, null for banks), market_cap_bn (billions),
npl_ratio_pct, nim_pct, cost_income_pct, capital_ratio_pct (banks only, else null),
results_period (e.g. "FY2025" or "H1 2026"), notes (one short sentence on data quality or conflicts).
Rules: numbers only (no text or commas) for numeric keys. Use null when you cannot find or verify a value. Never guess or invent. If sources disagree, pick the most official one and mention it in notes."""


@st.cache_data(ttl=6 * 3600, show_spinner=False)
def research(query):
    text, sources = gemini(RESEARCH_PROMPT.format(q=query), search=True)
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise RuntimeError("Could not read the research result. Try the full company name.")
    try:
        data = json.loads(m.group(0))
    except Exception:
        raise RuntimeError("The research result was garbled. Please try again.")
    return data, sources


def facts_from_yahoo(ticker):
    t = yf.Ticker(ticker)
    i = t.info or {}
    price = num(i.get("currentPrice") or i.get("regularMarketPrice"))
    if price is None:
        raise RuntimeError("Yahoo has no data for this ticker. Try Web research instead.")

    def row(names):
        try:
            df = t.financials
            for n in names:
                if n in df.index:
                    return df.loc[n].dropna().sort_index()
        except Exception:
            pass
        return None

    ni, rev = row(["Net Income"]), row(["Total Revenue"])
    last = lambda s, k: float(s.iloc[k]) if s is not None and len(s) >= abs(k) else None
    de = num(i.get("debtToEquity"))
    roe = num(i.get("returnOnEquity"))
    mc = num(i.get("marketCap"))
    facts = {
        "price": price, "eps": num(i.get("trailingEps")), "book_value_ps": num(i.get("bookValue")),
        "dividend_ps": num(i.get("dividendRate")), "net_profit": last(ni, -1), "net_profit_prior": last(ni, -2),
        "revenue": last(rev, -1), "revenue_prior": last(rev, -2),
        "roe_pct": roe * 100 if roe is not None else None,
        "debt_to_equity": de / 100 if de is not None else None,
        "market_cap_bn": mc / 1e9 if mc else None,
    }
    meta = {"name": i.get("longName") or ticker.upper(), "ticker": ticker.upper(), "sector": i.get("sector"),
            "is_bank": "bank" in (i.get("industry") or "").lower(), "currency": i.get("currency"),
            "period": "latest annual (Yahoo)", "notes": "", "sources": [{"title": "Yahoo Finance", "url": ""}]}
    return facts, meta


# ---------------- analysis ----------------
def build_metrics(F, meta):
    g = lambda k: num(F.get(k))
    price, eps, bv, dps = g("price"), g("eps"), g("book_value_ps"), g("dividend_ps")
    npf, npp, eq = g("net_profit"), g("net_profit_prior"), g("total_equity")
    roe_stated = frac(g("roe_pct"))
    roe_calc = npf / eq if npf is not None and eq and eq > 0 else None
    return {
        "name": meta.get("name"), "sector": meta.get("sector"), "currency": meta.get("currency") or "",
        "is_bank": bool(meta.get("is_bank")), "price": price, "eps": eps,
        "pe": price / eps if price and eps and eps > 0 else None,
        "pb": price / bv if price and bv and bv > 0 else None,
        "book_value_ps": bv, "dividend_ps": dps,
        "dividend_yield": dps / price if price and dps else None,
        "payout_ratio": dps / eps if dps and eps and eps > 0 else None,
        "roe": roe_stated if roe_stated is not None else roe_calc,
        "roe_stated": roe_stated, "roe_calc": roe_calc,
        "debt_to_equity": g("debt_to_equity"), "market_cap_bn": g("market_cap_bn"),
        "profit_growth": growth(npf, npp), "revenue_growth": growth(g("revenue"), g("revenue_prior")),
        "npl": frac(g("npl_ratio_pct")), "nim": frac(g("nim_pct")),
        "cir": frac(g("cost_income_pct")), "car": frac(g("capital_ratio_pct")),
    }


def detect(m):
    flags = []
    add = lambda lvl, txt: flags.append({"level": lvl, "text": txt})
    if m["price"] is None:
        add("high", "No price found. Check the name or enter the price yourself.")
    if m["eps"] is not None and m["eps"] <= 0:
        add("high", "The company is losing money (negative EPS).")
    if m["pe"] is not None and m["pe"] < 2:
        add("medium", f"P/E of {m['pe']:.1f} is unusually low. The data may be wrong or the market sees serious risk.")
    if m["pe"] is not None and m["pe"] > 40:
        add("medium", f"P/E of {m['pe']:.1f} is very high.")
    if m["pb"] is not None and m["pb"] < 0.5:
        add("medium", f"P/B of {m['pb']:.2f}: valued at under half of book value. Check for bad assets or loans.")
    if m["pb"] is not None and m["pb"] > 5:
        add("medium", f"P/B of {m['pb']:.1f} is a big premium over book value.")
    if m["payout_ratio"] is not None and m["payout_ratio"] > 1:
        add("high", "Dividend is larger than profit per share. That is not sustainable.")
    if m["dividend_yield"] is not None and m["dividend_yield"] > 0.12:
        add("medium", "A dividend yield above 12% is often a warning sign.")
    if m["roe"] is not None and m["roe"] < 0.05:
        add("medium", f"Low return on equity ({m['roe']:.1%}).")
    if not m["is_bank"] and m["debt_to_equity"] is not None and m["debt_to_equity"] > 2:
        add("high", f"Debt is {m['debt_to_equity']:.1f}x equity. Heavy borrowing.")
    if m["profit_growth"] is not None and m["profit_growth"] < -0.2:
        add("high", f"Profit fell {abs(m['profit_growth']):.0%} versus the previous year.")
    if m["revenue_growth"] is not None and m["revenue_growth"] < -0.1:
        add("medium", f"Revenue fell {abs(m['revenue_growth']):.0%} versus the previous year.")
    if m["roe_stated"] is not None and m["roe_calc"] is not None and abs(m["roe_stated"] - m["roe_calc"]) > 0.05:
        add("medium", f"Stated ROE ({m['roe_stated']:.1%}) and ROE worked out from profit and equity "
                      f"({m['roe_calc']:.1%}) disagree. Check the figures.")
    if m["is_bank"]:
        if m["npl"] is None:
            add("medium", "Bad-loan (NPL) ratio not found. It is the key health check for a bank.")
        elif m["npl"] > 0.10:
            add("high", f"NPL ratio is {m['npl']:.1%}. A large share of loans is not being repaid.")
        elif m["npl"] > 0.05:
            add("medium", f"NPL ratio is {m['npl']:.1%}, above a comfortable level.")
        if m["cir"] is not None and m["cir"] > 0.70:
            add("medium", f"Cost-to-income of {m['cir']:.0%} is high. Costs eat most of the income.")
        if m["car"] is not None and m["car"] < 0.145:
            add("high", f"Total capital ratio of {m['car']:.1%} looks below the roughly 14.5% CBK minimum. Verify.")
    return flags


def score(m, flags, n_sources):
    s, why = 50, []

    def adj(p, t):
        nonlocal s
        s += p
        why.append((p, t))

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
    if m["is_bank"]:
        if m["npl"] is not None and m["npl"] <= 0.05: adj(+6, "Low bad loans")
        if m["cir"] is not None and m["cir"] <= 0.55: adj(+4, "Efficient costs")
        if m["car"] is not None and m["car"] >= 0.145: adj(+3, "Capital ratio above CBK minimum")
    for f in flags:
        if f["level"] == "high": adj(-12, "High-severity flag")
        elif f["level"] == "medium": adj(-5, "Medium-severity flag")

    keys = ["pe", "pb", "dividend_yield", "roe", "profit_growth", "revenue_growth"] + (["npl"] if m["is_bank"] else [])
    coverage = sum(m[k] is not None for k in keys) / len(keys)
    if m["price"] is None or coverage < 0.34:
        s = min(s, 35)
        why.append((0, "Too little data: rating capped"))
    if any(f["level"] == "high" for f in flags):
        if s > 60:
            why.append((0, "High-severity flag: score capped at 60"))
        s = min(s, 60)
    s = max(0, min(100, s))
    rating = "Good" if s >= 70 else "Fair" if s >= 50 else "Weak" if s >= 35 else "Poor"
    issues = sum(f["level"] in ("high", "medium") for f in flags)
    c = coverage - 0.1 * issues - (0.15 if n_sources < 2 else 0)
    conf = "High" if c >= 0.8 else "Medium" if c >= 0.5 else "Low"
    return {"score": s, "rating": rating, "confidence": conf, "why": why}


def fmt(v, kind="num"):
    if v is None:
        return "n/a"
    return f"{v:.1%}" if kind == "pct" else f"{v:,.2f}"


def facts_text(m, flags, res, meta):
    return "\n".join([
        f"Company: {m['name']} ({m['sector']}), bank: {m['is_bank']}, period: {meta.get('period')}",
        f"Price {fmt(m['price'])} {m['currency']}, P/E {fmt(m['pe'])}, P/B {fmt(m['pb'])}, EPS {fmt(m['eps'])}",
        f"Dividend yield {fmt(m['dividend_yield'], 'pct')}, payout {fmt(m['payout_ratio'], 'pct')}, ROE {fmt(m['roe'], 'pct')}",
        f"Profit growth {fmt(m['profit_growth'], 'pct')}, revenue growth {fmt(m['revenue_growth'], 'pct')}, debt/equity {fmt(m['debt_to_equity'])}",
        f"Bank: NPL {fmt(m['npl'], 'pct')}, NIM {fmt(m['nim'], 'pct')}, cost-to-income {fmt(m['cir'], 'pct')}, capital ratio {fmt(m['car'], 'pct')}",
        f"Rating {res['rating']} ({res['score']}/100), confidence {res['confidence']}",
        "Red flags: " + ("; ".join(f["text"] for f in flags) or "none found"),
        f"Data notes: {meta.get('notes') or 'none'}",
    ])


def ai_analysis(m, flags, res, meta):
    prompt = ("You are a cautious investment research assistant explaining to a beginner. Using ONLY the facts below, write: "
              "1) a 3-sentence verdict, 2) Strengths, 3) Red flags and cautions, 4) What the numbers say, 5) Key risks, "
              "6) What to check next. Use simple words and short bullets. Never promise returns, never invent numbers, "
              "and say clearly when data is missing.\n\n" + facts_text(m, flags, res, meta))
    try:
        return gemini(prompt)[0]
    except Exception as e:
        return (f"**{m['name']}**: {res['rating']} ({res['score']}/100), {res['confidence']} confidence.\n\n"
                + " ".join(f["text"] for f in flags[:3]) + f"\n\n(AI analysis unavailable: {e})")


# ---------------- UI ----------------
st.title("📊 StockScope")
st.caption("Type a company. It researches the web, runs the checks big investors use, and explains the result.")
st.warning(DISCLAIMER)

mode = st.radio("Source", ["Web research (best for Kenya)", "Yahoo ticker (international)"])
q = st.text_input("Company or ticker", placeholder="Diamond Trust Bank, Safaricom, KCB..." if mode.startswith("Web") else "AAPL, BP.L")

if st.button("Analyse", type="primary") and q.strip():
    try:
        with st.spinner("Researching... this can take up to a minute"):
            if mode.startswith("Web"):
                data, sources = research(q.strip())
                facts = {k: num(data.get(k)) for k, _ in NUM_FIELDS}
                meta = {"name": data.get("name") or q, "ticker": data.get("ticker"), "sector": data.get("sector"),
                        "is_bank": bool(data.get("is_bank")), "currency": data.get("currency") or "KES",
                        "period": data.get("results_period"), "notes": data.get("notes") or "",
                        "price_date": data.get("price_date"), "sources": sources}
            else:
                facts, meta = facts_from_yahoo(q.strip())
        st.session_state.facts, st.session_state.meta = facts, meta
        st.session_state.rid = st.session_state.get("rid", 0) + 1
        st.session_state.pop("ai", None)
    except Exception as e:
        st.error(str(e))

if "facts" in st.session_state:
    facts, meta, rid = st.session_state.facts, st.session_state.meta, st.session_state.rid

    with st.expander("✏️ Check and edit the numbers"):
        st.caption("If a figure is wrong or missing, fix it from the NSE or the company's results. Everything below updates.")
        vals = {}
        for k, label in NUM_FIELDS:
            vals[k] = st.number_input(label, value=facts.get(k), key=f"{rid}_{k}")
        meta["is_bank"] = st.checkbox("This is a bank", value=meta.get("is_bank", False), key=f"{rid}_bank")

    m = build_metrics(vals, meta)
    flags = detect(m)
    n_src = len({s["title"] for s in meta.get("sources", []) if s.get("title")})
    res = score(m, flags, n_src)

    st.header(m["name"])
    st.caption(f"{meta.get('ticker') or ''}  |  {m['sector'] or ''}  |  Results: {meta.get('period') or 'n/a'}  |  Price date: {meta.get('price_date') or 'n/a'}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Rating", res["rating"])
    c2.metric("Score", f"{res['score']}/100")
    c3.metric("Confidence", res["confidence"])
    st.progress(res["score"] / 100)

    st.subheader("Key numbers")
    rows = [("Price", fmt(m["price"])), ("Market cap (bn)", fmt(m["market_cap_bn"])), ("EPS", fmt(m["eps"])),
            ("P/E", fmt(m["pe"])), ("P/B", fmt(m["pb"])), ("Dividend yield", fmt(m["dividend_yield"], "pct")),
            ("Payout ratio", fmt(m["payout_ratio"], "pct")), ("ROE", fmt(m["roe"], "pct")),
            ("Profit growth", fmt(m["profit_growth"], "pct")), ("Revenue growth", fmt(m["revenue_growth"], "pct"))]
    if m["is_bank"]:
        rows += [("NPL ratio", fmt(m["npl"], "pct")), ("Net interest margin", fmt(m["nim"], "pct")),
                 ("Cost-to-income", fmt(m["cir"], "pct")), ("Capital ratio", fmt(m["car"], "pct"))]
    else:
        rows.append(("Debt/Equity", fmt(m["debt_to_equity"])))
    st.dataframe(pd.DataFrame(rows, columns=["Metric", "Value"]), hide_index=True, use_container_width=True)

    st.subheader("Red flags")
    if not flags:
        st.success("None detected in the available data.")
    icons = {"high": "🔴", "medium": "🟠", "info": "ℹ️"}
    for fl in flags:
        st.write(f"{icons[fl['level']]} {fl['text']}")

    npf, npp = num(vals.get("net_profit")), num(vals.get("net_profit_prior"))
    if npf is not None and npp is not None:
        st.subheader("Profit: previous vs latest")
        st.bar_chart(pd.DataFrame({"Net profit": [npp, npf]}, index=["Previous", "Latest"]))

    st.subheader("AI analysis")
    if "ai" not in st.session_state:
        with st.spinner("Writing analysis..."):
            st.session_state.ai = ai_analysis(m, flags, res, meta)
    st.markdown(st.session_state.ai)
    if st.button("Refresh analysis with my edits"):
        with st.spinner("Writing analysis..."):
            st.session_state.ai = ai_analysis(m, flags, res, meta)
        st.rerun()

    with st.expander("Why this score?"):
        for pts, why in res["why"]:
            st.write(f"{pts:+d}  {why}")

    st.subheader("Sources")
    if meta.get("notes"):
        st.caption(f"Data note: {meta['notes']}")
    seen = set()
    for s in meta.get("sources", []):
        if s["title"] and s["title"] not in seen:
            seen.add(s["title"])
            st.markdown(f"- [{s['title']}]({s['url']})" if s["url"] else f"- {s['title']}")
    if not seen:
        st.caption("No sources returned. Treat the figures with extra caution.")

with st.expander("📖 Learn the terms"):
    for k, v in GLOSSARY.items():
        st.markdown(f"**{k}**: {v}")
