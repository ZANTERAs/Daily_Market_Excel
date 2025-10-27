#!/usr/bin/env python3
"""
News Market Bot (Excel-enabled)
- Same behavior as original script, plus:
  * Saves a single Excel workbook with multiple sheets:
      - RawNews
      - MappedScored
      - DailySignals
"""

import json
import argparse
import datetime as dt
import hashlib
import os
import re
import sys
from typing import Dict, List

import feedparser
import pandas as pd

# --- Sentiment backends ---
from nltk.sentiment import SentimentIntensityAnalyzer  # VADER
import nltk

# Optional: FinBERT (huggingface transformers)
try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch
    FINBERT_AVAILABLE = True
except Exception:
    FINBERT_AVAILABLE = False

# Optional: prices
try:
    import yfinance as yf
    YF_AVAILABLE = True
except Exception:
    YF_AVAILABLE = False

# Optional: plots
try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except Exception:
    PLOTLY_AVAILABLE = False


# -----------------------------
# Configuration
# -----------------------------

from ticker_aliases import DEFAULT_TICKERS, build_aliases

if os.path.exists("aliases.json"):
    with open("aliases.json", "r", encoding="utf-8") as f:
        TICKER_ALIASES = json.load(f)
else:
    TICKER_ALIASES = build_aliases(DEFAULT_TICKERS)
    with open("aliases.json", "w", encoding="utf-8") as f:
        json.dump(TICKER_ALIASES, f, ensure_ascii=False, indent=2)

# Argentina-focused economic / markets feeds
AR_FEEDS = [
    # Ámbito Financiero (Economía / Finanzas / Negocios)
    "https://www.ambito.com/rss/pages/economia.xml",
    "https://www.ambito.com/rss/pages/finanzas.xml",
    "https://www.ambito.com/rss/pages/negocios.xml",

    # El Cronista (economía / mercados argentinos)
    "https://www.cronista.com/rss/feed.xml",

    # Infobae Argentina (cobertura general Argentina, energía, política económica)
    "https://www.infobae.com/argentina-footer/infobae/rss/",
]

# Global / US market feeds
GLOBAL_FEEDS = [
    "https://www.reutersagency.com/feed/?best-topics=business-finance&post_type=best",
    "https://feeds.a.dj.com/rss/RSSMarketsMain.xml",          # WSJ Markets
    "https://www.cnbc.com/id/100003114/device/rss/rss.html",  # CNBC Top News
    "https://www.investing.com/rss/news_25.rss",              # Investing.com Markets
]

# Merge them: we'll crawl both global + Argentina every time
GENERAL_FEEDS = GLOBAL_FEEDS + AR_FEEDS

# Yahoo Finance per-ticker RSS template
YF_TICKER_FEED = (
    "https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
)


DATA_DIR = "news_bot_output"
os.makedirs(DATA_DIR, exist_ok=True)


# -----------------------------
# Utilities
# -----------------------------
def md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def normalize_text(text: str) -> str:
    if not text:
        return ""
    # Remove excessive whitespace and urls
    text = re.sub(r"http\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_date(entry) -> dt.date:
    # Attempt multiple fields, fallback to today
    for key in ("published_parsed", "updated_parsed"):
        if getattr(entry, key, None):
            tstruct = getattr(entry, key)
            try:
                return dt.date(*tstruct[:3])
            except Exception:
                pass
    return dt.date.today()


def build_ticker_regexes(tickers: List[str], aliases_map: Dict[str, List[str]]) -> Dict[str, re.Pattern]:
    patterns = {}
    for t in tickers:
        words = [re.escape(t)]
        for alias in aliases_map.get(t, []):
            words.append(re.escape(alias))
        # word boundary for names; ticker can appear in parentheses, etc.
        pat = r"(?i)\b(" + r"|".join(words) + r")\b"
        patterns[t] = re.compile(pat, flags=re.IGNORECASE)
    return patterns


# -----------------------------
# Fetch news
# -----------------------------
def fetch_feeds(tickers: List[str]) -> pd.DataFrame:
    feeds = list(GENERAL_FEEDS)
    # add per-ticker yahoo feeds (tend to be very relevant)
    feeds += [YF_TICKER_FEED.format(ticker=t) for t in tickers]

    rows = []
    for url in feeds:
        try:
            parsed = feedparser.parse(url)
            for e in parsed.entries:
                title = normalize_text(getattr(e, "title", ""))
                summary = normalize_text(getattr(e, "summary", ""))
                link = getattr(e, "link", "")
                date = parse_date(e)
                uid = md5((title or "") + (summary or "") + (link or ""))
                rows.append(
                    {
                        "uid": uid,
                        "date": pd.to_datetime(date),
                        "title": title,
                        "summary": summary,
                        "link": link,
                        "source": parsed.feed.get("title", url),
                    }
                )
        except Exception as ex:
            print(f"[warn] failed feed: {url} -> {ex}", file=sys.stderr)

    df = pd.DataFrame(rows).drop_duplicates(subset=["uid"])
    # Basic filter for empty rows
    df = df[(df["title"].str.len() > 0) | (df["summary"].str.len() > 0)]
    return df.sort_values("date")


# -----------------------------
# Sentiment
# -----------------------------
class VaderBackend:
    def __init__(self):
        try:
            nltk.data.find("sentiment/vader_lexicon.zip")
        except LookupError:
            nltk.download("vader_lexicon")
        self.analyzer = SentimentIntensityAnalyzer()

    def score(self, text: str) -> float:
        if not text:
            return 0.0
        return self.analyzer.polarity_scores(text)["compound"]  # [-1, 1]


class FinBERTBackend:
    """
    Requires internet on first run to download weights.
    Model: 'ProsusAI/finbert'
    Output mapped to [-1, 1] via (pos - neg)
    """
    def __init__(self):
        if not FINBERT_AVAILABLE:
            raise RuntimeError("FinBERT backend not available: install transformers + torch.")
        self.tokenizer = AutoTokenizer.from_pretrained("ProsusAI/finbert")
        self.model = AutoModelForSequenceClassification.from_pretrained("ProsusAI/finbert")
        self.model.eval()

    @torch.no_grad()
    def score(self, text: str) -> float:
        if not text:
            return 0.0
        inputs = self.tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
        outputs = self.model(**inputs)
        probs = torch.nn.functional.softmax(outputs.logits, dim=-1).flatten()
        # order: negative, neutral, positive
        neg, neu, pos = probs.tolist()
        return float(pos - neg)  # roughly in [-1, 1]


def get_backend(name: str):
    name = name.lower()
    if name in ("vader", "default"):
        return VaderBackend()
    if name in ("finbert", "bert", "prosusai/finbert"):
        return FinBERTBackend()
    raise ValueError("Unknown sentiment backend. Use 'vader' or 'finbert'.")


# -----------------------------
# Mapping headlines to tickers
# -----------------------------
def map_articles_to_tickers(df_news: pd.DataFrame, tickers: List[str]) -> pd.DataFrame:
    regs = build_ticker_regexes(tickers, TICKER_ALIASES)
    rows = []
    for _, r in df_news.iterrows():
        text = f"{r['title']} {r['summary']}".strip()
        matched = []
        for t in tickers:
            if regs[t].search(text):
                matched.append(t)
        if not matched:
            # keep general market articles under 'MARKET'
            matched = ["MARKET"]
        for t in matched:
            rows.append(
                {
                    "date": r["date"].date(),
                    "ticker": t,
                    "title": r["title"],
                    "summary": r["summary"],
                    "link": r["link"],
                    "source": r["source"],
                    "uid": r["uid"],
                }
            )
    mapped = pd.DataFrame(rows).drop_duplicates(subset=["uid", "ticker"])
    return mapped


def score_articles(df_mapped: pd.DataFrame, backend_name: str) -> pd.DataFrame:
    backend = get_backend(backend_name)
    scores = []
    for _, r in df_mapped.iterrows():
        text = (r["title"] or "") + ". " + (r["summary"] or "")
        s = backend.score(text)
        scores.append(s)
    df_mapped = df_mapped.copy()
    df_mapped["sentiment"] = scores
    return df_mapped


def aggregate_daily(df_scored: pd.DataFrame) -> pd.DataFrame:
    agg = (
        df_scored.groupby(["date", "ticker"])
        .agg(
            mean_sentiment=("sentiment", "mean"),
            n_articles=("uid", "nunique"),
        )
        .reset_index()
        .sort_values(["ticker", "date"])
    )
    # simple signal: thresholds can be tuned
    def signal(x: float) -> str:
        if x >= 0.15:
            return "BUY"
        if x <= -0.15:
            return "SELL"
        return "HOLD"

    agg["signal"] = agg["mean_sentiment"].apply(signal)
    return agg


# -----------------------------
# Prices & Plotting
# -----------------------------
def add_returns(daily: pd.DataFrame, lookahead_days: int = 1) -> pd.DataFrame:
    if not YF_AVAILABLE:
        return daily
    out = []
    for tkr, d in daily.groupby("ticker"):
        if tkr == "MARKET":
            # use ^GSPC as proxy for market
            y_ticker = "^GSPC"
        else:
            y_ticker = tkr
        try:
            start = (pd.to_datetime(d["date"].min()) - pd.Timedelta(days=7)).date()
            end = (pd.to_datetime(d["date"].max()) + pd.Timedelta(days=7)).date()
            px = yf.download(y_ticker, start=str(start), end=str(end), progress=False)["Adj Close"].dropna()
            df = d.copy()
            df = df.sort_values("date")
            # align with prices (business days)
            df["date"] = pd.to_datetime(df["date"])
            # forward returns (next-day close to close)
            px = px.asfreq("B").ffill()
            # return over lookahead_days
            next_px = px.shift(-lookahead_days)
            ret = (next_px / px - 1.0).rename("fwd_return")
            # join on same day
            joined = df.set_index("date").join(px.rename("price")).join(ret)
            joined["ticker"] = tkr
            out.append(joined.reset_index())
        except Exception as ex:
            print(f"[warn] price fetch failed for {y_ticker}: {ex}", file=sys.stderr)
    if out:
        res = pd.concat(out, ignore_index=True)
        # keep the columns if present
        keep = [c for c in ["date", "ticker", "mean_sentiment", "n_articles", "signal", "price", "fwd_return"] if c in res.columns]
        return res[keep]
    return daily


def plot_ticker(daily_with_ret: pd.DataFrame, ticker: str):
    if not PLOTLY_AVAILABLE:
        print("[info] Plotly not installed; skipping plot.")
        return
    d = daily_with_ret[daily_with_ret["ticker"] == ticker].dropna(subset=["mean_sentiment"])
    if d.empty:
        print(f"[info] No data to plot for {ticker}")
        return
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=d["date"],
        y=d["mean_sentiment"],
        name="Daily Sentiment"
    ))
    if "fwd_return" in d.columns and d["fwd_return"].notna().any():
        fig.add_trace(go.Scatter(
            x=d["date"],
            y=d["fwd_return"],
            name="Next-Day Return",
            mode="lines+markers",
            yaxis="y2"
        ))
        fig.update_layout(
            title=f"{ticker} — Sentiment vs. Next-Day Returns",
            xaxis_title="Date",
            yaxis_title="Sentiment (avg)",
            yaxis2=dict(title="Fwd Return", overlaying="y", side="right"),
            legend=dict(orientation="h")
        )
    else:
        fig.update_layout(
            title=f"{ticker} — Daily Sentiment",
            xaxis_title="Date",
            yaxis_title="Sentiment (avg)",
            legend=dict(orientation="h")
        )
    fig.show()


# -----------------------------
# Excel writer
# -----------------------------
def save_to_excel(news: pd.DataFrame, scored: pd.DataFrame, daily: pd.DataFrame) -> str:
    xlsx_path = os.path.join(DATA_DIR, "news_outputs.xlsx")  # always overwrite same file
    with pd.ExcelWriter(xlsx_path, engine="xlsxwriter") as writer:
        news.to_excel(writer, sheet_name="RawNews", index=False)
        scored.to_excel(writer, sheet_name="MappedScored", index=False)
        daily.to_excel(writer, sheet_name="DailySignals", index=False)
    print(f"[info] Excel overwritten: {xlsx_path}")
    return xlsx_path

# -----------------------------
# Main
# -----------------------------
def run(tickers: List[str], backend: str, days: int, plot: bool, lookahead: int):
    print(f"[info] tickers={tickers} backend={backend} days={days}")

    news = fetch_feeds(tickers)
    if news.empty:
        print("[warn] no news found")
        return

    # filter by recency
    cutoff = pd.Timestamp.today().normalize() - pd.Timedelta(days=days)
    news = news[news["date"] >= cutoff]

    mapped = map_articles_to_tickers(news, tickers)
    scored = score_articles(mapped, backend)
    daily = aggregate_daily(scored)
    daily = add_returns(daily, lookahead_days=lookahead)

    # Save artifacts
    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    news_file = os.path.join(DATA_DIR, f"raw_news_{ts}.csv")
    mapped_file = os.path.join(DATA_DIR, f"mapped_scored_{ts}.csv")
    daily_file = os.path.join(DATA_DIR, f"daily_signals_{ts}.csv")

    news.to_csv(news_file, index=False)
    scored.to_csv(mapped_file, index=False)
    daily.to_csv(daily_file, index=False)

    # NEW: save to Excel (multi-sheet)
    xlsx_path = save_to_excel(news, scored, daily)

    # Print summary signals
    print("\n=== Signals (last {} days) ===".format(days))
    latest_day = daily["date"].max()
    latest = daily[pd.to_datetime(daily["date"]) == pd.to_datetime(latest_day)]
    latest = latest.sort_values(["ticker"])
    for _, r in latest.iterrows():
        sent = float(r["mean_sentiment"])
        n = int(r["n_articles"])
        sig = r["signal"]
        print(f"{r['ticker']:<6}  signal={sig:<4}  sentiment={sent:+.3f}  n={n}")

    print(f"\nSaved:\n- {news_file}\n- {mapped_file}\n- {daily_file}\n- {xlsx_path}")

    plot = plot or (os.getenv("PLOTLY_ENABLED", "0") == "1")

    if plot :
        print("\n[info] Generating plots...")
        for t in tickers:
            plot_ticker(daily, t)
    else:
        print("[info] Plotting skipped (use --plot to enable)")


def parse_args():
    p = argparse.ArgumentParser(description="News Market Bot (Excel-enabled)")
    p.add_argument("--tickers", nargs="+", default=DEFAULT_TICKERS, help="List of tickers")
    p.add_argument("--backend", default="vader", choices=["vader", "finbert"], help="Sentiment backend")
    p.add_argument("--days", type=int, default=7, help="Lookback window for news")
    p.add_argument("--plot", action="store_true", help="Plot sentiment vs returns")
    p.add_argument("--lookahead", type=int, default=1, help="Days ahead to compute forward return")
    # parse_known_args to be notebook-friendly (ignores -f from Jupyter)
    args, _ = p.parse_known_args()
    return args



if __name__ == "__main__":
    args = parse_args()
    try:
        run(args.tickers, args.backend, args.days, args.plot, args.lookahead)
    except KeyboardInterrupt:
        print("\nInterrupted by user")
