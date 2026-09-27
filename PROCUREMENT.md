# Market data licensing — what to ask procurement for

Purpose: replace the qe.com.qa scraper with a licensed feed. This is the requirements
pack — hand it to procurement as the basis for an RFI.

Written from a working implementation, so the field list is what the dashboard actually
consumes, not a wish list. Field-by-field origins are in [API_REFERENCE.md](API_REFERENCE.md).

---

## 1. Read this before contacting any vendor

**The requirement splits into two very different halves, and conflating them is how this
procurement goes wrong.**

| | A — Commodity market data | B — QSE-proprietary datasets |
|---|---|---|
| What | prices, OHLCV, index levels, sector indices, fundamentals | ownership by nationality, investor activity by nationality × investor type, insider trades |
| Who has it | every global vendor | realistically **only the exchange**, or a Gulf-specialist redistributor |
| Risk | none — commoditised, competitive | **this is the hard part** |

Half A is easy to buy and easy to price. Half B is the reason the scraper exists: those
three datasets are published by Qatar Stock Exchange as part of its own market reports and
are **not standard products** in global market-data catalogues. A vendor can honestly say
"yes, we cover QSE" and still not have any of Half B.

**So the single most important instruction to procurement: do not accept "we cover Qatar"
as an answer. Require a field-level response to §3, and require sample data.**

If Half B turns out to be unlicensable, that is a real finding — it changes the dashboard
scope, and it is much better to learn it during the RFI than after signing.

---

## 2. Where to send the RFI

Verify coverage in every case; none of this is confirmed from our side.

**Start here — the exchange itself.** QSE operates market-data licensing and a vendor
programme. It is the origin of every dataset we need, including all of Half B, and is the
only party who can license Half B authoritatively. Ask for their market data licensing /
information-products team.

**Global vendors — for Half A, and to test Half B claims.** LSEG (Refinitiv), Bloomberg,
S&P Global Market Intelligence, FactSet, SIX, Morningstar. Expect strong Half A, and expect
Half B to be absent or partial.

**Gulf / MENA specialists — most likely to have Half B if the exchange itself is slow.**
DirectFN / Mubasher and comparable regional redistributors build products specifically
around GCC exchange reports.

**API-first, lower cost — worth an RFI purely on price.** EODHD, Twelve Data, Intrinio,
Financial Modeling Prep, Marketstack, Finage. Expect end-of-day OHLCV at best; treat QSE
coverage and corporate-action quality as things to prove, not assume.

**One more, specific to the share graph.** The intraday chart in the source dashboard is
served by **Euroland IR** (`tools.eurolandir.com`), which is the issuer's IR-website vendor.
If Estithmar's IR team already pays Euroland, intraday history for that symbol may already
be inside a contract the group holds — worth an internal check before buying it again.

---

## 3. Field-level requirements

Give the vendor this table and require a per-row yes / no / partial answer.

### 3A. Per-instrument, per-period (daily, weekly, monthly)

```
open  high  low  close  previousClose  changeValue  changePct
volume  tradedValue  tradesCount
high52  low52
sharesOutstanding  marketCap
eps  peRatio  priceToBook  bookValuePerShare
dividendPerShare  dividendYieldPct
sector  sectorIndexCode  ISIN  currency
```

Two notes that matter commercially:

- **We need weekly and monthly as the exchange computes them**, not as something we
  re-aggregate. The exchange's weekly/monthly records carry their own `previousClose` and
  period change; re-deriving them from dailies produces numbers that do not tie to
  published reports.
- **`priceToBook` must be a real point-in-time value.** Our current implementation
  approximates historical P/B by applying today's book value per share to a historical
  close — documented, but wrong for any date but today. A licensed feed should fix this.

### 3B. Index and market aggregates

```
QE Index level, change, changePct
all sector indices (7) — level, change, changePct
QE All Share, Total Return, Al Rayan Islamic (price + TR)
market volume, traded value, trades count, market cap
traded / gaining / losing instrument counts
52-week index high and low
```

### 3C. Market breadth

```
top 5 gainers, losers, by traded value, by volume — per period
```

### 3D. **Half B — the QSE-proprietary datasets.** Ask explicitly, by name.

**Ownership register by nationality and investor type**, per instrument, per session:

```
nationality ∈ {Qatari, GCC, Arab, Foreign} × investorType ∈ {Individual, Institutional}
→ holderCount, shares, percentOfRegister
```

**Investor activity (traded value share) by nationality and investor type**, per session,
market-wide:

```
nationality × investorType × {Buy, Sell}
→ instrumentCount, tradedVolume, tradedValue, percentOfMarketTradedValue
plus per-nationality total buy % and total sell %
```

**Insider trades**, per session: instrument, insider name, shares bought, shares sold.

Also worth asking for, since the exchange publishes them and we currently do not use them:
major shareholders, free-float and foreign-ownership limits, index constituent weights,
corporate actions and dividend history, disclosures/news, XBRL financial statements.

### 3E. Intraday

```
intraday price and volume — state the granularity offered (tick / 1-min / 5-min)
history depth for intraday, and whether it is backfillable
```

**This is currently our biggest gap.** qe.com.qa publishes no intraday history at all, so
our intraday series only exists from the moment we started polling and can never be
backfilled. **Ask specifically for historical intraday** — it is the one thing a licence
buys that we cannot obtain at any effort.

### 3F. History depth

Ask for **at least 5 years** of daily history, and state your real need. Our scraper reaches
back to 2020-01-02; a licence should not be a downgrade. Confirm the history is
**corporate-action adjusted** and that both adjusted and unadjusted closes are available —
Estithmar had a 10% stock dividend in March 2025, so unadjusted series break across it.

---

## 4. Commercial terms — ask these before asking about price

These determine the price bracket far more than the field list does. Getting them wrong is
the standard way a data contract turns out to cost several times the quoted figure.

1. **Display vs non-display.** A dashboard that shows prices to humans is *display* use.
   Feeding prices into a model or an algorithm is *non-display* and priced separately.
   State that we need display, and say whether any non-display use is planned.
2. **Redistribution — the one to get right.** If this dashboard is shown to PIH, or carries
   Datategy branding for a client, that is likely **redistribution / external
   distribution**, not internal use. It is a different and much more expensive licence
   tier. Declare the intended audience up front; discovering this after signing an internal
   licence is a compliance problem, not just a cost one.
3. **Derived data rights.** We compute market cap, cap ranks, price-to-book and 52-week
   ranges from the feed. Confirm derived values may be displayed and stored.
4. **Storage and retention.** We keep an on-disk archive. Confirm we may retain history
   after the licence ends, or negotiate what happens to it.
5. **User counts and named users.** Per-seat, per-server, or enterprise. Say how many
   people will see the dashboard.
6. **Real-time vs delayed.** Real-time is the expensive tier. **We probably do not need
   it:** the site's own feed only regenerates every 5 minutes, so 15-minute delayed data is
   barely worse than what we have today. Quote **delayed as the base case** and real-time
   as an option — this is likely the single biggest cost lever.
7. **Symbol scope.** Whole market (54 listed equities + ETFs + debt) or a named watchlist.
   Whole-market is cleaner and often not much dearer; per-symbol pricing gets expensive as
   coverage grows.
8. **Term and exit.** Contract length, notice period, price escalation, and what breaks if
   we leave.

---

## 5. Technical requirements

```
REST/JSON (or documented alternative); OpenAPI spec
authentication: API key or OAuth2 — no cookie/session schemes
documented rate limits, and a quota that supports 5-minute polling of ~54 instruments
sandbox / trial credentials before signature
symbology: QSE ticker AND ISIN, with a mapping file
explicit timezone on every timestamp (we operate in Asia/Qatar, UTC+3)
trading-calendar endpoint — sessions, holidays, and the Sunday–Thursday week
bulk historical download, not just per-symbol paging
uptime SLA, incident channel, deprecation policy with notice period
support contact and response times
```

Two hard-won requirements worth naming explicitly, because our current source fails both:

- **A stale response must be distinguishable from a fresh one.** One qe.com.qa endpoint
  serves a frozen row for hours with no error — same price, same volume, mid-session. Ask
  for a per-record `asOf` timestamp and a documented freshness guarantee.
- **Missing data must return an error, not stale or partial data.** Silent staleness cost us
  a full session of corrupt intraday capture.

---

## 6. Acceptance test — put this in the contract

Do not accept a vendor on a demo. Require sample data for **2026-08-18, symbol IGRD**, and
check it against the exchange's own published figures:

| Field | Must equal |
|---|---|
| close | 4.107 |
| volume | 4,112,307 |
| high / low | 4.186 / 4.065 |
| previous close | 4.167 |
| change % | −1.44% |
| shares outstanding | 4,493,329,500 |
| QE Index close | 9,848.10 |

Then require **one Half B sample** — the ownership register and investor activity for the
same date. If a vendor cannot produce those two tables, they cannot replace the scraper,
whatever else they offer.

We can run this comparison automatically: the pipeline already reproduces these numbers, so
a vendor's sample can be diffed against ours field by field.

---

## 7. What this changes on our side — almost nothing

Worth telling procurement, because it strengthens the negotiating position: **we are not
locked in, and we can run a vendor in parallel before committing.**

The pipeline has exactly one file that touches the network (`qse/client.py`). Everything
downstream works on plain data and does not know where it came from — which is why the test
suite runs with the network unplugged. Swapping to a licensed API means reimplementing that
one file against the new endpoints. The dashboard, the derivations and the archive are
untouched.

So we can:

- trial two vendors against the same dashboard and compare output directly,
- keep the scraper running during migration as a cross-check,
- and walk away from a vendor without rewriting the product.

---

## 8. One thing to flag to legal, separately

The current implementation reads public qe.com.qa endpoints without authentication. That is
fine for internal analysis, but **exchanges generally restrict redistribution of market
data**, and a Datategy-branded dashboard shown to a client is redistribution. This is a
reason to license regardless of what the scraper can technically do — worth stating plainly
in the business case rather than leaving procurement to discover it.
