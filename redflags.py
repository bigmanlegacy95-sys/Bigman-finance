"""Detect red flags and things that do not add up."""


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
