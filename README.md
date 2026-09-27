# Qatar Stock Exchange → JSON → dashboard

A Streamlit app that pulls everything on `qe.com.qa` and rebuilds the Estithmar dashboard
from it, refreshing every 5 minutes.

```bash
pip install -r requirements.txt
streamlit run app.py
```

That is the whole thing. Pick a company in the sidebar; every section follows.

**The captured cookies and tokens are not needed.** The two `mw.php` POSTs are wrappers
around static files that answer a plain `GET`. Full endpoint map, schemas and gotchas:
[API_REFERENCE.md](API_REFERENCE.md).

## The app

Native Streamlit — dense tables, Altair charts, no iframe. **Designed to fit one screen**:
sections are sized so nothing hides behind a scrollbar and every table row is visible.

```
┌ Estithmar Holding · IGRD ────────────────── [Open] [QE 9,871 −0.21%] [IGRD 4.126] [YTD] ┐
│ [1D 1M 3M Max]              [daily weekly monthly]                                 [⤓] │
├───────────────────────────────┬──────────────────────┬──────────────────────────────────┤
│ price line + volume columns   │ Share · 20 figures   │ QE Index · 14 figures            │
├──────────────┬────────────────┼──────────────┬───────┴──────────────────────────────────┤
│ vs mkt/sector│ sector indices │ ownership    │ register                                 │
├──────────────┴───┬────────────┴──┬───────────┴────┬─────────────────────────────────────┤
│ gainers          │ losers        │ by value       │ by volume                           │
├──────────────────┴───────────────┴────┬───────────┴─────────────────────────────────────┤
│ shareholders activity                 │ insider trades                                  │
└───────────────────────────────────────┴─────────────────────────────────────────────────┘
```

Four decisions made it fit, each of which also made it easier to read:

- **Label/value tables, not metric tiles.** A `st.metric` tile is ~90px; twenty of them is
  four rows and most of a screen. The same twenty figures take about a fifth of that here.
- **Static tables, not `st.dataframe`.** A dataframe gives ~35px rows and hides the rest
  behind a scrollbar — showing two of five movers defeats the point. Every row is visible.
- **The activity table is pivoted** to one row per nationality (individual buy/sell,
  institutional buy/sell, totals). The long form is 16 rows.
- **Large figures are abbreviated** — `4.49B`, not `4,493,329,500`. In a narrow column the
  full numeral gets clipped to `4,493,329,5…`, which reads as a different number.

Everything refreshes together: the page is one `st.fragment(run_every=300)` and every fetch
sits behind a `ttl=300` cache, so clicking a widget re-renders from cache instead of
refetching the market. Exports (bundle JSON, three CSVs, printable HTML) are in the `⤓`
popover on the selector row, so they cost no vertical space.

## The CLI is still there, for cron

`qse.py` covers the same pipeline headlessly — useful for scheduling, not needed for daily
use. `python3 qse.py dashboard IGRD` writes the JSON bundle and the standalone HTML;
`watch` loops; `raw` dumps every feed verbatim; `series` exports index history.

## Does the data actually change? Yes — every 5 minutes

Measured with the market open, polling every 10-15 s:

- **The live feeds regenerate every 5 minutes**, on a grid offset 2 minutes past the hour
  (`…:02, :07, :12, :17…` at `:02` seconds) — not on the round mark. Confirmed over three
  consecutive ticks: `12:37 → 12:42 → 12:47`. Polling faster returns identical bytes.
- Session is **Sunday–Thursday, 09:30–13:15 Qatar time**. Observed `State` values:
  `Pre-Open`, `Open`, `TAL`, `Closed`.

**One trap, and it is silent.** The live per-instrument feed must come from
`POST /wp/mw_app/mw.php` `f=MarketWatch`. Its static mirror
`/wp/mw/data/MarketWatch.txt` **freezes mid-session** — on 2026-08-18 it served IGRD at
4.126 / 330,768 from 11:07 right through to 13:39, while the session actually closed at
4.107 / 4,112,307. Nothing errors; you just get a flat line and a wrong price. Detail in
[API_REFERENCE.md](API_REFERENCE.md). The client POSTs first and keeps the mirror only as a
fallback.

One more thing to know: **the current session's report files only publish after the close.**
During trading hours the newest daily period is the previous session, and only the live
header moves. That is the exchange's behaviour, not the pipeline's.

## The three reporting periods

| Tab | Source | Latest available on 2026-08-17 |
|---|---|---|
| Daily | `/wp/trading_report_data/YYYY/MM/DD/` | 16 August 2026 |
| Weekly | `…/YYYY/MM/W<n>/` (Sun–Thu) | 9–13 August 2026 |
| Monthly | `…/YYYY/MM/` | July 2026 |

**Periods publish only once they close**, so Monthly can be up to six weeks behind — again
the exchange's cadence. A period with nothing published yet simply does not appear in the
selector.

Weekly and monthly carry 12 of the 15 report files — no `OwnershipPercentage`,
`InsiderTrades` or `MajorActivity`. Those are reconstructed: the ownership register is
read at the period's last trading day and compared against the session *before* the
period opened, and insider trades are summed per insider across the period's sessions
(the panel says which). Everything else comes straight from the period's own file, so
weekly OHLC, change % and index moves are the exchange's numbers, not re-derived ones.

## What comes out

`out/dashboard_<SYM>.json` — `meta`, `live`, and `periods.{daily,weekly,monthly}`, each
carrying `period`, `share`, `index`, `comparison`, `sectorIndices`, `allIndices`,
`topGainers/Losers/ByValue/ByVolume`, `shareholderActivity`, `ownership`, `insiderTrades`,
`indexSeries`. Sample: [sample/dashboard_IGRD_2026-08-13.json](sample/dashboard_IGRD_2026-08-13.json).

`out/raw/…` — the untouched feeds: `live/*.json`, `reports/<kind>/<period>/*.json`,
`company/<SYM>/{issue_information,news}.json`.

The HTML is one self-contained file — no external assets, so it survives being emailed or
opened from disk. Tab switching is pure CSS and works with JavaScript disabled. The page
carries its own bundle in a `<script type="application/json" id="bundle">` tag, so it is
also its own data export.

## The archive — every refresh persisted

Archiving is **on by default**. Each build writes to `out/archive/`, shaped by how long
each kind of data actually lives:

```
out/archive/
  live/index/2026-08-18.jsonl        one line per 5-min tick, market-wide
  live/IGRD/2026-08-18.jsonl         one line per tick, that symbol's quote
  live/QNBK/2026-08-18.jsonl
  market/2026-08-18.jsonl            every instrument per tick (opt-in)
  periods/IGRD/daily/2026-08-17.json one file per closed period, write-once
  periods/IGRD/weekly/2026-08-W2.json
  periods/IGRD/monthly/2026-07.json
  manifest.json                      index of everything on disk
```

The index tick is split from the symbol tick because it is symbol-independent — tracking
ten companies should not store the same QE Index reading ten times.

**The tick logs are the point.** qe.com.qa keeps daily/weekly/monthly reports back to
2020, so any period bundle can be rebuilt on demand — but it publishes **no intraday
history at all**. A tick that isn't captured is gone for good. So that is what the archive
is really for; period bundles are stored write-once because a closed period never changes,
and re-saving them every 5 minutes would just churn identical bytes.

```bash
python3 qse.py watch IGRD --refresh 300                    # archives as it goes
python3 qse.py watch IGRD --refresh 300 --archive-market    # + every instrument
python3 qse.py archive                                      # what's stored
python3 qse.py dashboard IGRD --no-archive                  # opt out
```

**Deduplication is on the feed's own timestamp truncated to the minute, per stream.** Two
things forced that: the refresh interval and the exchange's 5-minute cadence drift against
each other, and the feed republishes one tick with its seconds field flipped (`10:22:02` and
`10:22:03` are the same tick). Poll as often as you like, from the CLI or the Streamlit app,
and you get exactly one line per real tick per stream.

Size: a tick is ~350 bytes, so a session is ~16 KB and a year ~4 MB. With
`--archive-market` a tick is ~25 KB — ~1 MB a session, ~250 MB a year.

JSONL is chosen so appends never rewrite the file and analysis is one line:

```python
import pandas as pd
ticks = pd.read_json("out/archive/live/2026-08-18.jsonl", lines=True)
```

## The share graph

One chart, one range selector. `1M` upward are daily closes from `StocksSummary`, reaching
back as far as the report tree does — verified to 2020-01-02. `--history-days` (or the
sidebar slider) sets the window.

**`1D` is intraday, rebuilt from your own tick archive.** qe.com.qa publishes no intraday
history, so it cannot be backfilled — it accumulates one point every 5 minutes while the app
is open. When the archive has fewer than six ticks for the current session, the `1D` pill
simply is not offered; there is no placeholder panel.

Price is a line above, volume columns below, sharing one x-axis — **not** a dual-axis chart.
A second y-scale would let a reader read a price/volume relationship out of whatever the
scales happened to be.

Two rendering traps this chart hit, both now pinned by tests:

- **An area mark's implicit baseline is `y=0`.** On a price scale whose domain excludes zero,
  Vega clips the entire geometry and the chart renders its axes with no data at all. The fill
  is a separate layer with `y2` pinned to the domain floor.
- **A near-flat stretch** on an auto-fitted axis reads as a cliff, so the band has a floor of
  ±0.5% of the price level.

**The Euroland graph is not wired up.** `probe_euroland.py` is a discovery script for
`tools.eurolandir.com` — run it locally and it writes `euroland_probe.json`. That host is
unreachable from the environment this was built in, so the series above come from QSE data.
Euroland is the only route to *historical* intraday; everything else it shows, the QSE feeds
already cover.

## The register — book of record

The third tab is the **reporting** half of the register work, and it comes first on
purpose: before anything is discovered, the book has to be readable the way a
shareholder-services team already reads it. It replicates what the client's own files
publish, and extends it.

**What the supplied PDFs actually contain**, once page 2 is read: three cuts of the
register — above 500K, companies & funds, and the full list — each as a **two-period
comparison with a difference column**, ending on two lines:

```
Total                                                     123,469,089  2.75%  →  456,834,723  10.17%  +7.43%
Total Without Related Parties (UCC, Infra Road & H'Collective)  12,177  0.00%  →   45,144      0.00%  +0.00%
```

Those two lines are reproduced verbatim in shape, related-party exclusion included. The
three names are spelled out rather than being a flag only the system knows, because that
is how the client's file spells them.

**Added on top:** a top-200 long list; local against international and the four regional
buckets; the passive/active class split; related parties and board seats as their own
cuts; who entered and who left; and every split as a month-over-month series.

### Nothing on this tab infers

A figure here is a number in the register or a subtraction of two of them, and the tests
assert that: every cut and every segment must reconcile to the snapshot it came from. The
one exception is the watchlist, and it is marked as such — **each item carries the rule
that fired it and the figure that tripped it**, so a threshold you disagree with is one
number to change rather than an opinion to argue with.

The watchlist reports a **change of state, not a standing fact**. A holder that has sat
above the 5% disclosure threshold for two years is already disclosed; re-flagging it every
month buries the one line that matters under four that do not. What earns a place is a
crossing in either direction, an approach from below, a material move by someone already
above, a top-50 holder leaving, a new holder arriving above 500K, or the shape of the book
moving — concentration, nationality or class.

### Two things the data had to get right first

**Holders enter and leave.** The generator used to carry a fixed 100 holders present in
every month, which makes "who entered and who left" an empty table and a top-200 cut
impossible. It now carries 250 across the panel, of which about one in seven is not there
throughout.

**A holder that did not deal shows no change.** This one is easy to get wrong and obvious
once seen. The generator used to rescale every holding each month so the book still
totalled 4.49B shares, which silently moved holders who never traded — a register where
all 226 names change every single month is not a register. The tracked holders are now the
top of the book rather than all of it, an untracked tail absorbs what they buy and sell,
and a holder who stands still reports `+0.000pp / held`. In a typical month about 90 of
226 deal and the rest do not move at all.

That second change is also why the scan and the book are computed separately: correlation
detectors need a holder present in every month, so `discover.py` runs on the balanced
subset and says how many holders it therefore could not look at, while the book reports
all of them.

## The register scan

The fourth tab reads a **shareholder register** — one row per holder, one snapshot per
month — and reports the structure in it. The exchange publishes ownership only as seven
nationality x investor-type buckets, so nothing below is visible in its own reporting.

**The panel is synthetic, and has to be.** The three register PDFs in this folder carry
the schema and nothing else: names are `x`, NINs are `123`, every share count and
percentage is a placeholder. `synth/generate.py` therefore builds 100 holders across 24
monthly snapshots, anchored to the cohort splits and the 4.49B share count qe.com.qa does
publish, so the book reconciles against real figures even though no holder in it is real.
Five behaviours are planted. `synth/discover.py` is never told what they are and has to
find them from the panel alone — `out/synth/_ground_truth.json` is written by the
generator and read only by the scoreboard, never by the scan.

Everything works identically on a real register; only `load()` changes.

### What it reports

**Five detectors**, each firing only above its own threshold: co-movement, mirrored flow
(an off-market transfer rather than open-market trading), reduction in the month before a
negative disclosure, response to price, and metronomic accumulation toward the 5%
disclosure threshold.

On the panel as generated they return **five findings for five planted behaviours, and
nothing else** — every finding corresponds to something that was actually put there, and
no holder is flagged that was not. A detector that also reports four things nobody planted
is not more sensitive, it is less useful.

**An archetype for every holder, not only the flagged ones.** The detectors describe the
exceptions; this describes the book — quiet accumulators, coordinated holders, momentum
chasers, contrarian buyers, the exiting tail, and the stable core that in a healthy
register is most of it. Each card gives the count, the share of float and the
average move.

Two things make the classification portable rather than tuned:

- **Thresholds calibrate on the register itself.** "Active" means a multiple of *this*
  book's median idiosyncratic volatility, not a constant. A thinly held register and a
  liquid one differ by an order of magnitude in monthly variance, and a number fitted to
  one classifies the whole of the other.
- **Precedence is by specificity, not alphabet.** Accumulation is tested first because it
  is the only pattern with a regulatory consequence, then a direct pairwise link, then a
  response to price, and "Stable core" is last because it is the residual rather than a
  finding.

**The register as a chart.** Co-movement and mirroring already *are* a graph; printing
the three strongest pairs as text throws the shape away. Every holder is drawn, and
**nothing on it is positioned by the drawing code.** Across is where a holder ended up —
shares held now divided by shares held at the start of the panel, on a log axis so halving
and doubling sit the same distance either side of 1.0. Up is how it got there — the size
of a typical single month's change in that holding, measured once the register's common
factor is removed, because a register is zero-sum in percentages and a cohort adding 6%
moves everyone else's line without anyone trading.

**The second axis is consistency, not growth**, and that is what makes it worth spending
an axis on: two holders can both finish unchanged, one having never moved and the other
having swung hard and come back. Ardent Emerging Mkts tripled while never moving more than
0.6% in a month — bottom right, on its own — and Blackwater Frontier lost two thirds at
12.6% a month, top left. Position alone separates a plan from a panic. Area is the holding, colour is the archetype, so the
cards above are the chart's legend rather than a second one competing for the corner.

That the coordinates are real figures is the whole point, and it was learned the hard way.
An earlier version placed holders on concentric rings — linked groups spaced evenly on an
inner circle, everyone else around a rim. It was tidy, deterministic, and wrong twice
over. Position carried no information, so the eye searched it for meaning and found none.
And exact circles with dots at exact equal angles are not a thing any real shareholder
book produces: **a drawing of real data that looks manufactured discredits the data.** On
real axes the cloud comes out irregular because the numbers are, which is what a register
actually looks like — a dense core that barely moves, and a few holders on their own where
the eye goes first.

The lines become evidence rather than decoration for the same reason. Holders that move
together land next to each other and are joined by a short blue link; the two sides of a
transfer land on opposite sides of the plot, and the red line drawn between them crosses
the whole chart.

Two details that keep it readable:

- **Only each holder's strongest few links are drawn.** Any group sharing a common driver
  correlates pairwise across the whole group, so n holders can produce n(n-1)/2 edges that
  all repeat what the group already says by existing. Nothing is dropped from the
  analysis, and tests assert thinning never splits a group or orphans a linked holder.
- **Only holders that left the pack are named** — both halves of a linked pair, anything
  outside the unremarkable band on either axis. A hundred labels in the middle of a cloud
  cover the cloud. Where two named holders sit on top of each other, which is exactly
  what a co-moving pair does, the lower one puts its label underneath.

### The assistant can read the scan, and how it talks about it

`digest()` carries the archetype table, every finding with its evidence, the graph
summary and the concentration figures, so "what did the register scan find?" is answered
from the scan rather than from the exchange's ownership table. The two were previously
both introduced to the model as "Register", which is exactly what made it answer a
question about one using the other; each section now states what it is and what it is not.

**The provenance rule is deliberate and split.** The panel being generated is already on
screen in the tab's own caption, so the model does not repeat it — not as an opening line,
a closing line, a parenthetical or a footnote under a table. Restating it in every answer
is noise, and it buries the finding under a disclaimer nobody asked for.

The exception is absolute: **if the user asks whether the data is real, where it came
from, whether a named holder exists, or challenges the findings, the model says plainly
and immediately that the register is generated for demonstration.** It may never assert
that a holder here is a real person or institution, and it may never deny that the panel
is generated. Not volunteering something already displayed is presentation. Denying it
when asked is a different thing entirely, and it is the answer that would actually lose
the room.

### The constraint worth knowing before asking for data

**Every detector needs a panel, not a snapshot.** Co-movement needs the full run of
monthly deltas; the pre-event test needs several months that precede a negative
disclosure; the creep test needs a run long enough for a trend to be a trend. The
comparison PDFs here hold June against July 2026 — **one delta**, on which every detector
returns nothing at all. Two snapshots support a difference; twenty-four support a finding. It is the same
argument the tick archive makes one timescale down.

## Verification

The daily tab pinned to 2026-08-13 was compared field by field with the source PDF.
**Every share and market figure reconciles exactly** — OHLC, previous close, change,
volume, value, 52-week high, share count, market cap `19,456,116,735`, price-to-book
`3.718`, 1-year change `3.56%`, cap ranks `7` and `2`, all four top-5 tables, all seven
sector index moves, the full shareholders-activity grid, and ownership
`95.33 / 0.28 / 0.78 / 3.61` with institutions at `29.383%` against `29.403%` the day
before.

Three figures do **not** reconcile, and the PDF looks like the side that is off — the QE
Index 52-week high/low, the "53 weeks low", and the index volume/value totals. Detail and
arithmetic in [API_REFERENCE.md](API_REFERENCE.md) §4. `priceToBook` for past periods is
an approximation for the reason given there.

`test_build.py` runs 152 checks with no network: the PDF's own figures, the period
aggregation rules, the Sunday-rolling week numbering (including the months that open on a
Saturday), and a structural check that the shareholders-activity table stays rectangular
when a nationality is missing a Buy or Sell leg. The register-scan checks — archetype
coverage and exclusivity, that every holder has a position a log axis can plot, that
positions really are the register's own figures, labelling rules, and that edge thinning
never splits a group — run whenever the synthetic panel exists and are skipped when it
does not.

## Faithful to the source, including its one awkward chart

**Ownership by nationality** keeps the source's logarithmic axis, so a 95% holding and a
0.28% holding share one frame. Bar heights are therefore not proportional, which the caption
says outright. (Bars on a log axis need an explicit floor — their implicit baseline is zero,
which is negative infinity on a log scale and renders as a full-width band.)

The source's **Institutions Shares** line chart is not reproduced: its axis spans
`29.383–29.405%`, turning a 0.02pp move into a cliff. The app shows the same number as a
tile with a `pp` delta instead. The printable HTML export still draws the zoomed line, for
when the output has to match the original page for page.

## Not covered

- The intraday line plot at the top of the PDF — a different source, out of scope as agreed.
- Financial statements: `https://www.qe.com.qa/qdisclosure/api/XBRL/…` is mapped in the
  reference but untested — `www.qe.com.qa` was unreachable from here.
- Real-time push (Lightstreamer, mapped in the reference). The 5-minute static files cover
  the same fields; wiring the push feed is the only way to get finer than 5-minute
  granularity.
- Nothing on news: `POST /wp/mw_app/mw.php` `f=News` returns ~200 market-wide items,
  which is what the ticker uses.

`test.sh` and `qe_data/` are the earlier cookie-based attempt, superseded by this.
