# Portfolio News & Sentiment Dashboard

This project takes a simple Excel of your positions and generates a full dashboard with:
- Live prices
- P/L per ticker and total portfolio P/L
- News sentiment per ticker
- Local Argentina coverage for Argentine tickers
- A clean Excel report with conditional formatting and per-ticker news sheets

It consists mainly of:
- `portfolio_news_profit.py` → orchestrates everything
- `news_harm.py` → fetches & scores news sentiment
- `ticker_aliases.py` → builds aliases / alternate names for tickers
- your input Excel file (e.g. `portfolio_input.xlsx`)


---

## 1. How it works

You maintain a simple spreadsheet with your trades, and the script outputs a richer Excel with:
- A **Summary** sheet (per ticker and totals)
- A **Portfolio** sheet (your raw input)
- One **NEWS - <TICKER>** sheet for each ticker, with recent headlines and sentiment


### Input format

The first sheet of your input Excel (default: `portfolio_input.xlsx`) must have the following columns:

| Column      | Meaning                                                  |
|-------------|----------------------------------------------------------|
| `Ticker`    | Stock ticker symbol, e.g. `YPF`, `MSFT`, `PAM`           |
| `Buy Price` | Your entry price per share                               |
| `Buy Date`  | Date you bought (any Excel-parsable date format is OK)   |
| `Shares`    | How many shares you own                                  |

If the file doesn’t exist, the script will auto-create a starter template with those four columns so you can fill it in.


---

## 2. What the script calculates

For each ticker in your sheet, the script calculates:

### Current Price
Pulled from Yahoo Finance using `yfinance`.  
If `fast_info.lastPrice` isn’t available, it falls back to the last daily close.

### P/L Abs (absolute P/L in dollars)
```text
(Current Price − Buy Price) * Shares
```

### P/L % (percentage return)
```text
(Current Price − Buy Price) / Buy Price
```
Important: this is stored as a fraction (e.g. -0.4025) and then formatted as a percentage in Excel (→ -40.25%).

### Avg Sentiment
We scrape recent headlines for that ticker, score their sentiment, and compute the average sentiment per ticker over the lookback window.

Sentiment is in the range `[-1, 1]`:
- Very negative ≈ -1
- Neutral ≈ 0
- Very positive ≈ +1

This per-ticker average becomes the `Avg Sentiment` column in the Summary sheet.

### TOTAL row
At the bottom of the `Summary` sheet, a bold `TOTAL` row summarizes the entire portfolio:

- **Buy Price (TOTAL row)**  
  The total **cost basis** of the portfolio:  
  `Σ( Buy Price * Shares )`

- **Shares (TOTAL row)**  
  `Σ( Shares )` across all tickers

- **Current Price (TOTAL row)**  
  The total **current value** of the portfolio:  
  `Σ( Current Price * Shares )`

- **P/L Abs (TOTAL row)**  
  The total dollar P/L across all tickers:  
  `Σ( P/L Abs )`

- **P/L % (TOTAL row)**  
  The total portfolio return:  
  `(Total Current Value − Total Cost Basis) / Total Cost Basis`

- **Avg Sentiment (TOTAL row)**  
  Currently left blank. (Future work: compute a portfolio-wide sentiment.)

So at a glance, you see not just each ticker, but the whole book.


---

## 3. Output Excel structure

When you run the script, it creates an output workbook (e.g. `portfolio_output.xlsx`) with multiple sheets:

### `Summary`
Contains:
- `Ticker`
- `Buy Price`
- `Buy Date`
- `Shares`
- `Current Price`
- `P/L Abs`
- `P/L %`
- `Avg Sentiment`
- A final bold `TOTAL` row with portfolio aggregates.

Formatting in `Summary`:
- `P/L %` is conditionally shaded **green if positive** and **red if negative**.
- `Avg Sentiment` is colored on a red → yellow → green gradient (bearish → neutral → bullish).
- Currency columns (`Current Price`, `P/L Abs`, totals) are formatted as USD.
- The `TOTAL` row is bolded programmatically.

### `Portfolio`
This is just your raw data (Ticker / Buy Price / Buy Date / Shares), so you always have the original inputs visible.

### `NEWS - <TICKER>`
There is one sheet per ticker, for example:
- `NEWS - YPF`
- `NEWS - PAM`
- `NEWS - MSFT`

Each `NEWS - <TICKER>` sheet includes:
- Date
- Source
- Title
- Link
- Sentiment

The Sentiment column in this sheet also has a color scale from red (-1) to yellow (0) to green (+1).


---

## 4. News and sentiment pipeline

All the news/sentiment intelligence comes from `news_harm.py`.

### Step 1. Fetch feeds
`news_harm.py` gathers articles from:
- Global finance/markets RSS feeds (Reuters, WSJ/Markets, CNBC, Investing.com, etc.)
- Yahoo Finance RSS feeds specific to each ticker
- Argentina-focused economic/energy/business feeds (e.g. Ámbito, El Cronista, Infobae Economía / Energía)

This ensures that:
- Big US tickers like `MSFT` get global coverage
- Argentina tickers like `YPF`, `PAM`, etc. also get local Spanish-language coverage

The script uses `feedparser` to normalize those feeds into a single pandas DataFrame with columns like `date`, `title`, `summary`, `link`, `source`.

### Step 2. Map to tickers
Each article is matched to tickers using two things:
1. The raw ticker symbol (e.g. `YPF`, `PAM`, `MSFT`)
2. A list of **aliases** (see the next section)

If an article matches any alias, we label that article with that ticker.  
If an article doesn’t match any ticker, we can label it as `"MARKET"` to capture macro sentiment.

### Step 3. Sentiment scoring
For each matched article:
- We run a sentiment model.
- By default the script supports:
  - `"vader"`: fast rule/lexicon-based scoring that returns a `compound` score in `[-1, 1]`
  - `"finbert"`: a finance-tuned BERT model; converts probabilities into a bullish/bearish score in `[-1, 1]`

We store that numeric sentiment score with the article.

### Step 4. Aggregation
We can optionally aggregate by ticker and by date:
- average sentiment that day
- how many headlines that day
- a coarse “signal” label like BUY / HOLD / SELL based on thresholds:
  - sentiment ≥ +0.15 → BUY
  - sentiment ≤ −0.15 → SELL
  - otherwise HOLD

This is mostly for analysis and backtesting. The portfolio script uses the per-article sentiment to compute an overall `Avg Sentiment` per ticker.

### Step 5. Local Argentina fallback (optional)
In the portfolio script, if a ticker gets **zero** results from the above feeds, it can also query Google News Argentina using that ticker’s aliases (in Spanish, localized to `es-419`, `gl=AR`).  
Those extra headlines get scored too, so Argentine names don’t end up with empty sheets.

This fallback can be toggled via a CLI flag (`--ar-news 1`), but as we add more Argentina-native feeds directly into `news_harm.py`, this becomes less necessary.


---

## 5. Ticker aliases

`ticker_aliases.py` builds intelligent aliases for each ticker, for example:

- The raw ticker (e.g. `"YPF"`)
- The long company name from Yahoo Finance (e.g. `"Yacimientos Petrolíferos Fiscales S.A."`)
- Cleaned versions of that name without “S.A.” / “Inc.” / “Corp.”
- Split variants (e.g. `"Pampa Energía"`, `"Pampa Holding"`)
- Any custom aliases you add in `aliases.json`

Why is this important?
- News articles might say “Pampa Energía” instead of the NYSE ticker `PAM`.
- Local outlets say “Yacimientos Petrolíferos Fiscales” instead of just “YPF”.
- The sentiment engine needs to catch those mentions and link them back to your tickers.

These aliases are used in:
- `map_articles_to_tickers()` so that headlines are properly assigned.
- Local Argentina searches, to make sure we’re not relying only on the English ticker symbol.


---

## 6. Running the script

Typical usage:

```bash
python portfolio_news_profit.py   --input portfolio_input.xlsx   --output portfolio_output.xlsx   --news-backend vader   --news-days 7   --aliases aliases.json   --ar-news 1
```

### Arguments

- `--input`  
  Path to your input workbook (the one you edit).

- `--output`  
  Where to write the enriched workbook.

- `--news-backend`  
  Which sentiment model to use:  
  - `vader` (default, lightweight), or  
  - `finbert` (finance-tuned language model, needs extra dependencies).

- `--news-days`  
  How many days back to include headlines.

- `--aliases`  
  (Optional) Path to a JSON file with custom aliases for tickers, for example:
  ```json
  {
    "YPF": ["Yacimientos Petrolíferos Fiscales", "YPF"],
    "PAM": ["Pampa Energía", "Pampa Holding"]
  }
  ```

- `--ar-news`  
  If set to `1`, the script will try a localized Argentina news search for any ticker that didn’t get coverage from the main feeds.  
  If set to `0`, it won’t do that extra step.


---

## 7. Excel styling details

The script uses `openpyxl` to apply styling:

- **Column widths** are set for readability.
- **`P/L %` cells** (column G in Summary) are:
  - Green fill if positive
  - Red fill if negative
- **`Avg Sentiment` cells** (column H in Summary) get a continuous color scale from -1 (red) to +1 (green).
- **Sentiment column in each `NEWS - <TICKER>` sheet** also gets a red→yellow→green scale.
- The `TOTAL` row in Summary is bolded automatically and uses proper number formats:
  - currency for totals,
  - percentage for total P/L %.

This makes the output Excel immediately usable as a dashboard.


---

## 8. TODO / Roadmap

These are the next steps / improvements we’ve defined for the project:

1. **Unify Argentina feeds natively**  
   Argentina-focused finance / energy / macroeconomic feeds (Ámbito, Cronista, Infobae Economía, etc.) should be included directly in `news_harm.py` so tickers like `YPF` and `PAM` get native Spanish coverage automatically and consistently.

2. **Remove `--ar-news`**  
   Once Argentina coverage is always present in the base feeds, the fallback Google News query (and the `--ar-news` flag) can be removed from `portfolio_news_profit.py` to simplify usage.

3. **Portfolio-wide sentiment**  
   Add a calculated `Avg Sentiment` for the entire portfolio in the `TOTAL` row, e.g. weighted by position size instead of leaving it blank.

4. **Multi-currency support**  
   Currently all money columns are formatted as USD.  
   We’d like to support ARS or mixed-currency holdings, plus FX conversion.

5. **More robust error handling**  
   Improve behavior if `yfinance` is down or an RSS feed throws an error.  
   Right now we skip failed feeds and continue; we could log failures or surface warnings in the Excel.

6. **Visual mini-charts**  
   `news_harm.py` can already produce plots of daily sentiment vs future return if you run it standalone.  
   Next step: embed small sparklines or trend columns directly into the Excel Summary.

7. **Alerting / backtesting**  
   Use the generated BUY / HOLD / SELL sentiment signal to trigger alerts when a ticker flips state (for example, HOLD → BUY), and eventually track performance.

---

# README (Español)

## 1. Qué hace este proyecto

Este proyecto transforma una planilla básica de tus posiciones en un informe completo con:
- Precios actuales de cada ticker
- Ganancia / Pérdida por ticker (en $ y en %)
- Sentimiento de noticias recientes sobre cada ticker
- Cobertura local argentina para tickers argentinos
- Un Excel final con formato condicional, una fila TOTAL y una hoja de noticias por ticker

Componentes principales:
- `portfolio_news_profit.py` → genera el informe final
- `news_harm.py` → baja noticias, les asigna un ticker y calcula sentimiento
- `ticker_aliases.py` → genera alias y nombres alternativos de cada empresa/ticker
- Tu Excel de entrada → donde cargás tus operaciones


---

## 2. Cómo cargo mis datos

En el archivo `portfolio_input.xlsx`, la primera hoja (`Portfolio`) tiene que tener:

- **Ticker**: símbolo bursátil (ej. `YPF`, `MSFT`, `PAM`)
- **Buy Price**: precio de compra por acción
- **Buy Date**: fecha de compra
- **Shares**: cantidad de acciones

Si `portfolio_input.xlsx` no existe, el script crea automáticamente una plantilla vacía con esas columnas.

Después simplemente completás tus operaciones ahí.


---

## 3. Qué calcula el script

Para cada ticker:

- **Current Price (Precio actual)**  
  Baja el último precio disponible desde Yahoo Finance.  
  Si no hay precio de último trade, usa el último cierre diario.

- **P/L Abs (Ganancia/Pérdida absoluta en USD)**  
  `(Precio actual − Precio de compra) * Cantidad`

- **P/L % (Rentabilidad porcentual)**  
  `(Precio actual − Precio de compra) / Precio de compra`  
  Se guarda como fracción y Excel lo muestra como %.

- **Avg Sentiment (Sentimiento promedio)**  
  Busca titulares recientes que mencionan ese ticker, calcula un puntaje de sentimiento entre -1 y +1, y promedia.  
  Ese promedio aparece en la columna `Avg Sentiment`.

- **Fila TOTAL**  
  Al final de la hoja `Summary` se agrega una fila `TOTAL` en negrita con:
  - Base de costo total (suma de Buy Price × Shares)
  - Cantidad total de acciones
  - Valor actual total (suma de Current Price × Shares)
  - P/L Abs total
  - P/L % total de toda la cartera  
  - Sentiment global todavía queda vacío (pendiente de mejora)

Esto te da la foto completa de tu cartera, no solo ticker por ticker.


---

## 4. Estructura del Excel de salida

El script genera un archivo nuevo (por ejemplo `portfolio_output.xlsx`) con estas hojas:

### `Summary`
Muestra:
- Ticker
- Buy Price
- Buy Date
- Shares
- Current Price
- P/L Abs
- P/L %
- Avg Sentiment
- Y una última fila `TOTAL` con la cartera consolidada

Formato visual:
- `P/L %` se pinta en **verde si es positivo** y **rojo si es negativo**
- `Avg Sentiment` tiene una escala de color rojo→amarillo→verde según el puntaje
- Las columnas de dinero se muestran en formato USD
- La fila `TOTAL` está en negrita

### `Portfolio`
Es básicamente la data cruda que cargaste, sin cálculos.

### `NEWS - <TICKER>`
Una hoja por cada ticker:
- Fecha
- Fuente
- Título
- Link
- Sentiment

La columna de Sentiment usa también el gradiente rojo (-1) → amarillo (0) → verde (+1), así podés ver rápido si las noticias son positivas o negativas.


---

## 5. Flujo de noticias y sentimiento (`news_harm.py`)

1. **Descarga de noticias (RSS)**  
   - Usa fuentes financieras globales (Reuters, WSJ/Markets, CNBC, etc.).
   - Usa el RSS de Yahoo Finance específico para cada ticker.
   - Usa fuentes económicas y energéticas de Argentina (por ejemplo Ámbito, El Cronista, Infobae Economía) para cubrir tickers locales como `YPF` o `PAM`.

   El código normaliza todos esos titulares en un DataFrame con `date`, `title`, `summary`, `link`, `source`.

2. **Asignación de cada nota a un ticker**  
   - Se comparan los titulares y resúmenes con el ticker y con todos sus alias.
   - Si matchea, esa nota se etiqueta con el ticker correcto.
   - Si no matchea ningún ticker, la nota puede caer en una etiqueta más general tipo `"MARKET"`.

3. **Cálculo de sentimiento**  
   - Puntúa cada titular en una escala [-1, 1].
   - Hay dos backends soportados:
     - `vader` (rápido, sin GPU)
     - `finbert` (modelo más financiero, requiere dependencias extra)

4. **Agregación**  
   - Se puede agrupar por día y ticker para ver el promedio diario de sentimiento, cantidad de titulares y generar una señal BUY / HOLD / SELL en base a umbrales sencillos.

5. **Cobertura argentina / fallback**  
   - Para tickers que casi no aparecen en prensa internacional, el script puede (opcionalmente) consultar Google News Argentina en español para completar con titulares locales y puntuarlos.  
   - Esto evita que `NEWS - YPF` o `NEWS - PAM` queden en blanco.


---

## 6. Aliases de tickers (`ticker_aliases.py`)

Para cada ticker se generan alias basados en:
- El nombre largo de la compañía en Yahoo Finance
- El mismo nombre pero sin sufijos tipo “Inc.”, “Corp.”, “S.A.”
- Variantes partidas (por ejemplo “Pampa Energía”, “Pampa Holding”)
- Alias personalizados que vos agregues en `aliases.json`
- El propio ticker (ej. “YPF”, “PAM”, etc.)

¿Para qué?
- Para que podamos detectar noticias que digan “Yacimientos Petrolíferos Fiscales” y entender que eso es `YPF`.
- Para que “Pampa Energía” matchee con `PAM`.
- Para que cuando buscamos en medios argentinos, usemos términos reales en español y no solo el ticker de Wall Street.


---

## 7. Cómo ejecutar el script

Ejemplo de uso:

```bash
python portfolio_news_profit.py   --input portfolio_input.xlsx   --output portfolio_output.xlsx   --news-backend vader   --news-days 7   --aliases aliases.json   --ar-news 1
```

### Parámetros

- `--input`: ruta del Excel donde cargaste tus operaciones.
- `--output`: ruta del Excel de salida (el dashboard).
- `--news-backend`: `vader` (rápido) o `finbert` (modelo financiero).
- `--news-days`: cuántos días hacia atrás mirar noticias.
- `--aliases`: un JSON opcional con alias personalizados para cada ticker.
- `--ar-news`: si vale `1`, el script intenta buscar titulares argentinos localizados (`hl=es-419`, `gl=AR`) cuando no hay cobertura internacional reciente.

Abrís el `output` y vas directo a `Summary` para ver P/L y sentimiento, más la fila TOTAL que resume toda la cartera.


---

## 8. TODO / Próximos pasos

1. **Incluir feeds argentinos por defecto**  
   Seguir integrando medios económicos argentinos directamente en `news_harm.py` para que tickers locales tengan siempre cobertura en español.

2. **Eliminar `--ar-news`**  
   Cuando todas las fuentes argentinas estén incorporadas siempre, vamos a poder borrar el flag `--ar-news` y el código de fallback por Google News Argentina.

3. **Sentimiento de la cartera completa**  
   Calcular y mostrar `Avg Sentiment` global de la cartera en la fila `TOTAL` (por ejemplo ponderado por el tamaño de cada posición).

4. **Soporte multi-moneda**  
   Hoy todo se muestra como USD.  
   Próximo paso: poder mostrar cada posición en su moneda local (por ejemplo ARS) con conversión.

5. **Manejo de errores más robusto**  
   Mejorar el manejo si `yfinance` no puede devolver precio o un feed RSS falla.  
   Registrar esos errores en el Excel o en un log.

6. **Mini-gráficos / sparklines en Excel**  
   Insertar pequeñas series de sentimiento histórico directamente al lado de cada ticker en `Summary`.

7. **Alertas y backtesting**  
   Usar los cambios de señal BUY / HOLD / SELL para alertar cuando una acción se vuelve “BUY” o “SELL”, y trackear resultados históricos.
