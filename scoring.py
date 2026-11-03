"""Score 0-100, a rating, and a confidence level. Strict by design."""

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
