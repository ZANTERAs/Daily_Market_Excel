# Daily_Market_Excel
Portfolio News, Sentiment & Valuation Dashboard  
(English + Español)

This project generates an Excel dashboard of your portfolio with:
- Live prices
- Profit / loss (absolute and %)
- Sentiment from recent news (including Argentine news sources for local tickers like YPF and PAM)
- A daily and weekly view of risk/harm from news
- A TOTAL row summarizing the entire portfolio
- A roadmap for adding valuation metrics (P/E, forward P/E, DCF) and predictive analytics (LSTM forecast)

It consists mainly of:
- `portfolio_news_profit.py` → orchestrates the workflow
- `news_harm.py` → fetches news, maps it to tickers, scores sentiment
- `ticker_aliases.py` → builds aliases / alternate names for each ticker
- Your Excel input (`portfolio_input.xlsx`) → you list your positions here and the script does the rest.  fileciteturn8file1


---

## 1. How it works (Daily_Market_Excel Bot)

You maintain a simple spreadsheet of your positions, and the script produces an enriched Excel output with:
- A **Summary** sheet (per ticker + a TOTAL row)
- A **Portfolio** sheet (your raw input, unchanged)
- One **NEWS - <TICKER>** sheet per ticker with recent headlines and sentiment
- (Future) a **Daily Snapshot** sheet with valuation metrics and comparisons
- (Future) a **Weekly Summary** sheet with “harm/risk” scoring per ticker  fileciteturn8file0  fileciteturn8file1


### Input format (`portfolio_input.xlsx`)

The first sheet must contain these columns:

| Column      | Meaning                                                  |
|-------------|----------------------------------------------------------|
| `Ticker`    | Stock ticker symbol, e.g. `YPF`, `MSFT`, `PAM`            |
| `Buy Price` | Your entry price per share                               |
| `Buy Date`  | The date you bought (any Excel-parsable date is okay)    |
| `Shares`    | How many shares you own                                  |

If the file doesn't exist yet, the script will auto-create a template with those 4 columns so you can fill it in.  fileciteturn8file1


---

## 2. What the script calculates today

For each ticker in your portfolio:

### Current Price
Pulled with `yfinance`. If the live `lastPrice` isn't available, it falls back to most recent daily close.  fileciteturn8file1

### P/L Abs (absolute profit/loss in dollars)
\`\`\`
(Current Price − Buy Price) * Shares
\`\`\`  fileciteturn8file1

### P/L % (percent return since you bought)
\`\`\`
(Current Price − Buy Price) / Buy Price
\`\`\`
Stored as a fraction (ex: -0.4025) and then formatted in Excel as a percentage (-40.25%).  fileciteturn8file1

### Avg Sentiment
We scrape news headlines that mention the ticker, score sentiment for each headline, and compute the average sentiment per ticker over the recent lookback window.  
- Sentiment is in [-1, 1], where -1 is very negative and +1 is very positive.  
- This becomes the `Avg Sentiment` column in Summary.  fileciteturn8file1

### TOTAL row (whole portfolio snapshot)
At the bottom of the `Summary` sheet we append a bold `TOTAL` row with portfolio-wide aggregates:
- **Buy Price (TOTAL row)** → total *cost basis* = Σ(Buy Price × Shares)
- **Shares (TOTAL row)** → total shares across all tickers
- **Current Price (TOTAL row)** → total *current value* = Σ(Current Price × Shares)
- **P/L Abs (TOTAL row)** → total dollar P/L across the portfolio
- **P/L % (TOTAL row)** → overall portfolio return = (Total Current Value − Total Cost Basis) / Total Cost Basis
- **Avg Sentiment (TOTAL row)** → currently left blank (future: weighted portfolio sentiment)

This lets you see both per-position performance and full portfolio performance at a glance.  fileciteturn8file1


---

## 3. Output Excel structure

When you run the script, it builds an output workbook (e.g. `portfolio_output.xlsx`) with:

### `Summary`
Columns:
- `Ticker`
- `Buy Price`
- `Buy Date`
- `Shares`
- `Current Price`
- `P/L Abs`
- `P/L %`
- `Avg Sentiment`
- Plus the bold `TOTAL` row.

Formatting:
- `P/L %`: green if positive, red if negative
- `Avg Sentiment`: color scale from red (-1) to yellow (0) to green (+1)
- Currency columns are formatted as USD
- The TOTAL row is bold + formatted  fileciteturn8file1

### `Portfolio`
The raw data you typed in, unchanged, so you always see inputs.  fileciteturn8file1

### `NEWS - <TICKER>` (one per ticker)
For example:
- `NEWS - YPF`
- `NEWS - PAM`
- `NEWS - MSFT`

Each sheet has:
- Date
- Source
- Title
- Link
- Sentiment score for that headline

Sentiment cells get a red→yellow→green gradient.  fileciteturn8file1


---

## 4. News + Sentiment pipeline

All news/sentiment logic lives in `news_harm.py`.

1. **Fetch feeds**  
   We pull from:
   - Global finance feeds (Reuters, WSJ/Markets, CNBC, etc.)
   - Yahoo Finance RSS feeds that are specific to each ticker
   - Argentina-focused financial / energy / macro outlets like Ámbito, El Cronista, Infobae Economía / Energía (to capture coverage on local tickers like YPF and PAM).  fileciteturn8file1

   Everything is normalized into a pandas DataFrame with columns like `date`, `title`, `summary`, `link`, `source`.

2. **Map articles to tickers**  
   Each story is matched to a ticker using:
   - the ticker symbol itself (`YPF`, `PAM`, `MSFT`, …)
   - all known aliases for that ticker (see next section)  
   If no ticker clearly matches, we can tag a headline as `"MARKET"` to capture macro mood.  fileciteturn8file1

3. **Score sentiment**  
   Each article is scored using one of two backends:
   - `"vader"`: lexicon-style sentiment → score in [-1, 1]
   - `"finbert"`: finance-tuned language model → also mapped to [-1, 1]  
   That sentiment score is saved per headline, and then averaged per ticker.  fileciteturn8file1

4. **Aggregation / Signal**  
   We can roll headlines up by ticker and by date to get:
   - mean sentiment that day
   - number of articles
   - and even a coarse BUY / HOLD / SELL label based on thresholds  
   (used for analysis / alerting / backtesting).  fileciteturn8file1

5. **Argentina fallback (when needed)**  
   If a ticker gets zero coverage from global feeds, we optionally query Google News Argentina (`hl=es-419`, `gl=AR`) using all aliases of that ticker.  
   This fills sheets like `NEWS - YPF` with Spanish-language headlines even when US outlets ignore it.  
   This fallback is controlled by `--ar-news 1`, and will eventually be made unnecessary once Argentinian sources are fully integrated directly.  fileciteturn8file1  fileciteturn8file0


---

## 5. Ticker aliases

`ticker_aliases.py` builds intelligent aliases for each ticker, combining:
- The raw ticker (e.g. `YPF`)
- The long company name from Yahoo Finance (`Yacimientos Petrolíferos Fiscales S.A.`)
- Cleaned versions without suffixes like “Inc.”, “Corp.”, “S.A.”
- Split variants like `Pampa Energía`, `Pampa Holding`
- Any custom aliases you provide in `aliases.json`

Why this matters:
- Local press might say “Yacimientos Petrolíferos Fiscales” instead of “YPF”.
- Spanish media might say “Pampa Energía” instead of “PAM”.  
These aliases let us tag those headlines correctly and include them in sentiment + news sheets.  fileciteturn8file1


---

## 6. Running the script

Typical usage:

```bash
python portfolio_news_profit.py   --input portfolio_input.xlsx   --output portfolio_output.xlsx   --news-backend vader   --news-days 7   --aliases aliases.json   --ar-news 1
```

**Arguments:**
- `--input`: path to your input workbook (the one you edit)
- `--output`: where the enriched workbook will be written
- `--news-backend`: which sentiment model to use (`vader` or `finbert`)
- `--news-days`: how many days of headlines to include
- `--aliases`: optional JSON with custom aliases for tickers
- `--ar-news`: `1` = also pull Argentina-local headlines if global feeds miss a ticker; `0` = skip that extra query  fileciteturn8file1


---

## 7. Excel styling details

Inside the generated Excel:
- Column widths are set for readability
- `P/L %` cells go green if positive, red if negative
- `Avg Sentiment` cells use a red→yellow→green gradient
- Sentiment in each `NEWS - <TICKER>` sheet is also color-scaled
- The TOTAL row is bold and has currency / % formatting so it looks like a proper dashboard, not raw data  fileciteturn8file1


---

## 8. Roadmap / TODO (English)

Below is the work plan to evolve this into a full “Daily Market Excel Bot” that can act as both a daily dashboard and a weekly risk monitor.  fileciteturn8file0

### 8.1 Daily Snapshot Sheet (new)
Create a new sheet (e.g. `Daily Snapshot`) that, for each ticker, shows:
- Ticker
- Current Price
- P/L Abs
- P/L %
- % From Historical Value (relative move vs a baseline like 30d avg / 52-week avg / last month close)
- P/E (trailing)
- Forward P/E (next year expected earnings)
- Competitor P/E + Competitor ticker(s)
- 10-day LSTM forecast (only if requested)

Implementation notes:
- Reuse current fields we already compute (`Ticker`, `Current Price`, `P/L Abs`, `P/L %`)
- Add fundamentals (trailing P/E, forward P/E)
- Add competitor mapping and competitor P/E comparison
- Add an optional LSTM price projection for the next 10 days (only when user specifically asks)

Status:
- Core P/L pieces are partially implemented in `Summary` (🟡)
- Valuation metrics (P/E, forward P/E, competitor P/E) are not implemented (❌)
- Historical baseline % move not implemented (❌)
- LSTM forecast concept exists but not implemented (❌)  fileciteturn8file0


### 8.2 Weekly Summary Sheet (new)
Add a `Weekly Summary` sheet with:
- Ticker
- Avg Sentiment over the last 7 days
- (#) of articles in that 7-day window (and especially # of negative articles)
- A “Harm / Risk” label such as LOW / MEDIUM / HIGH based on sentiment level and negative coverage volume

This gives you: “How much did news hurt this company this week?”  
Status: sentiment scoring and per-ticker `NEWS - <TICKER>` sheets exist (🟡), but the rollup-by-week and harm labeling are not built yet (❌).  fileciteturn8file0


### 8.3 Portfolio-Level Enhancements
- Portfolio TOTAL row currently includes:
  - Total cost basis
  - Total current value
  - Total P/L Abs
  - Total P/L %  
  (🟡 already implemented)

Next steps:
- Add a portfolio-wide sentiment score, ideally weighted by position size, and show it in the TOTAL row (❌)
- Add multi-currency awareness (USD vs ARS, etc.), convert into a reporting currency, and display both native and converted values (❌)  fileciteturn8file0


### 8.4 Valuation: Discounted Free Cash Flow (DCF)
Add a valuation block (new “Valuation” sheet or extra columns) that shows:
- DCF fair price estimate per ticker
- % Upside / Downside vs current price

Requires:
- Cash flow projections
- Discount rate / WACC
- Terminal growth assumption

Status: not implemented (❌).  fileciteturn8file0


### 8.5 Cleanup / Simplification
- Integrate Argentina-focused feeds natively into `news_harm.py` so we *always* capture local Spanish coverage of tickers like YPF and PAM, instead of relying on fallback scraping or the `--ar-news` flag (❌ / in progress)
- Once that’s in place, remove the `--ar-news` flag and delete the Google News Argentina fallback path to simplify the pipeline (❌)  fileciteturn8file0  fileciteturn8file1


---

## 9. Versión en Español (resumen)

### 9.1 ¿Qué hace el bot?
Genera un Excel diario con:
- Precio actual de cada ticker
- Ganancia / Pérdida en $ y en %
- Sentimiento promedio de las noticias recientes
- Una hoja de noticias por ticker
- Una fila TOTAL con el estado consolidado de toda la cartera  fileciteturn8file1

Próximas mejoras:
- Hoja `Daily Snapshot` con métricas de valuación (P/E, Forward P/E, comparables)
- Hoja `Weekly Summary` con el “riesgo / daño” reputacional de la semana
- Sentimiento global de la cartera en la fila TOTAL
- Soporte multi-moneda (USD / ARS)
- Modelo de valuación por DCF
- Predicción de precio a 10 días con LSTM bajo demanda  fileciteturn8file0


### 9.2 Flujo de noticias (Argentina incluido)
El sistema baja titulares desde:
- Medios financieros globales (Reuters, WSJ/Markets, CNBC, etc.)
- RSS específico de cada ticker (Yahoo Finance)
- Medios económicos de Argentina (Ámbito, Cronista, Infobae Economía / Energía)  
Si un ticker argentino no tiene cobertura internacional, se puede (por ahora) consultar Google News Argentina en español usando todos los alias de esa compañía, para que hojas como `NEWS - YPF` no queden vacías.  fileciteturn8file1  fileciteturn8file0

Plan futuro:
- Integrar las fuentes argentinas directamente en `news_harm.py` y después eliminar el flag `--ar-news`.  fileciteturn8file0


### 9.3 Próximos pasos clave
1. Nueva hoja `Daily Snapshot` con P/E, Forward P/E, comparables y % vs valor histórico.  
2. Nueva hoja `Weekly Summary` con un score de daño (“Harm / Risk”) semanal.  
3. Sentimiento global de la cartera y soporte multi-moneda en la fila TOTAL.  
4. Modelo de valoración por Descuento de Flujos de Caja (DCF).  
5. Predicción de 10 días con LSTM si el usuario la pide (no siempre).  fileciteturn8file0


---

## 10. TL;DR

- **Today:** You already get prices, P/L, sentiment, per-ticker news sheets, and a TOTAL row. 🟡  fileciteturn8file1  
- **Next:** Add valuation (P/E, Forward P/E, DCF), competition comparison, multi-currency, portfolio sentiment, weekly harm scoring, and optional 10-day forecasts. ❌  fileciteturn8file0

