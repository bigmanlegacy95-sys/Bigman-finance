"""Turn raw data into the key investing ratios."""


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
