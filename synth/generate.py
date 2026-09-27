"""Synthetic Estithmar shareholder register — a panel the register tabs run on.

Schema mirrors the register PDFs (NIN, name, nationality, CARD_ID_NO, shares, %)
so a real register drops into the same slot, with four columns added that the
dashboard needs and the redacted PDFs do not expose: investor type, the
passive/active class, the related-party flag and the board-member flag.

Aggregates are anchored to figures the QSE feed actually publishes, so the
synthetic book reconciles against real data:

    total shares    4,493,329,500          (README, qe.com.qa)
    cohort splits   OwnershipPercentage    (2026-08-13 snapshot)

The three related parties are the ones the client's own PDF names in its
"Total Without Related Parties" line: UCC, Infra Road and H'Collective.

Holders enter and leave. Roughly one in seven is not on the register for the
whole panel, which is what makes "who entered / who left" a real question rather
than an empty table — and it is why the detectors in discover.py run on the
balanced subset rather than on this.

Five behaviours are PLANTED. discover.py is not told about them and has to find
them from the panel alone; that is the whole point of the scan.
"""
from __future__ import annotations
import csv, json, math, random
from pathlib import Path

SEED = 20260906
random.seed(SEED)

OUT = Path(__file__).resolve().parent.parent / "out" / "synth"
TOTAL_SHARES = 4_493_329_500

# Real cohort weights from the 2026-08-13 OwnershipPercentage snapshot, with the
# holder counts scaled up so a "top 200" cut is a cut and not the whole book.
COHORTS = [
    ("QTR", "Institutions", 26.047,  30),
    ("QTR", "Individuals",  69.318, 115),
    ("FRN", "Institutions",  3.044,  50),
    ("FRN", "Individuals",   0.536,  20),
    ("ARB", "Individuals",   0.775,  20),
    ("GCC", "Institutions",  0.250,  10),
    ("GCC", "Individuals",   0.031,   5),
]

# The 250 named holders are the top of the book, not all of it — the client's own
# files are 100-row extracts of something longer. The rest sits in an untracked
# tail, and that tail is what makes the register add up: when a tracked holder
# buys, the shares come from the tail, and when one sells they go back to it.
#
# Without it every holder's share count has to be rescaled each month so the book
# still totals 4.49B, which silently moves holders who never dealt. A register
# where all 226 names change every single month is not a register.
TRACKED_SHARE = 0.965

# How often a holder deals at all, by class. Most of the book does nothing in
# any given month, which is the single most important thing to get right here.
TRADE_ODDS = {"A": 0.70, "P": 0.15, "board": 0.06, "related": 0.04}
TRADE_SIZE = {"A": 0.055, "P": 0.030, "board": 0.010, "related": 0.006}

MONTHS = [(y, m) for y in (2024, 2025, 2026) for m in range(1, 13)]
MONTHS = [x for x in MONTHS if (2024, 9) <= x <= (2026, 8)]      # 24 months

# Nationality codes as the real files spell them — the register mixes ISO-3 with
# long names and a couple of non-standard codes, and the dashboard has to fold
# them together rather than assume they are clean.
FOREIGN = ["USA", "UK", "UKZ", "IRL", "Irland", "CYM", "VGB", "CAN", "SWI", "KOR", "SDI"]
ARAB    = ["IRQ", "SYR", "PLS", "JOR", "EGY", "LBN"]
GULF    = ["UAE", "KSA", "KWT", "BHR", "OMN"]

STEM = ["Al Rayan", "Doha", "Qatar Pension", "Gulf Horizon", "Msheireb", "Lusail",
        "Sidra", "Al Bidda", "Corniche", "Katara", "Dukhan", "Zubarah", "Meridian",
        "Blackwater", "Sterling Gulf", "Northgate", "Helios", "Cedar Rock", "Ardent",
        "Pinebridge", "Vantage", "Kestrel", "Orion", "Talos", "Aspen", "Brightwater",
        "Carrick", "Dunmore", "Eastvale", "Fairhaven", "Glenmore", "Harrow",
        "Ironbridge", "Jadeite", "Kingsmere", "Larkspur", "Marlowe", "Nordhaven"]
TAIL = ["Capital", "Asset Mgmt", "Partners", "Investments", "Ventures", "Advisors",
        "Frontier", "EM Capital", "MENA Equity", "Emerging Mkts", "Holding", "Securities"]
FIRST = ["Mohammed", "Ahmed", "Ali", "Fatima", "Khalid", "Noora", "Hamad", "Aisha",
         "Jassim", "Maryam", "Saeed", "Latifa", "Rashid", "Sara", "Nasser", "Hessa",
         "Faisal", "Amna", "Tariq", "Reem", "Abdulla", "Shaikha", "Yousef", "Dana"]
LAST = ["Al-Thani", "Al-Kuwari", "Al-Mannai", "Al-Sulaiti", "Al-Emadi", "Al-Marri",
        "Al-Naimi", "Al-Attiyah", "Al-Dosari", "Al-Hajri", "Al-Misnad", "Al-Ansari",
        "Al-Khater", "Al-Buainain", "Al-Sada", "Al-Jaber"]

RELATED = {"UCC Holding", "Infra Road Trading", "Health Collective W.L.L."}
N_BOARD = 9


def _name(kind: str, used: set) -> str:
    for _ in range(800):
        n = (f"{random.choice(STEM)} {random.choice(TAIL)}" if kind == "Institutions"
             else f"{random.choice(FIRST)} {random.choice(LAST)}")
        if n not in used:
            used.add(n)
            return n
    return f"Holder {len(used) + 1}"


def _nationality(code: str) -> str:
    """The register stores a country, not the cohort bucket the exchange reports."""
    return {"QTR": "QTR", "FRN": None, "ARB": None, "GCC": None}[code] or random.choice(
        {"FRN": FOREIGN, "ARB": ARAB, "GCC": GULF}[code])


def _lifespan(n: int) -> tuple[int, int]:
    """First and last month a holder is on the register, inclusive.

    Most holders are there throughout — a register is mostly stable, and a book
    where a third of the names churn every year would be the finding rather than
    the backdrop. The rest is what the entered/left tables are built from.
    """
    r = random.random()
    if r < 0.86:
        return 0, n - 1                                   # there all along
    if r < 0.93:
        return random.randint(3, n - 5), n - 1            # came in, still there
    if r < 0.98:
        return 0, random.randint(4, n - 3)                # was there, left
    return random.randint(2, 7), random.randint(13, n - 2)  # in and out again


def build_holders() -> list[dict]:
    """Holders across the panel. Cohort share counts hold the real percentages."""
    holders, used, nin = [], set(), 10_000_001
    forced = {("QTR", "Institutions"): sorted(RELATED)}
    for code, itype, pct, n in COHORTS:
        pool = TOTAL_SHARES * TRACKED_SHARE * pct / 100.0
        # Zipf split: a few large holders, a long tail — as real registers look.
        w = [1.0 / (i + 1) ** 1.15 for i in range(n)]
        s = sum(w)
        names = forced.get((code, itype), [])[:]
        for i in range(n):
            nm = names.pop(0) if names else _name(itype, used)
            used.add(nm)
            related = nm in RELATED
            first, last = (0, len(MONTHS) - 1) if related else _lifespan(len(MONTHS))
            holders.append({
                "nin": nin, "name": nm,
                "nationality": "QTR" if code == "QTR" else _nationality(code),
                "bucket": code, "investor_type": itype,
                "base": pool * w[i] / s, "cohort": f"{code}/{itype}",
                "related": related, "board": False,
                # Passive holders sit on a position; active ones work it. The
                # class drives the noise, so the column and the behaviour agree.
                "cls": "P" if random.random() < 0.58 else "A",
                "first": first, "last": last, "behaviour": "drift",
            })
            nin += 1
    return holders


def plant(holders: list[dict]) -> dict:
    """Five latent behaviours. discover.py must recover these unaided."""
    # Only holders present for the whole panel can carry a behaviour a
    # correlation detector could find — a pattern needs a run of months.
    full = [h for h in holders
            if h["first"] == 0 and h["last"] == len(MONTHS) - 1 and not h["related"]]
    by = lambda c: [h for h in full if h["cohort"] == c]
    fi, qi = by("FRN/Institutions"), by("QTR/Institutions")

    truth = {}
    fi[0]["behaviour"] = "leaker";        truth["leakage"] = fi[0]["name"]
    fi[1]["behaviour"] = "twin_a"
    fi[2]["behaviour"] = "twin_b";        truth["coordinated_pair"] = [fi[1]["name"], fi[2]["name"]]
    qi[1]["behaviour"] = "transfer_out"
    qi[2]["behaviour"] = "transfer_in";   truth["internal_transfer"] = [qi[1]["name"], qi[2]["name"]]
    fi[3]["behaviour"] = "contrarian";    truth["contrarian"] = fi[3]["name"]
    qi[3]["behaviour"] = "creeper";       truth["threshold_creeper"] = qi[3]["name"]
    for h in (fi[1], fi[2], fi[3], qi[3], fi[0]):
        h["cls"] = "A"
    qi[3]["cls"] = "P"                    # the creeper reads passive and is not
    return truth


def seat_board(holders: list[dict]) -> list[str]:
    """Directors, as a flag on the register rather than a separate list.

    Generated, not real. A real director's name against a fabricated holding is
    the one thing this file must never produce.
    """
    # Never seat a holder that is already carrying a planted behaviour. The
    # movement loop tests the board branch before the behaviour branch, so a
    # director who was also the transfer counterparty would silently stop being
    # one — the behaviour is still in _ground_truth.json, and the scan is then
    # marked down for missing something that was never actually written.
    seats = [h for h in holders
             if h["bucket"] == "QTR" and not h["related"]
             and h["behaviour"] == "drift"
             and h["first"] == 0 and h["last"] == len(MONTHS) - 1]
    chosen = seats[:2] + seats[len(seats) // 3:][:N_BOARD - 2]
    for h in chosen[:N_BOARD]:
        h["board"] = True
        h["cls"] = "P"                    # directors sit on stock, they do not trade it
    return [h["name"] for h in chosen[:N_BOARD]]


def market(n: int) -> tuple[list[float], list[dict]]:
    """Monthly close plus disclosure events, in listening.py's shape."""
    px, p = [], 4.10
    for _ in range(n):
        p *= math.exp(random.gauss(0.002, 0.055)); px.append(round(p, 3))

    neg_m = {3, 9, 14, 19}          # negative disclosures
    pos_m = {1, 6, 11, 16, 21}      # positive disclosures
    ev = []
    for i, (y, m) in enumerate(MONTHS):
        if i in neg_m:
            ev.append({"month": f"{y}-{m:02d}", "sentiment": "Negative",
                       "headline": "Estithmar Holding Q.P.S.C.: discloses delay in project handover"})
        if i in pos_m:
            ev.append({"month": f"{y}-{m:02d}", "sentiment": "Positive",
                       "headline": "Estithmar Holding Q.P.S.C.: announces contract award"})
    return px, ev


FIELDS = ["nin", "name", "nationality", "card_id_no", "investor_type", "cls",
          "related_party", "board_member", "shares", "pct"]


def run() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for stale in OUT.glob("register_*.csv"):
        stale.unlink()

    holders = build_holders()
    truth = plant(holders)
    board = seat_board(holders)
    px, events = market(len(MONTHS))
    neg = {e["month"] for e in events if e["sentiment"] == "Negative"}
    labels = [f"{y}-{m:02d}" for y, m in MONTHS]
    nxt = {labels[i]: labels[i + 1] for i in range(len(labels) - 1)}
    pre_neg = {m for m, n in nxt.items() if n in neg}          # month before bad news

    state = {h["nin"]: int(round(h["base"])) for h in holders}
    tail = TOTAL_SHARES - sum(state[h["nin"]] for h in holders if h["first"] == 0)
    twin_shock = {}
    alive_before: set[int] = set()

    def deal(h: dict, i: int, lab: str, ret: float) -> float:
        """The fraction of its holding a holder moves this month. 0.0 = no deal."""
        b = h["behaviour"]
        if b == "leaker":
            return -0.30 if lab in pre_neg else random.gauss(0.02, 0.03)
        if b in ("twin_a", "twin_b"):
            return twin_shock[lab] + random.gauss(0, 0.012)
        if b == "transfer_out":
            return -0.09 if i % 4 == 2 else random.gauss(0, 0.012)
        if b == "transfer_in":
            return +0.09 if i % 4 == 2 else random.gauss(0, 0.012)
        if b == "contrarian":
            return -2.2 * ret + random.gauss(0, 0.02)
        if b == "creeper":
            return 0.055 + random.gauss(0, 0.004)
        kind = "related" if h["related"] else "board" if h["board"] else h["cls"]
        if random.random() > TRADE_ODDS[kind]:
            return 0.0                                   # did not deal this month
        return random.gauss(0.0, TRADE_SIZE[kind])

    for i, lab in enumerate(labels):
        ret = 0.0 if i == 0 else (px[i] - px[i - 1]) / px[i - 1]
        twin_shock[lab] = random.gauss(0, 0.075)
        live = [h for h in holders if h["first"] <= i <= h["last"]]
        now = {h["nin"] for h in live}

        # Arrivals are bought out of the tail, departures are sold back into it.
        for h in live:
            if h["nin"] not in alive_before and i > 0:
                tail -= state[h["nin"]]
        for h in holders:
            if h["nin"] in alive_before and h["nin"] not in now:
                tail += state[h["nin"]]
        alive_before = now

        for h in live:
            d = deal(h, i, lab, ret)
            if d == 0.0:
                continue
            change = int(round(state[h["nin"]] * d))
            change = max(change, 5_000 - state[h["nin"]])      # never below the floor
            change = min(change, tail - 1_000_000)             # never drain the tail
            state[h["nin"]] += change
            tail -= change

        rows = [{
            "nin": h["nin"], "name": h["name"], "nationality": h["nationality"],
            "card_id_no": 0, "investor_type": h["investor_type"], "cls": h["cls"],
            "related_party": h["related"], "board_member": h["board"],
            "shares": state[h["nin"]],
            "pct": round(100.0 * state[h["nin"]] / TOTAL_SHARES, 4),
        } for h in live]
        rows.sort(key=lambda r: -r["shares"])

        with open(OUT / f"register_{lab}.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)

    json.dump({"months": labels, "close": px, "events": events,
               "total_shares": TOTAL_SHARES, "related_parties": sorted(RELATED),
               "board_members": board},
              open(OUT / "market.json", "w"), indent=1)
    json.dump(truth, open(OUT / "_ground_truth.json", "w"), indent=1)

    spans = [(h["first"], h["last"]) for h in holders]
    whole = sum(1 for a, b in spans if a == 0 and b == len(labels) - 1)
    print(f"{len(holders)} holders x {len(labels)} months -> {OUT}")
    print(f"  {labels[0]} .. {labels[-1]} | {len(events)} events ({len(neg)} negative)")
    print(f"  {whole} on the register throughout, {len(holders) - whole} enter or leave")
    print(f"  {N_BOARD} board seats, {len(RELATED)} related parties")
    print(f"  planted: {len(truth)} behaviours (held in _ground_truth.json, not read by discover)")


if __name__ == "__main__":
    run()
