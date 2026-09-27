# Qatar Stock Exchange (qe.com.qa) — reverse-engineered data endpoints

Reverse-engineered 2026-08-17 from `qe.com.qa`. Everything below was verified live
against the site except where marked **[untested]**.

## TL;DR — no cookies needed, but do not skip the POST for MarketWatch

The captured requests need **no cookies, no session, no CSRF token**. That part held up:
`PHPSESSID`, `JSESSIONID` and the `TS*` WAF cookies are all ignored.

**Correction to an earlier claim in this document.** I originally wrote that the two
`mw.php` POSTs were merely wrappers around static files, so you could always substitute a
plain `GET`. That is true for `Index` and `Indices`. It is **false for `MarketWatch`**, and
the failure is silent:

| Source | IGRD on 2026-08-18 | |
|---|---|---|
| `GET /wp/mw/data/MarketWatch.txt` | last 4.126 · vol 330,768 · low 4.121 | **frozen at 11:07, never advanced** |
| `GET /pps/qse_files/MarketWatch.txt` | last 3.468 · vol 6,842,901 | **stale by months** |
| `POST /wp/mw_app/mw.php` `f=MarketWatch` | last 4.107 · vol 4,112,307 · low 4.065 | **correct** |
| official `StocksSummary` for that date | close 4.107 · vol 4,112,307 · low 4.065 | ✓ matches the POST |

The static mirror served one frozen row for the whole session — same price, same volume,
from 11:07 to 13:39 — while the index feed beside it updated every 5 minutes. Nothing
errors; you simply get a flat line and a wrong price.

So: **POST for the live feeds, GET for everything historical.**

| What | How |
|---|---|
| Live per-instrument quotes | `POST /wp/mw_app/mw.php` `f=MarketWatch` |
| Live index | `POST /wp/mw_app/mw.php` `f=Index` (or the `.txt`, which agrees) |
| Live sector indices | `POST /wp/mw_app/mw.php` `f=Indices` |
| Every historical report | `GET /wp/trading_report_data/…` |

Note also that `www.qe.com.qa` and `qe.com.qa` are **different hosts**. `www.` fronts the
QDisclosure/Lightstreamer stack and did not resolve from where this was built; the bare host
serves the portal and both `mw.php` endpoints. Prefer the bare host.

## 1. Live market data — `POST /wp/mw_app/mw.php`

Plain JSON, no `for(;;);` prefix. Regenerates every 5 minutes during the session.
Each feed has a static mirror under `/wp/mw/data/`; the MarketWatch mirror is unsafe
(see above), the Index and Indices mirrors agree with the POST.

### `POST https://qe.com.qa/wp/mw_app/mw.php` with `f=MarketWatch`
One row per instrument (125 rows: equities, ETFs, bonds, sukuks, T-bills, venture). The
richest single response on the site — it carries the fundamentals that appear nowhere else.
**Use the POST, not `/wp/mw/data/MarketWatch.txt`** (see the correction above).

```
Topic Symbol CompanyEN CompanyAR Trend StateEN StateAR CatEN CatAR SectorEN SectorAR
ShariahEN ShariahAR CompType OfferVolume OfferPrice BidPrice BidVolume OpenPrice High
Low IMP NAV INAV LastPrice PrevClosing Change PercentChange Trades Volume W52High
W52Low Value CompMarketCap PERatio EPS Yield SubscribedShares NetProfit CashDividend
ReferencePrice PriceBook SectorCode IndexCode Market Order
```

`CompType` ∈ `COMP` (equity), `ETF`, `BOND`. `IndexCode` links a stock to its sector
index (`QIND`, `QBNK`, …). `SubscribedShares` = shares outstanding.
`PriceBook` is *live* (recomputed off `LastPrice`), so book value per share =
`LastPrice / PriceBook`.

### `POST … f=Index` (mirror: `/wp/mw/data/Index.txt`)
Single row for the QE Index (`QE20/ID`) plus whole-market aggregates split by segment:
`EqTrades/EqVolume/EqValue`, `SPTrades/SPVolume/SPValue`, `DebtTrades/…`,
`VentureTrades/…`, `MarketCap`, `EqMarketCap`, `VentureMarketCap`, `YTD`,
`UpComp/DownComp/UnchgComp`, `State` (`Pre-Open`, `Open`, `Close`), `LastUpdate`.

### `POST … f=Indices` (mirror: `/wp/mw/data/Indices.txt`)
13 rows — QE Index, Total Return, Al Rayan Islamic (price + TR), All Share, and the
seven sector indices. Fields: `Topic Symbol CompanyEN CompanyAR Trend CurrentIndex
PrevClosing Change PercentChange`.

### Real-time push (optional)
The ticker subscribes to **Lightstreamer** rather than polling:
`https://www.qe.com.qa/lightstreamer/` (TLCP 2.1.0), client at
`/wp/mw/js/lightstreamer.js` + `/wp/mw/js/lsClient.js`.
Items are `<SYMBOL>/NM` plus `QE20/ID`; schema
`ArabicName EnglishName Symbol LastPrice Change PercentChange CompType CompUp CompDown
CompUnChg Value`. Only worth wiring up if you need sub-second updates — the `.txt`
POST feeds cover everything else at 5-minute granularity. **[untested]**

---

## 2. Historical trading reports — `/wp/trading_report_data/…`

This is the backbone. `interactive-trading-reports` is a pure static-file browser:
`var jsonPath = "/wp/trading_report_data/"`.

**Path shapes** (from `func.trading_reports2025.js`):

| Period | Path | `DATE_TYPE` |
|---|---|---|
| Daily | `/wp/trading_report_data/YYYY/MM/DD/<File>.txt` | `Day` |
| Weekly | `/wp/trading_report_data/YYYY/MM/W<n>/<File>.txt` | `Week` |
| Monthly | `/wp/trading_report_data/YYYY/MM/<File>.txt` | `Month` |
| Yearly | `/wp/trading_report_data/YYYY/<File>.txt` | `Year` |

History verified back to **2020-01-02**. Non-trading days 404 (Fri/Sat weekend, plus
holidays — e.g. `2026/08/14` 404s, `2026/08/16` is a Sunday and exists).

### Periods only appear once they close

**A period is published only after it ends.** On 2026-08-17 the latest available were:
daily `2026/08/16`, weekly `2026/08/W2` (the 9–13 Aug week), monthly `2026/07`, yearly
`2025`. `2026/08` and `2026` both 404. So a "monthly" view is at worst six weeks behind
the live market — that is the exchange's cadence, not a pipeline limitation.

Aggregated periods are fully self-consistent: `OPEN_PRICE`/`HIGH_PRICE`/`LOW_PRICE`/
`CLOSE_PRICE` span the period, `PREVIOUS_CLOSE_PRICE` is the *prior period's* close, and
`CHANGE_PRCT` is the period change. Nothing needs recomputing from dailies.

### Weekly and monthly carry 12 files, not 15

Verified file-by-file across all four period types:

| File | daily | weekly | monthly | yearly |
|---|---|---|---|---|
| MarketSummary, IndicesSummary, Top5, InvestorActivity | yes | yes | yes | yes |
| StocksSummary, ETFsSummary, all bond/sukuk/T-bill/venture files | yes | yes | yes | yes |
| **OwnershipPercentage** | yes | — | — | — |
| **InsiderTrades** | yes | — | — | — |
| **MajorActivity** | yes | — | — | — |

Those three are daily-only. To show them on a weekly or monthly view, reconstruct:
`OwnershipPercentage` is a point-in-time register, so read it on the period's last
trading day and compare against the session *before* the period opened; `InsiderTrades`
is a flow, so sum `BUY`/`SELL` per (symbol, insider) across the period's sessions.

### Week numbering, and the boundary-week trap

Weeks run **Sunday-Thursday** and are numbered within the month. The counter advances on
a Sunday, but only once a trading day has already been emitted — so a month opening on a
Saturday (Aug 2026, Nov 2025) still starts at `W1`. Validated against the site for 36
weeks across nine months: 35 matched on the first try.

The exception is a week straddling a month boundary, which is filed under the **later**
month: `2026/01/W1` closes on **2025-12-31**, and `2026/06/W5` (28–30 Jun) is not
published at all — those sessions roll into `2026/07/W1`. Do not trust the calendar
mapping alone: pin the period's last trading day by matching the week's `INDEX_VALUE`
against daily closes.

**All 15 files:**

| File | Contents |
|---|---|
| `MarketSummary.txt` | `INDEX_VALUE TRADED_STOCKS TRADES_COUNT TRADES_VOLUME TRADES_VALUE GAINER_STOCKS LOSER_STOCKS QSE_MCAP` |
| `IndicesSummary.txt` | 12 rows: `INDEX_CODE INDEX_NAME INDEX_NAME_2 PRIORITY INDEX_CLOSING_VALUE CHANGE_VALUE CHANGE_PRCT` |
| `Top5.txt` | 20 rows, `DATA_TYPE` ∈ `TOP5VALUE TOP5VOLUME TOP5GAINER TOP5LOSER` |
| `StocksSummary.txt` | per-equity OHLC: `TRADES_COUNT TRADES_VOLUME TRADES_VALUE OPEN_PRICE HIGH_PRICE LOW_PRICE CLOSE_PRICE PREVIOUS_CLOSE_PRICE HIGH52 LOW52 CHANGE_PRCT CHANGE_VALUE` |
| `ETFsSummary.txt` | same shape, ETFs |
| `BondsSummary.txt` | + `BNDNXTCPN BNDPRVCPN BNDACCINT` |
| `GovernmentSukuksSummary.txt` | " |
| `CorporateBondsSummary.txt` | " |
| `CorporateSukukSummary.txt` | " |
| `TBillsSummary.txt` | " |
| `VentureSummary.txt` | venture market equities |
| `InvestorActivity.txt` | buy/sell split by nationality × investor type — see below |
| `OwnershipPercentage.txt` | per-symbol register split by nationality × investor type |
| `InsiderTrades.txt` | `SYMBOL_CODE … NIN_NAME BUY SELL` |
| `MajorActivity.txt` | sector-grouped notable movers |

**Two parsing gotchas:**

1. Every response is prefixed with the anti-JSON-hijacking guard `for(;;);` — strip it
   before `json.loads`.
2. `Top5.TVALUE` is **polymorphic**: traded value for `TOP5VALUE`, share volume for
   `TOP5VOLUME`, and percent change for `TOP5GAINER`/`TOP5LOSER`.

`InvestorActivity.txt` shape — `natgrp` ∈ `QTR GCC ARB FRN`, `invtype` `I`=Individuals /
`C`=Institutions, `net_buy`/`net_sell` are the nationality totals as % of market value:

```json
[{"natgrp":"QTR","net_buy":31.5,"net_sell":75.983,
  "Data":[{"invtype":"I","Data":[{"trade_type":"Buy","companies":"50",
           "traded_value":"122832155.722","traded_volume":"60216900","prct":16.58}]}]}]
```

`OwnershipPercentage.txt` is the same nesting, with
`natgrp_count / natgrp_shares / natgrp_prcnt` per cell. Institutional ownership % =
sum of all `invtype == "C"` cells.

---

## 3. Company profile

### `GET https://qe.com.qa/pps/dfiles/compprofile/<CODE>_Issue_Information.xml`
XML, no auth. `<Issuer_Information>` contains:

- `HistPrice` × 5 — `HDate HCPrice HVolume` (only 5 rows, and **stale**: as of
  2026-08-17 the newest row was 2026-06-16. Do not rely on it for prices.)
- `IndexWeight` — weight in QE Index / All Share / Al Rayan Islamic / sector index,
  each with a `url` to the constituents `.xlsx`
- `Limits` — `AuthCapital PaidCapital TotalShares FreeFloatShares FOLperc FOLshares
  MaxSOLperc MaxSOLshares`
- `MajHolder` × n — `Ownership TotSecOwned HoldName HoldNameAR`
- `EGM_AGM`, `Distribution` × n (`Type DecDate RecDate ExDate Amount`)
- `Insiders` × n — `InsiderName InsiderJobDescription`

The `?r=<int>` in the captured request is just a cache-buster; omit it or send anything.
It is fetched with `POST` by the site but responds to `GET`.

### Market-wide news — `POST /wp/mw_app/mw.php` with `f=News`

**This is the news feed to use.** One ~108 KB POST returns ~200 items covering every
listed company, roughly 18 months deep. Plain JSON, no cookies, no scraping.

```
InformationTypeDetailID  Headline  Summary  PublishDate  UpdatedDate
Image  IsBreakingNews  BreakingNewsDisplayDuration
```

Detail page per item: `/displaynewsdetails?InfoID=<InformationTypeDetailID>`.

Two gotchas:

- **IDs are not chronological.** `46774` publishes at 07:21 while `46768` publishes at
  07:40. Sort on `PublishDate`, never on the id.
- `IsBreakingNews` is `Y`/`N`, useful for highlighting.

Only `f=News` works on this endpoint; `f=LatestNews`, `f=Announcements` and `f=Disclosure`
all return `[]`.

### Company news (superseded — prefer `f=News` above)
There is **no JSON API** for the per-company view. The news is server-rendered into the company-profile HTML as a
URL-encoded XML blob in a JS variable:

```
GET /web/guest/company-profile?InformationCategory=Company&InformationType=News
    &CompanyCode=IGRD&FromLocalSite=N&MoreNewsTitle=1
```
→ `var request_NewsEventsOnQuoteDetailPage_responseXML = '%3CServletOutputXML%3E…'`

Decode with `unquote_plus` and parse. `ServletInnerXML` normally contains **real nested
elements** (`ServletInnerXML/OutputStructure/OutputMessage/News`), not an escaped string —
`findtext("ServletInnerXML")` returns empty and looks like a failure. Some responses do
deliver it escaped, so handle both. Each `<News>` gives `InformationTypeDetailID
InformationTypeID InformationCategoryID Headline Summary Description PublishDate
Image IsInformationFromLocalSite`, plus `<TotalRecords>` (276 for IGRD).

Two hard limits, both verified:

- **Only the 6 most recent items are rendered.** `TotalRecords` is not reachable —
  `NumberOfElements`, `PageSize`, `PageNumber` and `Page` are all ignored. Full detail per
  item is at `/displaynewsdetails?InfoID=<InformationTypeDetailID>`.
- **`InformationType` is ignored.** `Events`, `PressRelease` and `CorporateAction` all
  return the same six News items, always under a `<News>` tag.

Cost comparison, which is why `f=News` wins outright: the per-company page is ~400 KB for
6 items (67 KB/item), a `displaynewsdetails` page is 244 KB for **one** item, and `f=News`
is 108 KB for 200 items (0.5 KB/item).

### Financial statements (XBRL)
`https://www.qe.com.qa/qdisclosure/api/XBRL/GetFinancialStatementsAPIData`
`?symCode=<CODE>&reportEndDate=<date>&sectionName=<financialPosition|statement|Cashflow>&getFilingDetails=<0|1>`
plus `GetFSAttachmentAPI` and `CheckFSAttachmentExistAPI` (same params + `lang=1|2`,
`attachmentType`). Attachments download via
`/qdisclosure/api/NonFS/downloadAttachmentFileAPI?ig=<guid>`. On the `www.` host.
**[untested — `www.qe.com.qa` was unreachable from the environment used for discovery]**

### Other static assets
- `https://qe.com.qa/pps/companylogos/<CODE>.jpg`
- `https://qe.com.qa/pps/qse_files/MarketWatch.txt` — a second, older MarketWatch copy

---

## 4. Field → PDF-dashboard mapping

Where each number on the Estithmar daily dashboard comes from:

| Dashboard field | Source |
|---|---|
| Open / High / Low / Closing / Previous Close / Change / Change % | `StocksSummary.txt[date]` |
| Volume / Value | `StocksSummary.txt[date]` `TRADES_VOLUME` / `TRADES_VALUE` |
| 52 Weeks High / Low | `StocksSummary.txt[date]` `HIGH52` / `LOW52` |
| Number of shares | `MarketWatch.txt` `SubscribedShares` |
| Market Cap | shares × close (derived) |
| Price to book | close ÷ (`LastPrice`/`PriceBook`) (derived — see caveat) |
| Dividend (Yield) | `MarketWatch.txt` `Yield` / `CashDividend` |
| 1-Year Change | close ÷ close one year earlier (`StocksSummary.txt[date-1y]`) |
| Cap rank to QE Market / to Sector | rank of shares × close across `StocksSummary` (derived) |
| QE Index value / Change / Change % | `IndicesSummary.txt[date]` `GNRI` |
| QE Index Volume / Value | `MarketSummary.txt` + `VentureSummary.txt` |
| Highest / Lowest Value 52 Weeks | max/min of `MarketSummary.INDEX_VALUE` over 52w (derived) |
| Top Gainers / Losers / By Value / By Volume | `Top5.txt` |
| Compared to Market & Sector | share `CHANGE_PRCT` + `GNRI` + sector index from `IndicesSummary` |
| Indices Performance | `IndicesSummary.txt`, codes `QBNK QCON QIND QINS QREA QTLC QTRN` |
| Qatar Market Shareholders Activity | `InvestorActivity.txt` |
| Ownership by Nationality (2 days) | `OwnershipPercentage.txt[date]` + `[prevDate]` |
| Institutions Shares in \<company\> | sum of `invtype == "C"` in `OwnershipPercentage.txt` |
| Insider Trades | `InsiderTrades.txt` |

### Three places the PDF does not reconcile

Verified against 2026-08-13 — 40-odd figures match to the decimal, but three do not:

1. **Index 52-week high / low.** PDF says `11,129.890` / `9,296.470`. Over the 247
   trading days to 2026-08-13 the QE Index closed between `9,920.69` (2026-07-30) and
   `11,648.81` (2025-08-14). The PDF's high is *below* the actual high, so it is not a
   different window on the same series — it is a different source. The PDF's own
   percentages don't close either: `10,020.84 / 9,296.47 − 1 = 7.79%`, not the 7.23%
   printed. This pipeline computes it from QE closes and reports its own numbers.
2. **"53 Weeks Low" `3.410`.** QE's own `LOW52` for IGRD on that date is `3.435`.
3. **QE Index Volume / Value.** PDF `238,398,584` / `741,528,961.455`; main + venture
   from QE is `238,373,136` / `741,474,285.813`. A ~25k share / ~55k riyal gap — most
   likely one more segment (debt or special-purpose trades) folded in.

Also note **`priceToBook` for a historical date is an approximation**: `PriceBook` only
exists in the live feed, so book value per share is taken from today's live snapshot and
re-applied to the historical close. It is exact for today, and drifts by however much
equity has moved since. (For 2026-08-13 it reproduces the PDF's `3.718` exactly.)

---

## 5. How often the data actually changes

Measured on 2026-08-17 with the market open, polling `/wp/mw/data/Index.txt` every 15s:

- **The live files regenerate every 5 minutes.** The grid is offset 2 minutes past the
  hour, not on the round mark: observed `LastUpdate` values `09:27:02`, `11:27:02`,
  `11:32:02`, `11:37:02`, `12:02:02`, `12:07:02` — every one ≡ 2 (mod 5) minutes, at `:02`
  seconds. So the ticks are `…:02, :07, :12, :17, :22, :27…`, never `:00` or `:05`.
  Polling faster than 5 minutes returns byte-identical data.
- Two CDN copies are in rotation, alternating between `:02` and `:03` in the timestamp.
  Same data; don't treat the one-second flip as a change.
- Between two ticks (12:02 → 12:07) the QE Index moved 9,930.22 → 9,933.89 and trades
  19,840 → 20,337. So roughly 500 trades and a few index points per tick.
- Session is **Sunday-Thursday, 09:30-13:15 Qatar time (UTC+3)**. `Index.txt` `State`
  goes `Pre-Open` → `Open` → `Close`.
- **The current session's report files do not exist until after the close.** During
  trading hours the newest daily report is yesterday's; only `/wp/mw/data/*.txt` moves.

A 30-minute rebuild is therefore comfortably inside the feed's own cadence — it will
never be more than 5 minutes behind the site itself, and there is nothing to gain from
polling more often than every 5 minutes.

## 6. Rate limits, robustness

No rate limiting observed; 250 sequential daily fetches ran clean. The files are
CDN-fronted static assets, so they are cheap — but be polite: cache aggressively, and
back off on non-200.

Failure modes to expect:
- Non-trading day → `404` with an HTML error page. Detect by status, not by parsing.
- WAF challenge → `200` with HTML. Always check the body starts with `{`, `[` or `<?xml`.
- `for(;;);` guard present on `/wp/trading_report_data/`, absent on `/wp/mw/data/`.
