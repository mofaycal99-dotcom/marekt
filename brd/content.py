"""Content of the Business Requirements Document — the words, not the layout.

Edit here and re-run `python3 brd/render.py` to rebuild the PDF. The document is
a generated artifact: never hand-edit the PDF, because the next rebuild discards
it. Same rule the maps follow.
"""

META = {
    "title": "Qatar Market & Shareholder Intelligence",
    "subtitle": "Business Requirements — turning the working prototype into a production system",
    "reference": "DTG-BR-QMSI-v0.1 (structure per DTG-METH-BR-v1.0)",
    "version": "v0.1 — draft for engineering review",
    "owner": "Datategy — Delivery",
    "prepared_for": "Engineering / delivery team",
    "requesting": "Power International Holding (PIH); requesting entity Estithmar Holding (QSE: IGRD)",
    "date": "27/09/2026",
    "classification": "Internal — Datategy. Contains client context; not for onward distribution.",
    "methodology": "ISO/IEC 42001 & 12792 (SC 42) - structured business-analysis practice",
}

NAMING_NOTE = (
    "Naming. Client-facing material must read \"NAWA Cloud, powered by Datategy\". "
    "\"Agentium\" is internal only. This document is internal and uses neutral "
    "product naming throughout; anything lifted from it into a client deck must be "
    "renamed before it leaves the building."
)

INTRO = [
    ("What this document is",
     "A working prototype of this system exists and runs. It rebuilds the Estithmar "
     "share update automatically from the exchange, carries a shareholder-register "
     "book of record and an unsupervised scan over that register, and answers questions "
     "in natural language over everything on screen. It is a demonstrator: it proves the "
     "analysis and the interface, and it is deliberately not a production system."),
    ("What it is not",
     "The prototype has no authentication, no database, no scheduler, no multi-tenancy "
     "and no licensed data. Its market data is scraped from a public website, and its "
     "shareholder register is generated, because the register extracts supplied by the "
     "client are redacted. Section 11 and Appendix A state exactly which parts are "
     "demonstration scaffolding and which are load-bearing."),
    ("How to read it",
     "Sections 1-3 are the business case. Sections 4-6 are what the system must do and "
     "how well. Section 7 is the one to read first if you are estimating: the data "
     "licensing position decides the shape of the build, and one half of it may not be "
     "purchasable at all. Sections 8-9 are the decision logic already implemented and "
     "the guardrails around it."),
]

CONTEXT = [
    ("Client / entity",
     "Power International Holding (PIH) - diversified holding group, Doha. Requesting "
     "entity: Estithmar Holding Q.P.S.C., listed on the Qatar Stock Exchange as IGRD, "
     "4,493,329,500 shares in issue."),
    ("Sponsor & business owner",
     "[to confirm] The prototype was built against material supplied through the PIH "
     "engagement. The sponsor for a production build has not been named and must be "
     "before scoping is signed off."),
    ("System in scope",
     "Qatar Market & Shareholder Intelligence. Five capabilities: (1) a market dashboard "
     "reproducing the daily share update from exchange data; (2) news and press listening; "
     "(3) a shareholder-register book of record with month-over-month comparison; (4) an "
     "unsupervised scan of the register for undeclared behaviour; (5) natural-language "
     "question answering over all of the above."),
    ("Current situation",
     "The daily share update is produced by hand and circulated as a PDF by email; the "
     "sample supplied is dated 13 August 2026. Shareholder-register analysis is produced "
     "manually as Excel two-period comparisons - three cuts (holdings above 500K, companies "
     "and funds, full list), each with a total line and a second total excluding the three "
     "named related parties. Both are recurring manual work on data that already exists in "
     "machine-readable form."),
]

PERSONA = [
    ("Persona & volume",
     "Primary: Investor Relations and the CFO office at the listed entity - a small group, "
     "under ten people, producing recurring reporting for the board and for investors. "
     "Secondary: Group Treasury and Corporate Finance, consuming the market view."),
    ("Current tools",
     "Microsoft Excel (register comparisons, share update workbooks), PowerPoint and PDF "
     "for circulation, email, the QSE public website, and depository extracts supplied as "
     "PDF."),
    ("Job-to-be-done",
     "When the month closes and the register extract arrives, I want the book compared "
     "against the prior month, the movements attributed, and the exceptions flagged, so I "
     "can brief the CFO without rebuilding a workbook."),
    ("AI literacy", "Medium. Comfortable with dashboards and Excel; not with statistics."),
    ("Trust posture",
     "Trusts the output only when every figure traces to the register or to the exchange, "
     "and when nothing is invented. Two specific failure modes destroy trust immediately: "
     "a holder named who does not exist, and a figure that cannot be reconciled to the "
     "source. A chart that requires explanation is treated as a chart that is hiding "
     "something - the prototype was reworked twice on exactly this point."),
]

AS_IS = [
    ["Step", "Actor", "Systems", "Time", "Pain point"],
    ["Pull the daily share and index figures", "IR analyst", "QSE website", "~30 min/day",
     "Manual transcription; figures re-keyed into a workbook"],
    ["Build the share update page", "IR analyst", "Excel, PowerPoint", "~1 h/day",
     "Rebuilt each day; formatting drift between issues"],
    ["Circulate as PDF", "IR analyst", "Email", "~10 min/day",
     "No version history; recipients cannot interrogate the figures"],
    ["Request the register extract", "IR / Company Secretary", "Depository, email",
     "days 1-3 of the month", "Arrives as PDF; no machine-readable form"],
    ["Rebuild the register comparison", "IR analyst", "Excel", "~half a day/month",
     "Three cuts rebuilt by hand; totals and the related-party exclusion recomputed each time"],
    ["Identify what changed", "IR analyst", "Excel", "~half a day/month",
     "Entries and exits found by eye; behaviour across months not analysed at all"],
    ["Brief the CFO", "IR manager", "PowerPoint", "~2 h/month",
     "Narrative assembled manually; no standing watchlist"],
]

TO_BE = [
    ["Step", "Performed by", "Systems", "Notes"],
    ["Ingest market data on the exchange's own 5-minute cadence", "System",
     "Licensed market-data feed", "Replaces daily manual transcription entirely"],
    ["Render the share update", "System", "Application", "Same layout as the circulated PDF; exportable"],
    ["Ingest the monthly register extract", "System", "Depository file transfer",
     "Requires a machine-readable extract; see R-3 in section 11"],
    ["Produce the three cuts, totals and the ex-related-party line", "System", "Application",
     "Reproduces the existing workbook exactly, including its two total lines"],
    ["Compare against any prior month; list entries, exits and dealings", "System",
     "Application", "Not possible from a single snapshot - drives requirement FR-12"],
    ["Flag exceptions against stated rules", "System", "Application",
     "Each item carries the rule and the figure that tripped it"],
    ["Review, annotate, decide", "Human (IR / CFO office)", "Application",
     "The system proposes; a person decides. No automated external action."],
    ["Brief the CFO", "Human (IR manager)", "Application export",
     "Executive snapshot and watchlist generated; narrative remains a human judgement"],
]

OUTCOMES = [
    ["ID", "Business outcome", "Why it matters", "Target signal"],
    ["BO-1", "Recurring reporting effort removed",
     "Roughly 1.5 person-days a month plus ~1.7 hours a day are spent rebuilding reports "
     "from data that is already machine-readable.",
     "Manual preparation time for the share update and the register comparison reduced to review only"],
    ["BO-2", "Register movements attributed rather than eyeballed",
     "Entries, exits and dealings are currently found by inspection, so small movements "
     "and anything spread across months are missed.",
     "Every holder movement between two months reported, with a stated status"],
    ["BO-3", "Exceptions surfaced before they become disclosures",
     "Approaches to the disclosure threshold, related-party and director dealings, and "
     "concentration shifts are the events with a regulatory consequence.",
     "Each reporting cycle produces a watchlist with a named rule per item"],
    ["BO-4", "Behaviour visible that aggregate reporting cannot show",
     "The exchange publishes ownership only as seven nationality and investor-type "
     "buckets. Coordination, off-market transfer and threshold creep are invisible at "
     "that resolution.",
     "Findings reported per holder, each with its evidence"],
    ["BO-5", "A defensible, auditable basis for what is reported",
     "Anything shown to a board or a regulator must reconcile to source.",
     "Every figure traceable to the register or the exchange feed; reconciliation enforced by test"],
    ["BO-6", "Intraday market history accumulated",
     "The exchange publishes no intraday history. A tick not captured is unrecoverable.",
     "Continuous capture running from go-live, backed up off the writing host"],
]

FUNCTIONAL = [
    ["ID", "Requirement", "Pri", "Module"],
    ["FR-1", "Ingest the exchange's live instrument feed on its 5-minute publication cadence and present price, volume, value, index level and market state.", "M", "Market"],
    ["FR-2", "Reproduce the circulated share-update page: OHLC, previous close, change, 52-week range, share count, market cap, price-to-book, cap ranks, sector and index comparison.", "M", "Market"],
    ["FR-3", "Present daily, weekly and monthly reporting periods, each from the exchange's own published file for that period rather than re-derived.", "M", "Market"],
    ["FR-4", "Present market breadth: top gainers, losers, by value and by volume.", "S", "Market"],
    ["FR-5", "Present ownership by nationality and investor type, shareholder activity by nationality and investor type, and insider trades, as published by the exchange.", "M", "Market"],
    ["FR-6", "Persist every live tick to an append-only store, deduplicated on the feed's own timestamp, and never overwrite a captured tick.", "M", "Archive"],
    ["FR-7", "Rebuild intraday price history for the current session from the captured archive.", "S", "Archive"],
    ["FR-8", "Ingest exchange disclosures and third-party press coverage, attributed to the issuing outlet with a working link to the source.", "S", "Listening"],
    ["FR-9", "Ingest a per-holder shareholder register as a monthly snapshot, carrying at minimum: holder identifier, name, nationality, investor type, share count.", "M", "Register"],
    ["FR-10", "Carry per holder, as maintained attributes rather than inferences: passive/active class, related-party flag, board-member flag.", "M", "Register"],
    ["FR-11", "Produce the cuts the existing workbook publishes - holdings above 500K, companies and funds, individuals, related parties, board members, top 200, full list - each as a two-period comparison with a difference column.", "M", "Register"],
    ["FR-12", "Report, between any two months: holders that entered, holders that left, holders that dealt, and holders that did not move.", "M", "Register"],
    ["FR-13", "Close every cut on two total lines: the cut total, and the total excluding related parties, naming them.", "M", "Register"],
    ["FR-14", "Report the book split by nationality (local vs international), region, class, investor type and affiliation, for the selected month and as a month-over-month series.", "M", "Register"],
    ["FR-15", "Report concentration: top-10, top-20, top-200, HHI, holders required to reach half the book, and free float excluding related parties.", "M", "Register"],
    ["FR-16", "Report free float on an index-provider basis - excluding related parties AND board holdings - alongside the ex-related figure.", "S", "Register"],
    ["FR-17", "Present every KPI against the prior month, prior quarter and prior year.", "M", "Register"],
    ["FR-18", "Produce a watchlist per reporting cycle. Each item must carry the rule that fired it, the figure that tripped it, and a recommended action.", "M", "Register"],
    ["FR-19", "Report a change of state, never a standing fact. A holder long above the disclosure threshold is already disclosed and must not be re-reported each cycle.", "M", "Register"],
    ["FR-20", "Detect, without being told what to look for: co-movement between holders, mirrored flow, reduction preceding an adverse disclosure, response to price, and monotonic accumulation toward the disclosure threshold.", "S", "Scan"],
    ["FR-21", "Classify every scanned holder into exactly one behavioural archetype, with thresholds calibrated on the book being analysed rather than on constants.", "S", "Scan"],
    ["FR-22", "Exclude holders not present for the full comparison window from correlation analysis, and report how many were excluded and why.", "M", "Scan"],
    ["FR-23", "Answer natural-language questions over the rendered state, quoting only figures present in it and stating plainly when a figure is absent.", "S", "Assistant"],
    ["FR-24", "Export the register comparison, the KPI set and the month-over-month trend as files suitable for a board pack.", "M", "Export"],
    ["FR-25", "Acquire every external source through its official or documented API where one exists. API first, always.", "M", "Ingestion"],
    ["FR-26", "Use scraping only as a fallback where no API is available, and only with the reason recorded against that source in section 7.", "M", "Ingestion"],
    ["FR-27", "Record, per ingestion run and per source, which path was used - API or fallback - and alert when a source silently drops from API to fallback.", "M", "Ingestion"],
    ["FR-28", "Isolate every source behind an adapter with a single interface, so replacing a scraper with a licensed API changes one component and nothing downstream.", "M", "Ingestion"],
    ["FR-29", "Authenticate every user against the client's own identity provider by single sign-on. No local passwords, no shared accounts.", "M", "Security"],
    ["FR-30", "Enforce role-based access control using the role matrix in section 6a. Deny by default: a capability not explicitly granted to a role is unreachable by that role.", "M", "Security"],
    ["FR-31", "Restrict the Register and Register scan capabilities to the Executive role. They must not be reachable by any other role, by direct URL, by export, or through the assistant.", "M", "Security"],
    ["FR-32", "Scope the assistant to the caller's role. A question asked by a user without register access must not be answered from register data.", "M", "Security"],
    ["FR-33", "Encrypt register data in transit (TLS 1.2 or better) and at rest. Holder identifiers and names to be encrypted at the field level, with keys held in a managed key store separate from the database.", "M", "Security"],
    ["FR-34", "Require step-up re-authentication before any export of register data.", "S", "Security"],
    ["FR-35", "Record a tamper-evident audit entry for every register view, query and export: who, what, when, from where. Retain per the client's policy.", "M", "Security"],
    ["FR-36", "Expire idle sessions and revoke access immediately when a user is removed at the identity provider.", "M", "Security"],
    ["FR-37", "Degrade per capability. A failure or outage in one data source must not prevent the others from rendering.", "M", "Platform"],
]

# Section 6a - the access matrix. Deny by default; a blank cell is a denial, not
# an omission. Note that the Administrator manages access and cannot read
# register data: separation of duties is the point, and it is the control an
# auditor will ask about first.
ROLES = [
    ["Role", "Market", "Listening", "Register", "Register scan", "Export", "Admin"],
    ["Executive - CEO, CFO", "Yes", "Yes", "Yes", "Yes", "Yes", "No"],
    ["IR Manager", "Yes", "Yes", "On explicit grant", "No", "Market only", "No"],
    ["Analyst", "Yes", "Yes", "No", "No", "No", "No"],
    ["Auditor", "No", "No", "Read-only, logged", "Read-only, logged", "No", "No"],
    ["Administrator", "No", "No", "No", "No", "No", "Yes"],
]

ROLES_NOTE = (
    "The client's instruction was that the register is reachable only with the "
    "CEO's account. This is written as a named Executive role rather than a "
    "single shared login, and the distinction matters: a shared account has no "
    "attribution, so the audit trail required by FR-35 cannot say who looked at "
    "the register; it cannot be revoked for one person; and it cannot be "
    "extended to the CFO without handing over the CEO's credentials. The role "
    "carries exactly the access asked for and starts with one member. Confirm "
    "with the sponsor before build."
)

NFR = [
    ["Quality", "Required", "Target / notes"],
    ["Sovereignty / data residency", "Yes",
     "Shareholder register data is client-confidential and identifies individuals. Residency to be confirmed with the client before any host is chosen. The prototype's language model is a third-party API outside the region - see S7 and C-7."],
    ["Security & identity", "Yes - highest priority",
     "Single sign-on against the client's identity provider; role-based access control, deny by default; Register and Register scan restricted to the Executive role; encryption in transit and at rest with field-level encryption of holder identity; step-up re-authentication before export; tamper-evident audit of every register access. Secrets in a managed key store, never in the repository. See FR-29 to FR-36 and the matrix in section 6a."],
    ["Robustness", "Yes",
     "Ingestion must be resumable and idempotent. A partial or failed market fetch must not corrupt the archive, and re-running a month's register ingest must not duplicate it."],
    ["Observability & audit", "Yes",
     "Every figure traceable to source. Ingestion runs logged with source, timestamp and outcome. Register access audited (FR-35)."],
    ["Scalability", "Should",
     "Single issuer at launch. Design for multiple issuers and multiple registers; the analysis layer is already issuer-agnostic, the data layer is not."],
    ["Performance & cost", "Yes",
     "Dashboard render under 5 s on warm data. Hard ceiling on total ingestion time per cycle, and a circuit breaker so an unreachable source fails in seconds rather than hanging - the prototype needed exactly this."],
    ["Availability & support", "Should",
     "Business hours, aligned to the QSE session (Sunday-Thursday, 09:30-13:15 Qatar time). Archive capture must run continuously through the session regardless of whether anyone is using the application."],
    ["Maintainability / extensibility", "Yes",
     "Analysis logic must stay independent of the data source: the register analysis works unchanged on a real register, with only the loader replaced. Preserve that separation."],
]

SOURCES = [
    ["#", "Source", "Type", "Access", "Status"],
    ["S1", "Exchange market data - prices, OHLCV, index and sector levels, fundamentals",
     "Commodity market data", "API first: licensed vendor or exchange API. Fallback: the public endpoints mapped in API_REFERENCE.md",
     "MUST be replaced by a licensed feed. Widely available from global vendors. Note the current path is undocumented HTTP endpoints rather than page scraping, so the adapter shape is already API-like."],
    ["S2", "Ownership by nationality and investor type; shareholder activity by nationality and investor type; insider trades",
     "Exchange only", "Currently scraped; no licence. No API offered",
     "HIGH RISK. Not a standard product in global market-data catalogues. Realistically available only from the exchange itself or a Gulf specialist. May not be licensable at all."],
    ["S3", "Per-holder shareholder register, monthly snapshot",
     "Client / depository", "Not yet supplied in usable form",
     "BLOCKING. The three extracts supplied are fully redacted - names, identifiers, share counts and percentages are all placeholders. Only the schema is real."],
    ["S4", "Related-party list", "Client-maintained", "Named in the client's own workbook",
     "Three entities named. Not derivable from the register; must be maintained by the client, with the basis for each stated."],
    ["S5", "Board-member list", "Client-maintained", "Not supplied",
     "Not derivable from the register. Directors holding through vehicles will not name-match, and family holdings are attributed under disclosure rules but not linked in the data."],
    ["S6", "Exchange disclosures and press coverage", "Public",
     "API first: exchange disclosure API and a licensed news API. Fallback: the public news feed in use today",
     "Usable. Aggregator terms to be checked for commercial use before the fallback is relied on."],
    ["S7", "Language model for question answering", "Third-party API", "Commercial API",
     "Provider must be agreed against the residency position in section 6 before any real register data reaches it."],
]

DECISIONS = [
    ["ID", "Decision", "Inputs", "Outcomes", "Threshold / default", "Escalation"],
    ["D1", "Is a holder approaching or crossing the disclosure threshold?",
     "Holding as % of shares in issue, this month and prior", "Crossed up / crossed down / approaching / no action",
     "Crossing at the statutory threshold; approaching within 1.5pp below it",
     "Always reported. Crossing is high severity."],
    ["D2", "Has a related party or director dealt?", "Holding change for flagged holders",
     "Reported / not reported", "Any movement", "Always reported; a filing question before an ownership one"],
    ["D3", "Has a significant holder left, or a significant holder arrived?",
     "Presence in two consecutive snapshots, size", "Reported / not reported",
     "Exit from the top 50; arrival above 500K shares", "Reported; an exit with no matching market volume implies a transfer"],
    ["D4", "Has the shape of the book moved materially?",
     "Top-10 concentration, nationality split, class split", "Reported / not reported",
     "1.0pp for concentration; 0.50pp for a segment", "Reported at medium severity"],
    ["D5", "Do two holders move together, or against each other?",
     "De-meaned monthly changes across the full window", "Co-movement / mirrored flow / neither",
     "Correlation beyond +/-0.85, with an offset test distinguishing a transfer from a trade",
     "Reported. Identification of the beneficial owner is a human task."],
    ["D6", "Did a holder reduce ahead of adverse disclosures?",
     "Monthly changes, disclosure calendar", "Reported / not reported",
     "Mean reduction materially below the holder's own norm in pre-event months, and never after",
     "High severity. Routed to compliance, not investor relations."],
    ["D7", "What kind of holder is this?",
     "Idiosyncratic volatility, correlation to price, monotonicity, drift",
     "One archetype per holder", "Calibrated on the book's own median volatility, not a constant",
     "Descriptive; no escalation"],
]

RULES = [
    ["ID", "Rule (IF ... THEN ...)", "Rationale"],
    ["R1", "IF a figure is not present in the ingested data THEN report it as absent; never estimate, interpolate or infer it.",
     "A wrong number in front of a board is worse than a missing one."],
    ["R2", "IF a holder did not deal in a period THEN report a zero change, not a recomputed one.",
     "Renormalising the book each period moves holders who never traded. A register where every holder changes every month is not a register."],
    ["R3", "IF a holder has been above the disclosure threshold across both periods without material movement THEN do not report it as a watch item.",
     "It is an already-disclosed fact. Repeating it buries the items that are new."],
    ["R4", "IF a source returns any HTTP response, including a 404 THEN treat the source as reachable.",
     "A 404 means no data for that day, which is normal. It must not be read as an outage."],
    ["R5", "IF a source fails at the network level more than twice consecutively THEN stop calling it and report it unreachable.",
     "Sequential per-request timeouts across a full ingestion turn a 20-second failure into an hour-long hang."],
    ["R6", "IF a capability's data source is unavailable THEN render every other capability normally.",
     "The register capabilities require no external data at all and must never be blocked by a market-data outage."],
    ["R7", "IF a watch item is raised THEN state the rule that raised it and the figure that tripped it.",
     "A threshold the business disagrees with must be one number to change, not an argument to have."],
    ["R8", "IF a segment split is drawn as a proportion THEN show any residual not covered by the named holders as its own share.",
     "Rescaling the named holders to 100% silently restates every figure."],
    ["R9", "IF asked about the provenance or reality of the data THEN answer plainly and immediately.",
     "Volunteering it in every answer is noise; denying it under direct questioning is the failure that loses the room."],
    ["R10", "IF a source offers an official API THEN use it; fall back to scraping only where no API exists, and record why.",
     "A scraper breaks silently when a page changes and carries no licence. An API is versioned, supported and contractual."],
    ["R11", "IF a source silently drops from its API to the fallback path THEN raise it as an operational alert, not a log line.",
     "An undetected fallback means the system is quietly running on an unlicensed, unsupported path."],
    ["R12", "IF a capability is not explicitly granted to a role THEN it is denied to that role.",
     "Deny by default. An omission in the matrix must fail closed."],
    ["R13", "IF a user without register access asks a question that would be answered from register data THEN decline and say why.",
     "Access control that the assistant can talk around is not access control."],
]

NEVER = [
    ["ID", "The system must never..."],
    ["N1", "Present a generated or placeholder holder as a real person or institution."],
    ["N2", "Deny, when asked, that demonstration data is demonstration data."],
    ["N3", "Execute, instruct or recommend a trade, or offer investment advice."],
    ["N4", "Transmit register data to any third party not covered by the agreed residency and processing position."],
    ["N5", "Overwrite or delete a captured market tick. The archive is append-only; the exchange publishes no intraday history and a lost tick is unrecoverable."],
    ["N6", "Make register data reachable without authentication, or by any role other than Executive."],
    ["N8", "Store register holder identifiers or names unencrypted at rest, or carry them over an unencrypted connection."],
    ["N9", "Authenticate through a shared or generic account. Every action must attribute to a named person."],
    ["N10", "Return register data through the assistant, an export, a log or an error message to a caller whose role does not carry register access."],
    ["N11", "Scrape a source that offers a usable API, or rely on a fallback path without recording that it was used."],
    ["N7", "Report a statistical finding as an established fact about a named party's intent."],
]

KPIS = [
    ["KPI", "Definition", "Baseline", "Target"],
    ["Manual preparation time", "Analyst hours per month spent building the share update and the register comparison",
     "~1.7 h/day plus ~1.5 days/month [to confirm]", "Review and sign-off only"],
    ["Reconciliation accuracy", "Share of reported figures reconciling exactly to source",
     "Manual, unmeasured", "100%, enforced by automated test"],
    ["Movement coverage", "Share of holder movements between two months that are reported",
     "Partial - found by inspection", "100% of holders, with a stated status each"],
    ["Exception lead time", "Working days between a threshold event occurring and it being surfaced",
     "Discovered during preparation, if at all", "Same cycle as the extract"],
    ["False-positive rate on the watchlist", "Items raised that require no action",
     "n/a", "Tracked per cycle; thresholds tuned against it"],
    ["Archive continuity", "Share of trading-session 5-minute ticks captured",
     "0 - capture not running in production", "Above 99% per session"],
    ["Availability during session", "Application available, QSE session hours", "n/a", "[to confirm with the business]"],
]

CONSTRAINTS = [
    ["#", "Constraint / assumption"],
    ["C-1", "ASSUMPTION. A machine-readable per-holder register can be obtained monthly. Everything in section 5 marked Register depends on this; the extracts supplied to date are redacted and unusable as data."],
    ["C-2", "CONSTRAINT. Market data is currently scraped from a public website with no licence. This is acceptable for a prototype and not for production. A licensed feed must be in place before go-live."],
    ["C-3", "RISK. The exchange-proprietary datasets (S2) may not be licensable at all. If they are not, the ownership, activity and insider-trade capabilities are out of scope and the market dashboard shrinks. This should be established during the RFI, not after contract."],
    ["C-4", "CONSTRAINT. Related-party and board-member lists are maintained by the client and cannot be derived from the register. Ownership of these lists must be assigned, with the basis for each entry recorded."],
    ["C-5", "CONSTRAINT. Two consecutive snapshots support a difference. They do not support behavioural analysis. Co-movement needs the full run of months; the scan requires roughly 24 monthly snapshots to be meaningful. On the two months supplied to date, most detectors return nothing."],
    ["C-6", "CONSTRAINT. Intraday market history cannot be backfilled. Capture must begin at go-live or earlier; every day of delay is permanently lost data."],
    ["C-7", "ASSUMPTION. Hosting, residency and the acceptable language-model provider will be agreed by the client before any real register data is loaded."],
    ["C-8", "CONSTRAINT. Directors holding through corporate vehicles, and family holdings attributed under disclosure rules, will not be identified by name matching. Coverage of the board cut is therefore incomplete by construction."],
    ["C-9", "ASSUMPTION. The prototype's analysis logic is reusable. The register analysis is written to be source-independent and is exercised by an automated suite; the ingestion layer is not reusable and is expected to be rebuilt."],
    ["C-10", "CONSTRAINT. Access control is not retrofittable in the prototype - it has none at all, and the register is reachable by anyone holding the URL. FR-29 to FR-36 are foundational and must be built before any real register data is loaded, not added at the end."],
    ["C-11", "ASSUMPTION. The client operates an identity provider supporting single sign-on, and will federate this application with it. If not, the authentication approach must be agreed before FR-29 can be estimated."],
    ["C-12", "CONSTRAINT. Encryption at rest and field-level encryption of holder identity require a managed key store and a key-rotation owner on the client side. Both are client decisions and neither is a code change."],
    ["C-13", "RISK. An API-first policy is only as good as the APIs available. Where no API exists the fallback is a scraper, which breaks silently when a page changes and carries no licence. Every fallback in section 7 is technical debt with a named reason and should carry a date for review."],
]

OUT_OF_SCOPE = [
    ["#", "Explicitly out of scope"],
    ["X-1", "Trading, order routing, or any instruction to buy or sell."],
    ["X-2", "Investment advice, recommendations or valuation opinions."],
    ["X-3", "Automated external communication. The system does not contact shareholders, file disclosures or send anything outward on its own."],
    ["X-4", "Determining whether a disclosure obligation has legally arisen. The system flags the figures; the judgement is the client's and their counsel's."],
    ["X-5", "Identifying beneficial ownership behind a holding. The system reports that two holdings move together; establishing why is a human investigation."],
    ["X-6", "Social-media listening. Attributing invented posts to real outlets is fabrication; this needs a licensed platform."],
    ["X-7", "Sub-5-minute market granularity. That requires the exchange's streaming feed, which is a separate licence and a separate build."],
    ["X-8", "Financial-statement and XBRL ingestion. Mapped but untested; a candidate for a later phase."],
]

APPENDIX = [
    ["Component", "State", "Reusable?", "Note"],
    ["Register analysis - cuts, totals, segments, entries/exits, KPIs, trend",
     "Complete, tested", "Yes",
     "Source-independent by design. Only the loader changes for a real register."],
    ["Register scan - five detectors, archetypes, watchlist mapping",
     "Complete, tested", "Yes",
     "Thresholds calibrate on the book analysed. Recovers all planted behaviours on the demonstration panel with no false positives."],
    ["Market dashboard rendering", "Complete", "Yes",
     "Reconciled field by field against the client's own circulated PDF; three figures disagree and the PDF appears to be the side in error."],
    ["Market data ingestion", "Working prototype", "No",
     "Scraping. Replace with a licensed feed. The endpoint mapping and the schema documentation carry over."],
    ["Tick archive", "Working prototype", "Partly",
     "Append-only store with deduplication on the feed's own timestamp. Storage layer to be replaced; the dedup rule and cadence findings carry over."],
    ["Shareholder register data", "Generated", "No",
     "Generated because the supplied extracts are redacted. Schema mirrors the real files. Must be replaced by a real ingest."],
    ["Question answering", "Working prototype", "Partly",
     "Briefing construction is reusable; the model provider is a decision, not a given."],
    ["Authentication, authorisation, audit", "Absent", "n/a", "Build from scratch. Blocking for any real data."],
    ["Persistence", "Flat files", "No", "No database. Adequate for one issuer and one analyst; not for production."],
    ["Scheduling", "Manual", "No", "Capture is a command run by hand. Needs a scheduler with monitoring."],
    ["Automated tests", "154 checks, no network", "Yes",
     "Covers reconciliation of every cut and segment, period aggregation, and the detector behaviour. Extend rather than replace."],
]


# ==================================================================== screens
# The dev team is rebuilding something that already exists and runs. This is the
# inventory of it, screen by screen and panel by panel, so nothing has to be
# reverse-engineered out of the prototype.

SCREENS = [
    ("Screen 1 - Market dashboard", "Live, from the exchange. One screen, no scrolling by design.", [
        ["Panel", "Contents"],
        ["Ticker bar", "Biggest absolute movers market-wide, scrolling; symbol, last, change %"],
        ["Selector row", "Company picker, range (1M / 3M / Max), period (Daily / Weekly / Monthly), export popover"],
        ["Price and volume chart", "Daily closes as a line above, volume as columns below, one shared x-axis. Not a dual axis - a second y-scale invites a price/volume relationship to be read out of the scales"],
        ["Share statistics", "~20 figures: OHLC, previous close, change and change %, 1-year change, 52-week high/low, volume, value, share count, market cap, price-to-book, dividend yield, cap rank to market and to sector"],
        ["Index statistics", "~14 figures for the QE Index over the same period"],
        ["Share vs index vs sector", "Percentage change of the three side by side"],
        ["Sector indices", "All seven sector index moves for the period"],
        ["Ownership by nationality", "Qatari / GCC / Arab / Foreign, current against prior reading. Logarithmic axis, as the source publishes it, with the caption stating that bar heights are therefore not proportional"],
        ["Institutions share", "Institutions vs individuals as a tile with a percentage-point delta. The source's own line chart is not reproduced: its axis spans 29.383-29.405%, turning a 0.02pp move into a cliff"],
        ["Market breadth", "Top five gainers, losers, by value and by volume - four tables"],
        ["Shareholder activity", "Buy and sell, value and volume, by nationality x investor type, pivoted to one row per nationality"],
        ["Insider trades", "Insider dealings for the period, market-wide"],
        ["Export", "Bundle JSON, three CSVs and a self-contained printable HTML, in a popover so they cost no vertical space"],
    ]),
    ("Screen 2 - News listening", "Exchange disclosures and press coverage. No social media - see X-6.", [
        ["Panel", "Contents"],
        ["Priority coverage", "Articles naming the selected company or its divisions, with date, outlet, headline and a working link to the source"],
        ["Whole market", "Market-wide coverage over a rolling window, filterable"],
        ["Sentiment split", "Positive / negative / neutral as a donut. Sentiment is a transparent keyword rule, labelled as a stand-in for a licensed listening platform, never as measurement"],
        ["Most-mentioned companies", "Ranked by article count, with share of coverage"],
        ["Article table", "Date, time, outlet, company attribution, sentiment, headline, link"],
    ]),
    ("Screen 3 - Register (book of record)", "The reporting half. Ten numbered sections, all visible; no drill-downs.", [
        ["Section", "Contents"],
        ["Month selectors", "The month to report, and any earlier month to compare it against"],
        ["1 Executive snapshot", "Six headline tiles, then an 18-KPI table with each KPI against 1, 3 and 12 months. Red marks movement in the direction that KPI is monitored for, which is not the same as down"],
        ["2 Top 200 holders", "Sortable comparison table: holder, nationality, type, class, related and board flags, shares and % for both months, delta, status. Closes on the two total lines"],
        ["3 / 3b Local vs international, by region", "Table, pie for the selected month, and a month-over-month line. Four regional buckets"],
        ["4 / 4b By class (P/A), by investor type", "Same three-part treatment"],
        ["5 Related parties", "The three named in the client's own file, with holdings and movement"],
        ["6 Board members", "Directors on the register, holdings and movement"],
        ["7 Holdings above 500K", "The cut the client's PDF publishes, reproduced with its two total lines"],
        ["8 Who entered and who left", "Four tables: entered, left, added most, trimmed most"],
        ["9 Month over month", "24 months x 16 columns - holders, in, out, dealt, concentration, float, splits, HHI - newest first, with a metric picker plotting any column"],
        ["10 What to watch", "Severity-ranked cards, each with the rule that fired it, the figure that tripped it, and a recommended action"],
        ["Export", "Full comparison, the KPI set and the trend, as CSV for the board pack"],
    ]),
    ("Screen 4 - Register scan (pattern detection)", "The discovery half. Eight numbered sections.", [
        ["Section", "Contents"],
        ["1 Executive snapshot", "Holders scanned and how many were excluded and why, findings and how many are high severity, holders flagged, float under a finding, holders moving in pairs, largest flagged holding"],
        ["2 Holder archetypes", "Every scanned holder classified into exactly one archetype, as cards: count, share of float, average move, and what the label means"],
        ["3 Who grew, who shrank, who trades", "Two ranked bar charts - change in holding over the window, and typical monthly movement. Blue is a holder the scan reported, grey is one it did not"],
        ["4 What the scan found", "Finding cards filtered by type, beside a trajectory chart plotting the holders behind the selected finding over the full panel, with adverse disclosures marked"],
        ["5 What the flagged holders did in a month", "Month picker, then each flagged holder's shares before and after, delta and share of the company"],
        ["6 What to watch", "Every finding as a severity-ranked card with a recommended action"],
        ["7 Was the scan right?", "Planted behaviour against recovered, for the demonstration panel only. Not part of the scan"],
        ["8 Register snapshot", "The raw register for any month on the panel"],
    ]),
    ("Screen 5 - Ask the data", "Natural-language questions over whatever is currently rendered.", [
        ["Panel", "Contents"],
        ["Identity", "Branded as the company under analysis, not as the model behind it"],
        ["Suggestion chips", "Seven starting questions covering share performance, market movers, valuation, ownership, news, price history and the register"],
        ["Conversation", "Streamed answers, tables where the answer is a comparison"],
        ["Input", "Text, plus voice typing through the browser's own speech recognition - no audio leaves the page, and the transcript lands in the input rather than being sent, so a misheard ticker can be corrected"],
        ["Language", "English, French and Arabic dictation; right-to-left layout detected per turn"],
    ]),
]


# ============================================================== user stories
# Written as the dev team will work from them. Acceptance criteria are stated as
# conditions a test can assert, not as adjectives.

STORIES = [
    ["ID", "Story", "Acceptance criteria"],
    ["US-1", "As an IR analyst, I want the share update built automatically from the exchange, so that I stop transcribing figures by hand.",
     "Every field on the circulated PDF is present and reconciles to the exchange's own published file for the period. Any figure that does not reconcile is listed with the discrepancy."],
    ["US-2", "As an IR analyst, I want daily, weekly and monthly views, so that I can answer a question at the resolution it was asked.",
     "Each period's figures come from that period's published file, not re-derived from daily data. A period with nothing published does not appear in the selector."],
    ["US-3", "As a treasury analyst, I want intraday price history for the current session, so that I can see how the day developed.",
     "Points accumulate from the captured archive. Where fewer than six ticks exist for the session, the view is not offered - no placeholder panel."],
    ["US-4", "As the CFO, I want a one-page snapshot of the register, so that I can open the board pack and know the position in thirty seconds.",
     "Six headline tiles plus every KPI against 1, 3 and 12 months. Each KPI names the direction it is monitored for."],
    ["US-5", "As an IR manager, I want the register compared against any earlier month, so that I can explain a change over a quarter rather than only a month.",
     "Any two months on the panel can be compared. Holders present in one and not the other are reported as entered or left, never as a change from zero."],
    ["US-6", "As an IR manager, I want to know who entered and who left, so that I can brief on the shape of the base and not just its size.",
     "Every holder in either month appears with a status of entered, left, dealt or unchanged. The four counts sum to the union of the two months."],
    ["US-7", "As an IR analyst, I want the cuts my workbook already publishes, so that the output is recognisable without retraining.",
     "Above 500K, companies and funds, individuals, related parties, board members, top 200 and full list. Each closes on a total and a total excluding related parties."],
    ["US-8", "As the CFO, I want the book split by nationality, region, class and investor type, so that I can see where ownership is moving.",
     "Each split reconciles to the month's snapshot. Any residual below the reporting floor is shown as its own share, never absorbed by rescaling."],
    ["US-9", "As a compliance officer, I want holders approaching the disclosure threshold flagged, so that a crossing is never a surprise.",
     "A crossing in either direction is high severity. An approach from below is reported. A holder steadily above the threshold without material movement is not re-reported each cycle."],
    ["US-10", "As a compliance officer, I want related-party and director dealings surfaced, so that I can check them against the closed-period calendar.",
     "Any movement by a flagged holder is reported, however small, with the figure."],
    ["US-11", "As the CFO, I want every flagged item to carry what to do about it, so that the report ends in a decision rather than an observation.",
     "Each watch item carries a severity, the rule that fired it, the figure that tripped it, and a recommended action."],
    ["US-12", "As a data scientist, I want holders that move together identified, so that a stake being built across several names is visible.",
     "Pairs beyond the correlation floor are reported with their coefficient and window. Pairs explained by a common driver are distinguished from pairs that are not."],
    ["US-13", "As a compliance officer, I want holders that reduced ahead of adverse disclosures identified, so that I can route it to the right place.",
     "Reported with the pre-event and other-period means, and the count of events. High severity, routed to compliance."],
    ["US-14", "As an IR manager, I want every holder described, not only the flagged ones, so that I understand the base rather than a list of oddities.",
     "Every scanned holder carries exactly one archetype. The archetype counts sum to the number scanned, and the float shares sum to 100%."],
    ["US-15", "As a sceptical reviewer, I want to know what the scan could not look at, so that I can judge what its silence means.",
     "The count of holders excluded from the scan, and the reason, is reported alongside the findings."],
    ["US-16", "As any user, I want to ask a question in plain language, so that I do not have to find the panel that holds the answer.",
     "Answers quote only figures present in the current render. A figure not present is reported as absent, never estimated."],
    ["US-17", "As a security officer, I want register access restricted and recorded, so that I can answer who saw what.",
     "Only the Executive role reaches the Register and Register scan capabilities, by any route including the assistant and exports. Every access writes a tamper-evident audit entry."],
    ["US-18", "As an operator, I want a source outage to fail fast and loudly, so that one feed cannot take the application down.",
     "An unreachable source fails within seconds, is reported on the affected capability only, and every other capability renders normally."],
]


# ==================================================== data science workstream

DS_INTRO = (
    "The Register scan is not feature work and should not be estimated as such. "
    "It is a data-science workstream with its own method, its own validation and "
    "its own failure modes, and it is the part of this system most likely to be "
    "wrong in a way that is invisible until someone checks. The prototype "
    "carries a working implementation of everything below; what it does not "
    "carry is the validation a production deployment needs on a real book."
)

DS_WORK = [
    ["Stage", "What it involves", "Why it is not trivial"],
    ["Panel construction",
     "Assemble a rectangle of holder x month from monthly snapshots. Exclude holders not present throughout, and report how many were excluded.",
     "Filling absent months with zeros invents a run of 'did nothing', which then correlates with every other holder that also did nothing. The exclusion costs recall on newcomers and is the only honest option."],
    ["Common-factor removal",
     "Subtract the cross-sectional median move from every holder, every month.",
     "A register is zero-sum in percentage terms: when one cohort adds, every other holder's share falls even if they never traded. Without this step any two passive holders correlate above 0.99, and a real pattern appears inverted in everyone else - the detector finds the reflection as readily as the cause."],
    ["Feature engineering",
     "Per holder: idiosyncratic volatility, drift across the window, monotonicity, correlation to the price series, pairwise correlation and net offset.",
     "Each feature has to survive a book with a different liquidity profile. Features calibrated on one issuer do not transfer."],
    ["Detector design and calibration",
     "Five detectors, each with a threshold. Thresholds derived from the book being analysed rather than fixed.",
     "A thinly held register and a liquid one differ by an order of magnitude in monthly variance. A constant tuned on one classifies the whole of the other."],
    ["Precedence and labelling",
     "Resolve holders that satisfy several detectors into one reading, by specificity.",
     "A cohort sharing a driver correlates pairwise as a side effect. Labelling those pairs 'coordinated' reports one mechanism twice and names it wrongly the second time."],
    ["Validation",
     "A generated panel with known behaviours planted, scored for recall AND precision. A null panel with nothing planted, which must return nothing.",
     "Recall alone is meaningless - a detector that flags everything recovers everything. The null panel is the only evidence the scan is not pattern-matching noise, and it is the thing a quantitative reviewer will ask for first."],
    ["False-positive management",
     "Track items raised that required no action; tune thresholds against that rate each cycle.",
     "A watchlist that cries wolf is switched off within two cycles, and switching it off is indistinguishable from it working."],
    ["Presentation",
     "Render findings so a finance reader can act on them without a statistician present.",
     "The prototype's first two attempts at this failed in review. A chart that needs a walkthrough is treated as a chart that is hiding something."],
]

DS_EFFORT = (
    "Skills required: a data scientist for the detector and validation work, not "
    "a backend engineer following a specification. Expect iteration against a "
    "real book once one is available - thresholds that hold on a generated panel "
    "are a starting point, not an answer. Budget explicitly for the null-panel "
    "and false-positive work; it produces no visible feature and is the reason "
    "anyone will believe the output."
)


# ==================================================== the assistant harness

ASSISTANT_INTRO = (
    "The assistant is a grounding harness around a language model, not a model "
    "integration. Almost all of the engineering is in what reaches the model and "
    "what it is allowed to do with it. The model itself is replaceable and should "
    "be treated as such - see S7 and C-7."
)

ASSISTANT = [
    ["Capability", "What it does", "Requirement"],
    ["Briefing construction",
     "Every figure currently rendered - live market, period statistics, breadth, ownership, activity, insider trades, the register book of record, the scan findings and archetypes, the news window - is serialised to a compact structured briefing on each render.",
     "Deterministic: the same state must produce the same briefing. It is a pure function of the render, and testable as one."],
    ["Grounding",
     "The model answers only from the briefing. A figure not in it is reported as absent.",
     "Never estimate, never fill a gap from memory. A wrong figure here is worse than no figure."],
    ["Scoping by role",
     "The briefing is assembled for the caller. A user without register access gets a briefing with no register in it.",
     "Access control the assistant can be talked around is not access control - FR-32, N10."],
    ["Source separation",
     "Datasets that share a name are introduced distinctly, each stating what it is and what it is not.",
     "The exchange's ownership split and the per-holder register were both called 'the register' and the model answered a question about one using the other. Each section now cross-references the other."],
    ["Provenance handling",
     "Demonstration provenance is stated when asked and not volunteered otherwise.",
     "Volunteering it in every answer buries the finding; denying it under direct questioning is the failure that loses the room - R9, N2."],
    ["Caveat propagation",
     "Where a figure carries a caveat in the briefing - an approximation, a single-session period, a keyword-derived sentiment - the caveat travels with the answer.",
     "A number quoted without its caveat is a different number."],
    ["Cost control",
     "The briefing is placed first and does not change within a conversation, so provider-side context caching applies from the second turn onward.",
     "A deterministic token budget is a non-functional requirement, not an optimisation."],
    ["Conversation scope",
     "A bounded number of prior turns is resent; the briefing carries the facts.",
     "No memory across sessions. No retrieval outside the briefing."],
    ["Refusal behaviour",
     "Declines investment advice, recommendations and anything outside the rendered state.",
     "N3. The system describes what the data shows."],
    ["Language",
     "Answers in the language asked. Right-to-left layout detected per turn.",
     "Arabic must render correctly, not merely be accepted."],
    ["Voice input",
     "Browser-native speech recognition; the transcript lands in the input for correction before sending.",
     "No audio leaves the page. A misheard ticker must be correctable before it becomes a question."],
]
