"""Find structure in a shareholder register panel. Unsupervised.

Reads out/synth/register_*.csv + market.json. Never reads _ground_truth.json.
Five detectors, each reporting only what clears its threshold:

  1 co-movement      pairs whose month-on-month deltas move together
  2 mirroring        pairs that move opposite and near-equal (internal transfer)
  3 pre-event exit   holders reducing the month BEFORE negative disclosures
  4 price response   holders trading against / with the price
  5 steady creep     monotonic accumulation, incl. distance to the 5% threshold

Everything here works identically on a real register — only load() changes.
"""
from __future__ import annotations

import csv
import json
import math
import statistics as st
from itertools import combinations
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "out" / "synth"

THRESHOLD_PCT = 5.0          # disclosure threshold a creeping holder approaches
CO_R = 0.85                  # co-movement correlation floor
MIRROR_OFFSET = 0.03         # mean |a+b| below which a pair is a transfer, not a trade
ACTIVE_SD = 0.02             # idiosyncratic sd a holder needs to be worth pairing


# The register stores a country, the exchange reports four buckets. Anything not
# recognised is treated as foreign, which is the safe direction: it can understate
# the Qatari share but never overstate it.
GULF = {"UAE", "KSA", "SAU", "KWT", "BHR", "OMN"}
ARAB = {"IRQ", "SYR", "PLS", "JOR", "EGY", "LBN", "YEM", "SDN"}
QATAR = {"QTR", "QAT", "QATAR"}


def bucket(code: str) -> str:
    """QTR / GCC / ARB / FRN from whatever spelling the register used."""
    c = (code or "").strip().upper()
    if c in QATAR:
        return "QTR"
    if c in GULF:
        return "GCC"
    if c in ARAB:
        return "ARB"
    return "FRN"


def load(out: Path = OUT):
    """The panel: market context, month labels, shares per holder, holder identity.

    Holders enter and leave, so `series` is ragged — a holder has an entry only
    for the months it was on the register. Callers that need a rectangle ask
    balanced() for one; everything describing the book as it stands uses this.
    """
    market = json.load(open(out / "market.json"))
    months = market["months"]
    series, names = {}, {}
    for label in months:
        for row in csv.DictReader(open(out / f"register_{label}.csv")):
            nin = int(row["nin"])
            series.setdefault(nin, {})[label] = int(row["shares"])
            names[nin] = {
                "name": row["name"],
                "nationality": row["nationality"],
                "bucket": bucket(row["nationality"]),
                "investor_type": row["investor_type"],
                "cohort": f'{bucket(row["nationality"])}/{row["investor_type"]}',
                "cls": row.get("cls", "P"),
                "related": row["related_party"] == "True",
                "board": row.get("board_member") == "True",
            }
    return market, months, series, names


def balanced(series: dict, months: list[str]) -> list[int]:
    """Holders on the register for every month, sorted.

    Every detector below compares one holder's run of monthly changes against
    another's, or against the price. A holder that arrives in month 14 has no
    change to compare for the first thirteen, and filling those with zeros would
    invent thirteen months of "did nothing" — which reads as co-movement with
    every other holder that also did nothing. Excluding them costs recall on the
    newcomers and is the only honest option; the dashboard reports them in full,
    and reports how many the scan therefore could not look at.
    """
    return sorted(k for k, s in series.items() if len(s) == len(months))


def deltas(series: dict, months: list[str]):
    """Month-on-month change, with the cross-sectional median removed.

    A register is zero-sum in percentage terms: if the large retail cohort adds
    6%, every other holder's share falls even when their holding never moved.
    That common factor manufactures r>0.99 between any two passive holders and
    an equally fake r<-0.85 between passive and active ones. Subtracting the
    median holder's move each month leaves only idiosyncratic behaviour, which
    is the only kind worth flagging. `raw` is kept for reference.
    """
    raw = {
        nin: [(s[months[i]] - s[months[i - 1]]) / s[months[i - 1]]
              for i in range(1, len(months))]
        for nin, s in series.items()
    }
    n = len(months) - 1
    common = [st.median([raw[k][i] for k in raw]) for i in range(n)]
    net = {k: [v[i] - common[i] for i in range(n)] for k, v in raw.items()}
    return net, raw, common


def corr(a: list[float], b: list[float]) -> float:
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return 0.0
    return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / (va ** 0.5 * vb ** 0.5)


def concentration(rows: list[dict], total: int) -> dict:
    shares = sorted((r["shares"] for r in rows), reverse=True)
    held = sum(shares)
    half, acc = 0, 0
    for size in shares:                        # holders needed to reach half the book
        acc += size
        half += 1
        if acc >= held / 2:
            break
    return {
        "top10": 100 * sum(shares[:10]) / held,
        "top3": 100 * sum(shares[:3]) / held,
        "related": 100 * sum(r["shares"] for r in rows if r["related"]) / held,
        "hhi": sum((s / held * 100) ** 2 for s in shares),
        "half": half,
    }


# --------------------------------------------------------------- archetypes
# The five detectors above flag the exceptional holder. They say nothing about
# the other ninety, which is most of the register and most of what an IR team
# actually wants described. Every holder therefore also gets exactly one
# archetype, derived from statistics the detectors already compute: the
# idiosyncratic volatility of its de-meaned deltas, its correlation to the
# monthly return, how monotonic it is, and how much of the position survived
# the panel.

ARCHETYPES = {
    "Quiet accumulator": "Monotonic buying at low variance — a position being built, not traded.",
    "Coordinated":       "Moves with, or against, a specific other holder — the linked nodes opposite.",
    "Momentum chaser":   "Adds into rising prices and cuts into falling ones.",
    "Contrarian buyer":  "Buys weakness — supplies liquidity when the price falls.",
    "Exiting":           "Materially smaller than at the start of the panel.",
    "Active trader":     "Turnover well above this book's own norm, with no stable signature.",
    "Stable core":       "No persistent signature — ordinary drift, nothing the scan can read.",
}

DRIFT_EXIT = -0.25           # shrinkage across the panel that counts as leaving
PRICE_R = 0.6                # correlation to monthly return that counts as a response
ACTIVE_MULT = 1.4            # multiple of the book's own median volatility = "active"
DEGREE_CAP = 3               # strongest links drawn per holder — see strongest()
NAMED_GROUP = 6              # cluster size at or below which both holders are named


def classify(deltas: list[float], ret: list[float], first: int, last: int,
             linked: bool, norm: float) -> str:
    """One archetype per holder.

    Precedence is deliberate rather than alphabetical: a signature that says
    *why* a holder moves outranks one that only says how much. Accumulation is
    tested first because it is the only pattern with a regulatory consequence,
    and "Stable core" is last because it is the residual — what is left when a
    holder has no signature at all, which for a healthy register is most of it.

    `norm` is the median holder's idiosyncratic volatility, and "active" means a
    multiple of it rather than a fixed number. A fixed threshold does not
    survive contact with a second register: a thinly traded book and a liquid
    one differ by an order of magnitude in monthly variance, and a constant
    tuned on one classifies the whole of the other. Calibrating on the book's
    own median makes "moves more than this company's holders normally move" mean
    the same thing everywhere — which is the claim the label actually makes.
    """
    sd = st.pstdev(deltas)
    ups = sum(1 for x in deltas if x > 0) / len(deltas)
    drift = last / first - 1
    r = corr(deltas, ret)
    if ups > 0.85 and sd < 0.02 and drift > 0:
        return "Quiet accumulator"
    if linked:
        return "Coordinated"
    if r > PRICE_R:
        return "Momentum chaser"
    if r < -PRICE_R:
        return "Contrarian buyer"
    if drift <= DRIFT_EXIT:
        return "Exiting"
    if sd > ACTIVE_MULT * norm:
        return "Active trader"
    return "Stable core"


# ------------------------------------------------------------------- graph
# Co-movement and mirroring are already a graph — printing the three strongest
# pairs as text throws away the shape. What follows prepares the same edges for
# drawing, but the holders are NOT given invented coordinates.
#
# An earlier version placed them on concentric rings: groups spaced evenly on an
# inner circle, unlinked holders spread around a rim. It was tidy, deterministic
# and completely wrong. Positions carried no information, so the eye searched
# them for meaning and found none — and the geometric regularity of it, exact
# circles with dots at exact equal angles, is not a thing any real book produces.
# A drawing of real data that looks manufactured discredits the data.
#
# So position now comes from the register itself: how much a holding changed
# across the panel, against how much it moves in a typical month. The cloud that
# falls out is irregular because the numbers are, every position reads as a
# sentence, and the lines between linked holders become evidence rather than
# decoration — co-moving holders land next to each other, and the two sides of a
# transfer land on opposite sides of the plot with the line drawn between them.


def components(nodes: list[int], edges: list[dict]) -> list[list[int]]:
    """Connected holders, largest group first. Plain flood fill."""
    adj: dict[int, set] = {n: set() for n in nodes}
    for e in edges:
        adj[e["a"]].add(e["b"])
        adj[e["b"]].add(e["a"])
    seen, out = set(), []
    for n in nodes:
        if n in seen:
            continue
        stack, group = [n], []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            group.append(x)
            stack.extend(adj[x] - seen)
        out.append(sorted(group))
    return sorted(out, key=len, reverse=True)


def strongest(edges: list[dict], cap: int = DEGREE_CAP) -> list[dict]:
    """Thin dense neighbourhoods to each holder's strongest `cap` links.

    Any group whose members share a common driver correlates pairwise across the
    whole group, so an n-holder group can produce up to n(n-1)/2 edges. Drawing
    all of them fills the group with ink that carries no information — every line
    repeats what the group already says by being a group. Capping per node keeps
    each holder's best evidence, keeps the group visibly connected, and leaves
    isolated pairs legible instead of drowned. Nothing is dropped from the
    analysis; this affects what is drawn, not what was found.
    """
    rank: dict[int, list] = {}
    for e in edges:
        for k in (e["a"], e["b"]):
            rank.setdefault(k, []).append(e)
    keep = set()
    for k, group in rank.items():
        for e in sorted(group, key=lambda x: -abs(x["r"]))[:cap]:
            keep.add((e["a"], e["b"], e["kind"]))
    return [e for e in edges if (e["a"], e["b"], e["kind"]) in keep]


def analyse(out: Path = OUT) -> dict:
    """Every finding, plus the panel they were derived from. No printing."""
    market, months, series, names = load(out)
    keys = balanced(series, months)
    panel = {k: series[k] for k in keys}
    net, raw, common = deltas(panel, months)
    dm = months[1:]                                    # months a delta exists for
    total = market["total_shares"]

    negative = {e["month"] for e in market["events"] if e["sentiment"] == "Negative"}
    close = market["close"]
    ret = [(close[i] - close[i - 1]) / close[i - 1] for i in range(1, len(close))][:len(dm)]

    findings: list[dict] = []

    def add(kind, subject, evidence, reading, holders=()):
        findings.append({"kind": kind, "subject": subject, "evidence": evidence,
                         "reading": reading, "holders": list(holders)})

    # ---- 1 + 2 — pairwise co-movement and mirroring --------------------------
    # Near-static holders (related parties, dormant estates) carry almost no
    # idiosyncratic variance, so after de-meaning they all read as -common and
    # correlate with each other at r>0.9. That is the common factor again, not a
    # relationship. Require real movement on both sides of a pair.
    active = sorted(k for k in keys if st.pstdev(net[k]) > ACTIVE_SD)
    together, mirrored = [], []
    for a, b in combinations(active, 2):
        r = corr(net[a], net[b])
        if r > CO_R:
            together.append((r, a, b))
        elif r < -CO_R:
            offset = st.mean(abs(net[a][i] + net[b][i]) for i in range(len(dm)))
            if offset < MIRROR_OFFSET:
                mirrored.append((r, a, b, offset))

    for r, a, b in sorted(together, reverse=True)[:3]:
        add("Co-movement", f'{names[a]["name"]} + {names[b]["name"]}',
            f'r={r:+.3f} across {len(dm)} months, both {names[a]["cohort"]}',
            "Deltas track each other far above the cohort norm — possible common "
            "beneficial owner, mandate or manager.", [a, b])

    for r, a, b, offset in sorted(mirrored, key=lambda x: x[3])[:3]:
        add("Mirrored flow", f'{names[a]["name"]} → {names[b]["name"]}',
            f"r={r:+.3f}, mean net offset {offset * 100:.2f}%",
            "One reduces almost exactly what the other adds — an off-market "
            "transfer rather than open-market trading.", [a, b])

    # ---- 3 — reduction in the month BEFORE a negative disclosure -------------
    pre = {dm[i] for i in range(len(dm) - 1) if dm[i + 1] in negative}
    if pre:
        for k in keys:
            inside = [net[k][i] for i, m in enumerate(dm) if m in pre]
            outside = [net[k][i] for i, m in enumerate(dm) if m not in pre]
            if len(inside) < 3:
                continue
            if st.mean(inside) - st.mean(outside) < -0.15 and max(inside) < 0:
                add("Pre-event exit", names[k]["name"],
                    f"mean {st.mean(inside) * 100:+.1f}% in the {len(inside)} months before "
                    f"a negative disclosure vs {st.mean(outside) * 100:+.1f}% otherwise",
                    "Position cut ahead of every bad disclosure and never after — "
                    "consistent with information reaching this holder early.", [k])

    # ---- 4 — response to price ----------------------------------------------
    for k in keys:
        r = corr(net[k], ret)
        if abs(r) > 0.6:
            add("Price response", names[k]["name"], f"r={r:+.3f} vs monthly return",
                "Buys into falling prices." if r < 0 else "Chases rising prices.", [k])

    # ---- 5 — steady accumulation toward the disclosure threshold -------------
    for k in keys:
        ups = sum(1 for x in net[k] if x > 0)
        if ups / len(net[k]) > 0.85 and st.pstdev(net[k]) < 0.02:
            first, last = series[k][months[0]], series[k][months[-1]]
            now = 100 * last / total
            gap = THRESHOLD_PCT - now
            add("Steady creep", names[k]["name"],
                f"up in {ups}/{len(net[k])} months, sd {st.pstdev(net[k]) * 100:.1f}%; "
                f"{first / total * 100:.2f}% → {now:.2f}%",
                f"Metronomic accumulation, "
                f"{'above' if gap <= 0 else f'{gap:.2f}pp below'} the "
                f"{THRESHOLD_PCT:g}% disclosure threshold — size is being managed, "
                "not discovered.", [k])

    # ---- every holder classified, not only the flagged ones -----------------
    edges = (
        [{"a": a, "b": b, "r": r, "kind": "Co-movement"} for r, a, b in together]
        + [{"a": a, "b": b, "r": r, "kind": "Mirrored flow"} for r, a, b, _ in mirrored]
    )
    linked = {k for e in edges for k in (e["a"], e["b"])}

    held_now = sum(series[k][months[-1]] for k in keys)
    norm = st.median(st.pstdev(net[k]) for k in keys)
    kind_of = {
        k: classify(net[k], ret, series[k][months[0]], series[k][months[-1]],
                    k in linked, norm)
        for k in keys
    }
    archetypes = []
    for label, blurb in ARCHETYPES.items():
        members = [k for k in keys if kind_of[k] == label]
        if not members:
            continue
        archetypes.append({
            "label": label,
            "blurb": blurb,
            "count": len(members),
            "pct": 100 * sum(series[k][months[-1]] for k in members) / held_now,
            "drift": 100 * st.mean(
                series[k][months[-1]] / series[k][months[0]] - 1 for k in members),
            "holders": members,
        })

    # ---- the same pairs, laid out as a graph --------------------------------
    # x: holding now against holding at the start of the panel (1.0 = unchanged).
    # y: the size of a typical month-to-month move, once the common factor is out.
    pos = {
        k: (series[k][months[-1]] / series[k][months[0]] if series[k][months[0]] else 1.0,
            st.pstdev(net[k]) * 100)
        for k in keys
    }
    groups = components(keys, edges)
    clustered = [g for g in groups if len(g) > 1]
    singles = [g[0] for g in groups if len(g) == 1]
    drawn = strongest(edges)

    # Name exactly the holders the findings list names, and nobody else.
    #
    # An earlier rule named anything statistically unusual — fifteen holders on a
    # 250-name book — which produced a chart a reader had to decode before it
    # said anything, and a set of names that did not match the list beside it.
    # Tying the two together means every label on the chart can be looked up in
    # the panel next to it, and the rest of the register is context rather than a
    # quiz. A holder that is odd but not worth reporting is not worth naming.
    notable = {k for f in findings for k in f["holders"]}

    # Two named holders sitting on top of each other print two labels on top of
    # each other, and the pair that co-moves is by definition the case where that
    # happens. Anything with a label already close above it puts its own below.
    nudge, placed = {}, []
    for k in sorted(notable, key=lambda k: (-pos[k][1], pos[k][0])):
        x, y = pos[k]
        crowded = any(abs(math.log10(x / px)) < 0.16 and abs(y - py) < 1.6
                      for px, py in placed)
        nudge[k] = 18 if crowded else -14
        placed.append((x, y))
    drawn = strongest(edges)
    small = {k for g in clustered if len(g) <= NAMED_GROUP for k in g}

    graph = {
        "nodes": [
            {
                "nin": k,
                "name": names[k]["name"],
                "cohort": names[k]["cohort"],
                "archetype": kind_of[k],
                "related": names[k]["related"],
                "pct": 100 * series[k][months[-1]] / total,
                "x": pos[k][0], "y": pos[k][1],
                "linked": k in linked,
                "tag": names[k]["name"] if k in notable else "",
                "dy": nudge.get(k, -14),
            }
            for k in keys
        ],
        "edges": [
            {
                "kind": e["kind"], "r": e["r"],
                # Carry the holder ids. Positions are register figures now, and
                # two holders that never dealt share one exactly — (1.0, 0.0) —
                # so a coordinate is no longer an identity.
                "a": e["a"], "b": e["b"],
                "pair": f'{names[e["a"]]["name"]} · {names[e["b"]]["name"]}',
                "x": pos[e["a"]][0], "y": pos[e["a"]][1],
                "x2": pos[e["b"]][0], "y2": pos[e["b"]][1],
            }
            for e in drawn
        ],
        "clusters": clustered,
        "singles": singles,
        "edges_found": len(edges),
    }

    # ---- panel context -------------------------------------------------------
    snapshots = {}
    for label in months:
        snapshots[label] = [
            {"nin": int(r["nin"]), "name": r["name"], "nationality": r["nationality"],
             "investor_type": r["investor_type"], "related": r["related_party"] == "True",
             "shares": int(r["shares"]), "pct": float(r["pct"])}
            for r in csv.DictReader(open(out / f"register_{label}.csv"))
        ]

    return {
        "findings": findings,
        "scanned": len(keys),
        "excluded": len(series) - len(keys),
        "archetypes": archetypes,
        "norm": norm,
        "graph": graph,
        "months": months,
        "series": series,
        "names": names,
        "net": net,
        "common": common,
        "market": market,
        "snapshots": snapshots,
        "first": concentration(snapshots[months[0]], total),
        "last": concentration(snapshots[months[-1]], total),
    }


def main():
    r = analyse()
    months, first, last = r["months"], r["first"], r["last"]
    print("=" * 78)
    print(f'REGISTER STRUCTURE REPORT   {months[0]} .. {months[-1]}   '
          f'{len(r["names"])} holders, {len(months)} snapshots')
    print("=" * 78)
    print(f'\nConcentration   top-10 {first["top10"]:.1f}% → {last["top10"]:.1f}%   '
          f'HHI {first["hhi"]:.0f} → {last["hhi"]:.0f}   '
          f'related parties {first["related"]:.1f}% → {last["related"]:.1f}%')
    print(f'Free float ex-related-parties  {100 - first["related"]:.1f}% → '
          f'{100 - last["related"]:.1f}%')
    print(f'Common factor removed  median holder move '
          f'{st.mean(r["common"]) * 100:+.2f}%/mo '
          f'(sd {st.pstdev(r["common"]) * 100:.2f}%)\n')
    print(f'Archetypes   (median holder volatility {r["norm"] * 100:.2f}%/mo; '
          f'"active" is {ACTIVE_MULT:g}x that)')
    for a in r["archetypes"]:
        print(f'  {a["label"]:<19} {a["count"]:>3} holders  {a["pct"]:>5.1f}% of float  '
              f'{a["drift"]:+6.1f}% avg move')
    g = r["graph"]
    print(f'\nGraph  {len(g["nodes"])} holders, {g["edges_found"]} edges '
          f'({len(g["edges"])} drawn), {len(g["clusters"])} connected group(s), '
          f'{len(g["singles"])} unconnected\n')
    for i, f in enumerate(r["findings"], 1):
        print(f'[{i:02d}] {f["kind"]:<17} {f["subject"]}')
        print(f'     evidence : {f["evidence"]}')
        print(f'     reading  : {f["reading"]}\n')
    print(f'{len(r["findings"])} findings, none of them told to the detector in advance.')
    return r["findings"]


if __name__ == "__main__":
    main()
