"""The register as a book of record — the analysis the client's own PDFs carry.

This is the reporting layer, kept apart from discover.py on purpose. discover.py
looks for behaviour nobody declared; everything here is arithmetic on a snapshot
that a shareholder-services team would recognise, and would check by hand:

  * the three cuts the PDFs publish — above 500K, companies & funds, the full
    list — each as a two-period comparison with a difference column,
  * a Total and a Total excluding related parties, which is the line the client's
    own file ends on,
  * the book split by the dimensions the register carries: local against
    international, passive against active, related parties, board seats,
  * who entered and who left, which two snapshots can answer and a single one
    cannot,
  * and month-over-month series for all of it.

Nothing here infers. A number on this page is a number in the register, or a
subtraction of two of them. Anything that needs a judgement is in the watchlist
at the bottom, where it is labelled as such and carries the rule that fired it.
"""
from __future__ import annotations

from .discover import THRESHOLD_PCT, bucket

MIN_LARGE = 500_000          # the "above 500K" cut the client's PDF publishes
TOP_N = 200                  # the long list, as asked
CONCENTRATION_MOVE = 1.0     # pp change in top-10 that is worth a line
STAKE_MOVE = 0.50            # pp change in a segment that is worth a line
CREEP_GAP = 1.5              # pp below the disclosure threshold that is close


# ----------------------------------------------------------------- snapshots

def snapshots(series: dict, names: dict, months: list[str]) -> dict[str, list[dict]]:
    """One list of holder rows per month, largest first."""
    out: dict[str, list[dict]] = {m: [] for m in months}
    for nin, runs in series.items():
        meta = names[nin]
        for month, shares in runs.items():
            out[month].append({
                "nin": nin, "name": meta["name"],
                "nationality": meta["nationality"], "bucket": meta["bucket"],
                "investor_type": meta["investor_type"], "cls": meta["cls"],
                "related": meta["related"], "board": meta["board"],
                "shares": shares,
            })
    for month in months:
        out[month].sort(key=lambda r: -r["shares"])
    return out


def with_pct(rows: list[dict], total_shares: int) -> list[dict]:
    return [dict(r, pct=100.0 * r["shares"] / total_shares) for r in rows]


# ---------------------------------------------------------------- the cuts

CUTS = {
    "Above 500K": lambda r: r["shares"] >= MIN_LARGE,
    "Companies & funds": lambda r: r["investor_type"] == "Institutions",
    "Individuals": lambda r: r["investor_type"] == "Individuals",
    "Related parties": lambda r: r["related"],
    "Board members": lambda r: r["board"],
    "Full list": lambda r: True,
}


def compare(prev: list[dict], curr: list[dict], total_shares: int,
            keep=None, limit: int | None = None) -> dict:
    """Two snapshots joined per holder, in the shape the client's PDF prints.

    A holder in only one of the two months is kept, not dropped: the PDF's own
    comparison has no way to show an arrival or a departure, and those are
    exactly the rows a reader would want flagged. They carry a status so the
    table can mark them rather than showing a change from nothing.
    """
    keep = keep or (lambda r: True)
    a = {r["nin"]: r for r in prev if keep(r)}
    b = {r["nin"]: r for r in curr if keep(r)}

    rows = []
    for nin in a.keys() | b.keys():
        was, now = a.get(nin), b.get(nin)
        meta = now or was
        s_was = was["shares"] if was else 0
        s_now = now["shares"] if now else 0
        rows.append({
            "nin": nin, "name": meta["name"], "nationality": meta["nationality"],
            "bucket": meta["bucket"], "investor_type": meta["investor_type"],
            "cls": meta["cls"], "related": meta["related"], "board": meta["board"],
            "shares_was": s_was, "shares_now": s_now,
            "pct_was": 100.0 * s_was / total_shares,
            "pct_now": 100.0 * s_now / total_shares,
            "delta_shares": s_now - s_was,
            "delta_pp": 100.0 * (s_now - s_was) / total_shares,
            "status": "entered" if not was else "left" if not now else "held",
        })
    rows.sort(key=lambda r: -r["shares_now"])
    shown = rows[:limit] if limit else rows

    def total(subset: list[dict]) -> dict:
        w = sum(r["shares_was"] for r in subset)
        n = sum(r["shares_now"] for r in subset)
        return {
            "holders": len(subset), "shares_was": w, "shares_now": n,
            "pct_was": 100.0 * w / total_shares, "pct_now": 100.0 * n / total_shares,
            "delta_shares": n - w, "delta_pp": 100.0 * (n - w) / total_shares,
        }

    return {
        "rows": shown,
        "all_rows": rows,
        "total": total(rows),
        # The line the client's own file ends on.
        "total_ex_related": total([r for r in rows if not r["related"]]),
        "truncated": bool(limit) and len(rows) > limit,
    }


# ------------------------------------------------------------- the segments

SEGMENTS = {
    "Nationality": lambda r: "Local (Qatari)" if r["bucket"] == "QTR" else "International",
    "Region": lambda r: {"QTR": "Qatar", "GCC": "GCC", "ARB": "Arab",
                         "FRN": "Foreign"}[r["bucket"]],
    "Class": lambda r: "Passive (P)" if r["cls"] == "P" else "Active (A)",
    "Investor type": lambda r: r["investor_type"],
    "Affiliation": lambda r: ("Related party" if r["related"]
                              else "Board member" if r["board"] else "Other"),
}


def segment(prev: list[dict], curr: list[dict], key, total_shares: int) -> list[dict]:
    """One row per segment value: holders, shares, share of the company, change."""
    def roll(rows):
        acc: dict[str, dict] = {}
        for r in rows:
            g = acc.setdefault(key(r), {"holders": 0, "shares": 0})
            g["holders"] += 1
            g["shares"] += r["shares"]
        return acc

    was, now = roll(prev), roll(curr)
    out = []
    for name in sorted(was.keys() | now.keys()):
        w = was.get(name, {"holders": 0, "shares": 0})
        n = now.get(name, {"holders": 0, "shares": 0})
        out.append({
            "segment": name,
            "holders": n["holders"], "holders_was": w["holders"],
            "holders_delta": n["holders"] - w["holders"],
            "shares": n["shares"], "shares_was": w["shares"],
            "pct": 100.0 * n["shares"] / total_shares,
            "pct_was": 100.0 * w["shares"] / total_shares,
            "delta_pp": 100.0 * (n["shares"] - w["shares"]) / total_shares,
        })
    return sorted(out, key=lambda r: -r["shares"])


def segment_series(snaps: dict, months: list[str], key, total_shares: int) -> list[dict]:
    """The same split, every month — what the month-over-month chart draws."""
    out = []
    for month in months:
        acc: dict[str, int] = {}
        for r in snaps[month]:
            acc[key(r)] = acc.get(key(r), 0) + r["shares"]
        for name, shares in acc.items():
            out.append({"month": month, "segment": name,
                        "pct": 100.0 * shares / total_shares})
    return out


# ------------------------------------------------------ arrivals and exits

def movements(cmp_result: dict) -> dict:
    """Entered, left, and the largest moves among holders present in both."""
    rows = cmp_result["all_rows"]
    entered = sorted([r for r in rows if r["status"] == "entered"],
                     key=lambda r: -r["shares_now"])
    left = sorted([r for r in rows if r["status"] == "left"],
                  key=lambda r: -r["shares_was"])
    held = [r for r in rows if r["status"] == "held"]
    return {
        "entered": entered, "left": left,
        "added": sorted([r for r in held if r["delta_shares"] > 0],
                        key=lambda r: -r["delta_shares"]),
        "trimmed": sorted([r for r in held if r["delta_shares"] < 0],
                          key=lambda r: r["delta_shares"]),
        "entered_shares": sum(r["shares_now"] for r in entered),
        "left_shares": sum(r["shares_was"] for r in left),
    }


def concentration(rows: list[dict], total_shares: int) -> dict:
    shares = sorted((r["shares"] for r in rows), reverse=True)
    held = sum(shares) or 1
    half, acc = 0, 0
    for size in shares:
        acc += size
        half += 1
        if acc >= held / 2:
            break
    return {
        "holders": len(rows),
        "top10": 100 * sum(shares[:10]) / total_shares,
        "top20": 100 * sum(shares[:20]) / total_shares,
        "top50": 100 * sum(shares[:50]) / total_shares,
        "hhi": sum((s / held * 100) ** 2 for s in shares),
        "half": half,
        "float_ex_related": 100 * sum(
            r["shares"] for r in rows if not r["related"]) / total_shares,
    }


# ------------------------------------------------------------- what to watch
# Everything above is arithmetic. This is the one place that applies judgement,
# so every item carries the rule that produced it and the number that tripped
# it — a reader who disagrees with the threshold can see exactly what to move,
# and nothing fires without a figure behind it.

def _fmt(n: float) -> str:
    for cut, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(n) >= cut:
            return f"{n / cut:,.1f}{suffix}"
    return f"{n:,.0f}"


def watchlist(cmp_all: dict, prev: list[dict], curr: list[dict],
              total_shares: int, months: tuple[str, str]) -> list[dict]:
    """Things a shareholder-services team would put in front of the board."""
    was_m, now_m = months
    rows = cmp_all["all_rows"]
    moves = movements(cmp_all)
    con_was = concentration(prev, total_shares)
    con_now = concentration(curr, total_shares)
    items: list[dict] = []

    def add(sev, title, detail, action, rule):
        items.append({"severity": sev, "title": title, "detail": detail,
                      "action": action, "rule": rule})

    # 1 — the only item with a regulatory consequence, so it leads.
    #
    # A holder that has sat above the threshold for years is a disclosed fact,
    # not something to watch: reporting it every month buries the one line that
    # matters under four that do not. What earns a place here is a change of
    # state — a crossing in either direction, an approach from below, or a
    # material move by someone already above.
    for r in sorted(rows, key=lambda r: -r["pct_now"]):
        if r["status"] == "left":
            continue
        was_over = r["pct_was"] >= THRESHOLD_PCT
        now_over = r["pct_now"] >= THRESHOLD_PCT
        gap = THRESHOLD_PCT - r["pct_now"]

        if now_over and not was_over:
            add("high", f'{r["name"]} crossed above {THRESHOLD_PCT:g}%',
                f'{r["pct_was"]:.2f}% → {r["pct_now"]:.2f}% '
                f'({_fmt(r["shares_now"])} shares) between {was_m} and {now_m}.',
                "A disclosure obligation may have been triggered this period. "
                "Confirm the filing and check the holder against the related-party "
                "and board registers before anything is reported externally.",
                f"holding crossing {THRESHOLD_PCT:g}% upward this period")
        elif was_over and not now_over:
            add("high", f'{r["name"]} fell back below {THRESHOLD_PCT:g}%',
                f'{r["pct_was"]:.2f}% → {r["pct_now"]:.2f}% '
                f'({r["delta_shares"]:+,} shares) between {was_m} and {now_m}.',
                "Confirm whether the reduction was disclosed, and where the stock "
                "went — a holding leaving the threshold has a counterparty.",
                f"holding crossing {THRESHOLD_PCT:g}% downward this period")
        elif now_over and abs(r["delta_pp"]) >= STAKE_MOVE:
            add("medium", f'{r["name"]} moved {r["delta_pp"]:+.2f}pp while above '
                          f'{THRESHOLD_PCT:g}%',
                f'{r["pct_was"]:.2f}% → {r["pct_now"]:.2f}%, already a disclosed '
                f'holder at {_fmt(r["shares_now"])} shares.',
                "Already-disclosed holders still have to report changes. Check the "
                "dealing against the closed-period calendar.",
                f"a holder above {THRESHOLD_PCT:g}% moving {STAKE_MOVE:g}pp or more")
        elif not now_over and 0 < gap <= CREEP_GAP:
            add("medium", f'{r["name"]} is approaching {THRESHOLD_PCT:g}%',
                f'Holds {r["pct_now"]:.2f}% ({_fmt(r["shares_now"])} shares), '
                f'{gap:.2f}pp below it, moved {r["delta_pp"]:+.2f}pp in {now_m}.',
                "Track monthly. At the current rate, model the crossing date and "
                "have the disclosure position agreed before it arrives.",
                f"holding within {CREEP_GAP:g}pp below the {THRESHOLD_PCT:g}% threshold")

    # 2 — related parties and directors, where any move is a disclosure question.
    for r in rows:
        if not (r["related"] or r["board"]) or abs(r["delta_pp"]) < 0.01:
            continue
        who = "Related party" if r["related"] else "Board member"
        sev = "high" if abs(r["delta_pp"]) >= STAKE_MOVE else "medium"
        add(sev, f'{who} {r["name"]} moved {r["delta_pp"]:+.2f}pp',
            f'{r["pct_was"]:.3f}% → {r["pct_now"]:.3f}% '
            f'({r["delta_shares"]:+,} shares) between {was_m} and {now_m}.',
            "Check this against declared dealings and the closed-period calendar "
            "before it is reported externally.",
            "any movement by a related party or board member")

    # 3 — a big holder leaving, or arriving.
    floor = sorted((r["shares"] for r in prev), reverse=True)[:50][-1] if prev else 0
    for r in moves["left"][:5]:
        if r["shares_was"] < floor:
            continue
        add("high", f'{r["name"]} left the register',
            f'Held {r["pct_was"]:.3f}% ({_fmt(r["shares_was"])} shares) in {was_m}, '
            f'absent in {now_m}.',
            "Establish whether the stock was sold on- or off-market. A top-50 exit "
            "with no matching market volume is a transfer, and has a counterparty.",
            "a top-50 holder no longer on the register")
    for r in moves["entered"][:5]:
        if r["shares_now"] < MIN_LARGE:
            continue
        add("medium", f'{r["name"]} is new on the register',
            f'Arrived at {r["pct_now"]:.3f}% ({_fmt(r["shares_now"])} shares) in {now_m}.',
            "Identify the holder and its class before the next investor-relations "
            "cycle; a new holder above 500K is worth a call.",
            f"a new holder above {_fmt(MIN_LARGE)} shares")

    # 4 — the shape of the book rather than any one holder.
    d10 = con_now["top10"] - con_was["top10"]
    if abs(d10) >= CONCENTRATION_MOVE:
        add("medium", f'Top-10 concentration moved {d10:+.2f}pp',
            f'{con_was["top10"]:.2f}% → {con_now["top10"]:.2f}% of the company. '
            f'{con_now["half"]} holders now reach half the register.',
            "If concentration is rising, review free-float headroom against index "
            "eligibility. If it is falling, check which large holder is distributing.",
            f"top-10 concentration moving {CONCENTRATION_MOVE:g}pp or more")

    for label, key in (("Nationality", SEGMENTS["Nationality"]),
                       ("Class", SEGMENTS["Class"])):
        for seg in segment(prev, curr, key, total_shares):
            if abs(seg["delta_pp"]) < STAKE_MOVE:
                continue
            add("medium", f'{seg["segment"]} moved {seg["delta_pp"]:+.2f}pp',
                f'{seg["pct_was"]:.2f}% → {seg["pct"]:.2f}% of the company, '
                f'{seg["holders_delta"]:+d} holders.',
                "Foreign and passive money move for different reasons — index "
                "reviews and mandate changes rather than the company. Check the "
                "index calendar before reading it as sentiment."
                if label == "Nationality" else
                "A shift toward active holders raises turnover and the odds of a "
                "stake being built. Re-run the scan before the next board pack.",
                f"{label.lower()} split moving {STAKE_MOVE:g}pp or more")

    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(items, key=lambda i: order[i["severity"]])


def what_moved(cmp_all: dict, months: tuple[str, str], total_shares: int,
               top: int = 5) -> dict:
    """The month in numbers: who added, who trimmed, who arrived, who left."""
    was_m, now_m = months
    moves = movements(cmp_all)
    return {
        "from": was_m, "to": now_m,
        "added": moves["added"][:top],
        "trimmed": moves["trimmed"][:top],
        "entered": moves["entered"][:top],
        "left": moves["left"][:top],
        "entered_count": len(moves["entered"]),
        "left_count": len(moves["left"]),
        "entered_pct": 100.0 * moves["entered_shares"] / total_shares,
        "left_pct": 100.0 * moves["left_shares"] / total_shares,
        "net_pct": 100.0 * (moves["entered_shares"] - moves["left_shares"]) / total_shares,
    }


def executive(prev: list[dict], curr: list[dict], cmp_all: dict,
              total_shares: int, months: tuple[str, str]) -> list[dict]:
    """Six figures and what each one did. The page someone reads standing up."""
    was_m, now_m = months
    con_was = concentration(prev, total_shares)
    con_now = concentration(curr, total_shares)
    moves = movements(cmp_all)
    nat = {s["segment"]: s for s in segment(prev, curr, SEGMENTS["Nationality"],
                                            total_shares)}
    cls = {s["segment"]: s for s in segment(prev, curr, SEGMENTS["Class"],
                                            total_shares)}
    intl = nat.get("International", {"pct": 0.0, "delta_pp": 0.0})
    active = cls.get("Active (A)", {"pct": 0.0, "delta_pp": 0.0})
    return [
        {"label": "Holders on the register", "value": f'{con_now["holders"]:,}',
         "delta": f'{con_now["holders"] - con_was["holders"]:+d} vs {was_m}',
         "note": f'{len(moves["entered"])} in, {len(moves["left"])} out'},
        {"label": "Top-10 concentration", "value": f'{con_now["top10"]:.2f}%',
         "delta": f'{con_now["top10"] - con_was["top10"]:+.2f}pp',
         "note": f'{con_now["half"]} holders reach half the book'},
        {"label": "Free float ex-related", "value": f'{con_now["float_ex_related"]:.2f}%',
         "delta": f'{con_now["float_ex_related"] - con_was["float_ex_related"]:+.2f}pp',
         "note": "excludes UCC, Infra Road, H'Collective"},
        {"label": "International", "value": f'{intl["pct"]:.2f}%',
         "delta": f'{intl.get("delta_pp", 0):+.2f}pp',
         "note": f'{intl.get("holders", 0):,} holders'},
        {"label": "Active (A) class", "value": f'{active["pct"]:.2f}%',
         "delta": f'{active.get("delta_pp", 0):+.2f}pp',
         "note": f'{active.get("holders", 0):,} holders'},
        {"label": "Net arrivals", "value": f'{moves["entered_shares"] - moves["left_shares"]:+,}',
         "delta": f'{100.0 * (moves["entered_shares"] - moves["left_shares"]) / total_shares:+.3f}pp',
         "note": f'{_fmt(moves["entered_shares"])} in, {_fmt(moves["left_shares"])} out'},
    ]


# ------------------------------------------------------------------- KPIs
# A CFO reads one number against three others: last month, last quarter, last
# year. A single month-on-month delta cannot separate a trend from a wobble, and
# on a register — where one holder dealing moves a whole line — most single
# months are wobble. Every KPI below therefore carries all three lookbacks.

LOOKBACKS = [(1, "1M"), (3, "3M"), (12, "12M")]


def metrics(rows: list[dict], total_shares: int) -> dict:
    """Every scalar the dashboard reports, for one month of the register."""
    con = concentration(rows, total_shares)
    held = sum(r["shares"] for r in rows)
    ranked = sorted((r["shares"] for r in rows), reverse=True)

    def pct(test) -> float:
        return 100.0 * sum(r["shares"] for r in rows if test(r)) / total_shares

    def count(test) -> int:
        return sum(1 for r in rows if test(r))

    return {
        "holders": len(rows),
        "shares": held,
        "pct_registered": 100.0 * held / total_shares,
        "top10": con["top10"], "top20": con["top20"], "top50": con["top50"],
        "top200": 100.0 * sum(ranked[:TOP_N]) / total_shares,
        "hhi": con["hhi"], "half": con["half"],
        "float_ex_related": con["float_ex_related"],
        "local": pct(lambda r: r["bucket"] == "QTR"),
        "international": pct(lambda r: r["bucket"] != "QTR"),
        "gcc": pct(lambda r: r["bucket"] == "GCC"),
        "arab": pct(lambda r: r["bucket"] == "ARB"),
        "foreign": pct(lambda r: r["bucket"] == "FRN"),
        "passive": pct(lambda r: r["cls"] == "P"),
        "active": pct(lambda r: r["cls"] == "A"),
        "institutions": pct(lambda r: r["investor_type"] == "Institutions"),
        "individuals": pct(lambda r: r["investor_type"] == "Individuals"),
        "related": pct(lambda r: r["related"]),
        "board": pct(lambda r: r["board"]),
        "above_500k": pct(lambda r: r["shares"] >= MIN_LARGE),
        "n_above_500k": count(lambda r: r["shares"] >= MIN_LARGE),
        "n_international": count(lambda r: r["bucket"] != "QTR"),
        "n_active": count(lambda r: r["cls"] == "A"),
        "n_institutions": count(lambda r: r["investor_type"] == "Institutions"),
        "n_related": count(lambda r: r["related"]),
        "n_board": count(lambda r: r["board"]),
    }


# label, key, unit, and whether a rise is the direction to worry about
KPI_ROWS = [
    ("Holders on the register", "holders", "n", False),
    ("Held by named holders", "pct_registered", "%", False),
    ("Top-10 concentration", "top10", "%", True),
    ("Top-20 concentration", "top20", "%", True),
    ("Top-200 concentration", "top200", "%", True),
    # More holders needed to reach half the book means the book is LESS
    # concentrated, so the direction to worry about is a fall, not a rise.
    ("Holders to reach half the book", "half", "n", False),
    ("HHI", "hhi", "n", True),
    ("Free float ex-related parties", "float_ex_related", "%", False),
    ("Local (Qatari)", "local", "%", False),
    ("International", "international", "%", False),
    ("Passive (P)", "passive", "%", False),
    ("Active (A)", "active", "%", True),
    ("Institutions", "institutions", "%", False),
    ("Individuals", "individuals", "%", False),
    ("Related parties", "related", "%", True),
    ("Board members", "board", "%", False),
    ("Holdings above 500K", "above_500k", "%", False),
    ("Holders above 500K", "n_above_500k", "n", False),
]


def kpis(snaps: dict, months: list[str], month: str, total_shares: int) -> list[dict]:
    """Every KPI against 1, 3 and 12 months back, where the panel reaches."""
    i = months.index(month)
    now = metrics(snaps[month], total_shares)
    back = {}
    for span, label in LOOKBACKS:
        if i - span >= 0:
            back[label] = (metrics(snaps[months[i - span]], total_shares),
                           months[i - span])

    out = []
    for label, key, unit, rising_is_risk in KPI_ROWS:
        row = {"label": label, "key": key, "unit": unit,
               "value": now[key], "risk_on_rise": rising_is_risk}
        for _, span in LOOKBACKS:
            if span in back:
                was, when = back[span]
                row[span] = now[key] - was[key]
                row[f"{span}_from"] = when
            else:
                row[span] = None
                row[f"{span}_from"] = None
        out.append(row)
    return out


def trend(snaps: dict, months: list[str], total_shares: int) -> list[dict]:
    """The whole panel, one row per month — the month-over-month table."""
    out = []
    for i, month in enumerate(months):
        m = metrics(snaps[month], total_shares)
        row = {"month": month, **m, "entered": 0, "left": 0,
               "dealt": 0, "entered_pct": 0.0, "left_pct": 0.0}
        if i:
            prior = {r["nin"]: r["shares"] for r in snaps[months[i - 1]]}
            here = {r["nin"]: r["shares"] for r in snaps[month]}
            gone = prior.keys() - here.keys()
            new = here.keys() - prior.keys()
            row["entered"] = len(new)
            row["left"] = len(gone)
            row["dealt"] = sum(1 for k in prior.keys() & here.keys()
                               if prior[k] != here[k])
            row["entered_pct"] = 100.0 * sum(here[k] for k in new) / total_shares
            row["left_pct"] = 100.0 * sum(prior[k] for k in gone) / total_shares
        out.append(row)
    return out


# ------------------------------------------------- reporting the scan
# discover.py says what it found. It does not say what anyone should do about
# it, and deliberately so — the detectors have to stay free of any view about
# consequence or they stop being detectors. The mapping from a finding to a
# severity and an action is a business judgement, so it lives here, in the open,
# one entry per finding type rather than buried in a UI string.

FINDING_ACTIONS = {
    "Steady creep": (
        "high",
        "Model the crossing date at the current rate and agree the disclosure "
        "position before it arrives. Check whether the holder is acting with "
        "anyone else — a stake built just under the threshold by two holders is "
        "still one stake.",
    ),
    "Pre-event exit": (
        "high",
        "Establish what this holder could have known and when. Cross-check the "
        "dealing dates against the disclosure calendar and the insider list, and "
        "route it to compliance rather than investor relations.",
    ),
    "Mirrored flow": (
        "medium",
        "Confirm whether the transfer was on- or off-market. An off-market "
        "transfer between two holders has a counterparty, a price and a reason, "
        "and none of them appear in exchange volume.",
    ),
    "Co-movement": (
        "medium",
        "Identify the beneficial owner behind both holdings. Holders moving in "
        "lockstep may share a manager, a mandate or an owner — the last of those "
        "is a concert-party question and aggregates for disclosure.",
    ),
    "Price response": (
        "low",
        "No action beyond knowing who they are. A holder that reliably buys "
        "weakness is a stabiliser worth calling when the stock is under pressure; "
        "one that chases strength adds to volatility rather than damping it.",
    ),
}


def scan_watchlist(findings: list[dict]) -> list[dict]:
    """Findings, ranked by consequence, each with what to do about it."""
    order = {"high": 0, "medium": 1, "low": 2}
    items = []
    for f in findings:
        severity, action = FINDING_ACTIONS.get(f["kind"], ("low", "Note and monitor."))
        items.append({
            "severity": severity, "kind": f["kind"], "title": f["subject"],
            "detail": f'{f["evidence"]} — {f["reading"]}',
            "action": action, "holders": f["holders"],
        })
    return sorted(items, key=lambda i: order[i["severity"]])


def scan_executive(scan: dict, total_shares: int) -> list[dict]:
    """Six figures describing what the scan looked at and what it found."""
    findings = scan["findings"]
    flagged = {k for f in findings for k in f["holders"]}
    months = scan["months"]
    held = sum(scan["series"][k][months[-1]] for k in flagged
               if months[-1] in scan["series"][k])
    watch = scan_watchlist(findings)
    high = sum(1 for w in watch if w["severity"] == "high")
    linked = sum(len(c) for c in scan["graph"]["clusters"])
    return [
        {"label": "Holders scanned", "value": f'{scan["scanned"]:,}',
         "delta": f'{scan["excluded"]:,} not scanned',
         "note": "A holder must be on the register every month to be compared "
                 "against another; arrivals and departures are reported on the "
                 "Register tab instead."},
        {"label": "Findings", "value": f"{len(findings)}",
         "delta": f"{high} high severity",
         "note": "Each finding is one behaviour above its own threshold."},
        {"label": "Holders flagged", "value": f"{len(flagged)}",
         "delta": f'{100 * len(flagged) / max(scan["scanned"], 1):.1f}% of those scanned',
         "note": "Named in at least one finding."},
        {"label": "Float under a finding", "value": f"{100 * held / total_shares:.2f}%",
         "delta": f"{brief(held)} shares",
         "note": "Combined holding of every flagged holder."},
        {"label": "Holders moving in pairs", "value": f"{linked}",
         "delta": f'{len(scan["graph"]["clusters"])} group(s)',
         "note": "Holders whose monthly changes track another holder's."},
        {"label": "Most concentrated holder", "value":
            f'{max((100 * scan["series"][k][months[-1]] / total_shares) for k in flagged) if flagged else 0:.2f}%'
            if flagged else "—",
         "delta": f'threshold {THRESHOLD_PCT:g}%',
         "note": "Largest single holding among the flagged holders."},
    ]


def brief(value: float) -> str:
    return _fmt(value)


def scan_month(scan: dict, month: str, total_shares: int) -> dict:
    """What the flagged holders did in one month, and who moved most."""
    months = scan["months"]
    i = months.index(month)
    prior = months[i - 1] if i else None
    flagged = {k for f in scan["findings"] for k in f["holders"]}
    kinds: dict[int, list[str]] = {}
    for f in scan["findings"]:
        for k in f["holders"]:
            kinds.setdefault(k, []).append(f["kind"])

    rows = []
    for k in flagged:
        runs = scan["series"][k]
        if month not in runs:
            continue
        was = runs.get(prior) if prior else None
        now = runs[month]
        rows.append({
            "nin": k, "name": scan["names"][k]["name"],
            "kinds": ", ".join(sorted(set(kinds[k]))),
            "shares_was": was or 0, "shares_now": now,
            "delta_shares": (now - was) if was else 0,
            "delta_pct": (100.0 * (now - was) / was) if was else 0.0,
            "pct": 100.0 * now / total_shares,
        })
    rows.sort(key=lambda r: -abs(r["delta_shares"]))
    return {"month": month, "prior": prior, "rows": rows,
            "moved": sum(1 for r in rows if r["delta_shares"])}
