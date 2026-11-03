"""Plain-language analysis. Uses Gemini free tier if a key exists, else a template."""
import os
import requests

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
