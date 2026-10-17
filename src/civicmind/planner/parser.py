"""Deterministic question parser: text -> ``QuerySpec`` or ``PlanRefusal``. No model, no guessing.

Order of checks (the first failure refuses):

1. empty / too long; 2. prompt-injection patterns; 3. causal and predictive language;
4. domain (water, roads, waste, census) — none is out of scope, more than one is cross-domain;
5. unsupported operations and units; 6. domain-specific parsing.

The parser works from a **closed vocabulary**. For water, any word it does not know is refused
(``query.unrecognised_terms``): a ward name, for example, would otherwise be silently ignored
and the city total returned. For roads, the unknown words form the city phrase; it is matched
exactly against the edition's labels later (analytics), never here.

Every default the parser applies (for example n = 10) is recorded in ``assumptions``.

Coverage and "latest" (checked once the domain is known, before domain-specific parsing):

* Availability questions ("which months are available?", "latest edition of road data") are
  answered from the catalogue (``data_coverage``); no data value is read.
* A request for a *value* "now", "currently" or for "the latest month/edition" without naming
  the period is refused (``query.period_missing``): the newest local file is never silently
  treated as current. The response's coverage block names the latest trusted period.
"""

from __future__ import annotations

import re

from civicmind.planner.spec import PlanRefusal, QuerySpec

MAX_LENGTH = 400
#: Years after this are treated as future (predictive) questions. A fixed constant, not the
#: system clock, so the parser stays deterministic; update it deliberately each year.
LATEST_YEAR = 2026

MONTHS = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3, "apr": 4,
    "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7, "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9, "oct": 10, "october": 10, "nov": 11,
    "november": 11, "dec": 12, "december": 12,
}  # fmt: skip
MONTH_YEAR = re.compile(r"\b(" + "|".join(sorted(MONTHS, key=len, reverse=True)) + r")\b"
                        r"[\s,.-]*(20\d\d)\b", re.IGNORECASE)  # fmt: skip
YEAR = re.compile(r"\b(19\d\d|20\d\d)\b")
TOKEN = re.compile(r"[A-Za-z0-9]+")
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10,
}  # fmt: skip

INJECTION = [
    r"ignore (all |any |the |your )?(previous|prior|above|earlier)",
    r"\bdisregard\b",
    r"system prompt",
    r"\byou are now\b",
    r"\bact as\b",
    r"\bpretend\b",
    r"\bjailbreak",
    r"developer mode",
    r"\boverride\b",
    r"\bbypass\b",
    r"\b(execute|eval)\b",
    r"\bimport os\b",
    r"rm -rf",
    r"drop table",
    r"<\s*script",
    r"\b(api[ _-]?key|password|secret|token)s?\b",
    r"\b(un-?quarantine|promote|unrestrict)\b",
    r"\bmark\b.*\bas (trusted|accepted|promoted|validated)\b",
    r"\bchange (the )?(review|status|permission|decision)",
    r"\bpermitted_uses\b",
    r"\binstructions?\b",
]
CAUSAL = [
    r"\bwhy\b",
    r"\bcaus(e|es|ed|al|ing)\b",
    r"\bbecause\b",
    r"\bdue to\b",
    r"\b(effect|impact|influence)s? (of|on)\b",
    r"\bled to\b",
    r"\bresult(ed|s)? in\b",
    r"\battribut",
    r"\b(reduc|improv|worsen|prevent|mitigat)\w*",  # agency: did X reduce / improve Y
    r"\b(lowered|helped)\b",
    r"\b(enforcement|intervention|campaign|policy|policies)\b",
    r"\bresponsible for\b",
    r"\bexplain",
]
PREDICTIVE = [
    r"\bpredict",
    r"\bforecast",
    r"\bproject(ed|ion|ions)\b",
    r"\bwill\b",
    r"\bgoing to\b",
    r"\bnext (month|year|quarter)\b",
    r"\bfuture\b",
    r"\bexpected? to\b",
    r"\bestimate\b",
]
UNSUPPORTED_OPS = [
    r"\b(average|mean|median|trend|correlat\w*|regression|variance|std|deviation)\b",
    r"\bgrowth rate\b",
]
WATER_BAD_UNITS = [
    r"\bkilo ?litres?\b",
    r"\bkl\b",
    r"\bgallons?\b",
    r"\bcubic\b",
    r"\bm3\b",
    r"\btmc\b",
    r"\bper (capita|person|household|head)\b",
    r"\btonnes?\b",
    r"\blakh litres\b",
    r"\bmld\b",
]
#: Questions about which periods exist (answered from the catalogue, any period wording).
AVAILABILITY = [
    r"\b(available|availability|coverage)\b",
    r"\b(which|what) (months?|years?|editions?|periods?)\b",
]
#: "The latest month/edition": coverage, unless a value is asked for (then period_missing).
LATEST_PERIOD = [
    r"\b(latest|most recent|newest|earliest) (\w+ ){0,3}?"
    r"(month|year|edition|period|data|dataset)s?\b"
]
#: Relative time that must never be resolved to "the newest file".
CURRENT = [
    r"\b(current|currently|latest|most recent|newest|now|today|present|nowadays)\b",
    r"\b(this|last|past) (month|year)\b",
]
VALUE_WORDS = {
    "water": [r"\bconsum\w*", r"\bconnections?\b", r"\bml\b", r"\bmegalitres?\b",
              r"\busage\b", r"\bused\b", r"\blitres?\b", r"\bhow much\b"],
    "roads": [r"\bhow many\b", r"\bkilled\b", r"\bdeaths?\b", r"\bdied\b",
              r"\bfatalit\w*", r"\binjur\w*", r"\bgrievous\w*", r"\bminor\w*",
              r"\bover[\s-]?speed\w*", r"\bspeeding\b", r"\bdrunk\w*", r"\balcohol\b",
              r"\bwrong side\b", r"\bred light", r"\bmobile\b", r"\bothers?\b"],
}  # fmt: skip
ROAD_BAD_UNITS = [
    r"\bper (lakh|1,?00,?000|10,?000|capita|person|km|kilometre|vehicle)",
    r"\brate\b",
]

DOMAIN_TERMS = {
    "water": {
        "water", "consumption", "consumed", "bwssb", "megalitres", "ml", "litres", "connection",
        "connections",
    },
    "roads": {
        "accident", "accidents", "crash", "crashes", "killed", "deaths", "died",
        "fatalities", "injured", "injuries", "speeding", "overspeeding", "drunken", "drunk",
        "traffic", "road", "morth",
    },
    "waste": {"waste", "garbage", "msw", "swm", "refuse", "recycling", "recycled"},
    "census": {"population", "census", "demographic", "demographics", "literacy"},
}  # fmt: skip

COMMON = {
    "a", "an", "the", "what", "which", "who", "how", "many", "much", "was", "were", "is",
    "are", "did", "does", "do", "has", "have", "had", "in", "of", "for", "during", "on", "at",
    "by", "from", "to", "and", "with", "as", "be", "been", "that", "this", "its", "their",
    "there", "all", "any", "me", "show", "list", "tell", "give", "please", "find", "according",
    "data", "dataset", "number", "count", "amount", "value", "values", "figure", "reported",
    "report", "record", "recorded", "records", "published", "total", "overall", "altogether",
    "top", "highest", "lowest", "most", "least", "largest", "smallest", "biggest", "rank",
    "ranked", "ranking", "rankings", "month", "year", "edition", "india", "s", "it", "each",
    "per", "between", "than", "compared", "compare", "comparison", "vs", "versus", "against",
    "change", "changed", "difference", "differ", "increase", "increased", "decrease",
    "decreased", "rise", "fall", "grow", "grew", "volatile", "volatility", "flag", "flagged",
    "flags", "under", "where", "when", "first", "single", "only",
}  # fmt: skip
WATER_VOCAB = COMMON | DOMAIN_TERMS["water"] | {
    "connection", "connections", "day", "daily", "city", "citywide", "wide", "bengaluru",
    "bangalore", "use", "used", "usage", "supplied", "row", "rows", "entry", "entries",
    "ward", "wards", "unique", "distinct", "board", "sewerage", "supply", "intensity",
    "consume", "megalitre", "litre", "across",
}  # fmt: skip
ROAD_VOCAB = COMMON | DOMAIN_TERMS["roads"] | {
    "persons", "people", "over", "driving", "alcohol", "drug", "drugs", "consumption",
    "wrong", "side", "jumping", "red", "light", "lights", "signal", "use", "mobile", "phone",
    "phones", "others", "other", "violation", "violations", "grievous", "grievously",
    "seriously", "minor", "minorly", "injury", "share", "percent", "percentage",
    "proportion", "cities", "city", "plus", "million", "category", "type", "rule", "rules",
    "involving", "related",
}  # fmt: skip
ROAD_KNOWN = ROAD_VOCAB | set(MONTHS) | set(NUMBER_WORDS)

ROAD_CATEGORIES = {
    "over_speeding": [r"\bover[\s-]?speed\w*", r"\bspeeding\b"],
    "drunken_driving": [r"\bdrunk\w*", r"\balcohol\b"],
    "wrong_side": [r"\bwrong side\b"],
    "red_light": [r"\bred light", r"\bjumping\b", r"\bsignal\b"],
    "mobile_phone": [r"\bmobile\b", r"\bphones?\b"],
    "others": [r"\bothers?\b(?! than)"],
}
ROAD_METRICS = {
    "accidents": [r"\baccidents?\b", r"\bcrash(es)?\b"],
    "killed": [r"\bkilled\b", r"\bdeaths?\b", r"\bdied\b", r"\bfatalit\w*"],
    "grievous": [r"\bgrievous\w*", r"\bseriously\b"],
    "minor": [r"\bminor\w*"],
    "total_injured": [r"\binjur(ed|ies|y)\b"],
}


def _any(patterns, text: str) -> bool:
    return any(re.search(p, text) for p in patterns)


def _refuse(code: str, reason: str, details=None) -> PlanRefusal:
    return PlanRefusal(code=code, reason=reason, details=details)


def _periods(question: str) -> tuple[list[str], list[str]]:
    """(month periods 'YYYY-MM' in order, bare years not part of a month)."""
    months, spans = [], []
    for m in MONTH_YEAR.finditer(question):
        months.append(f"{m.group(2)}-{MONTHS[m.group(1).lower()]:02d}")
        spans.append(m.span())
    years = [
        y.group(1)
        for y in YEAR.finditer(question)
        if not any(a <= y.start() < b for a, b in spans)
    ]
    return months, years


def _top_n(lower: str) -> int | None:
    m = re.search(r"\btop\s+(\d{1,3}|" + "|".join(NUMBER_WORDS) + r")\b", lower)
    m = m or re.search(
        r"\b(\d{1,3}|" + "|".join(NUMBER_WORDS) + r")\s+(published\s+)?"
        r"(rows|wards|entries|cities|records)\b",
        lower,
    )
    if not m:
        return None
    word = m.group(1)
    return NUMBER_WORDS.get(word) or int(word)


def _stray_numbers(text: str, lower: str) -> list[str]:
    """Numbers that are neither a period's year nor the ranking size (e.g. a ward number)."""
    allowed = {m.group(2) for m in MONTH_YEAR.finditer(text)} | set(YEAR.findall(text))
    n = _top_n(lower)
    if n is not None:
        allowed.add(str(n))
    return sorted({t for t in re.findall(r"\b\d+\b", text) if t not in allowed})


def _domain(tokens: set[str], lower: str) -> set[str]:
    found = {d for d, terms in DOMAIN_TERMS.items() if tokens & terms}
    water_only = DOMAIN_TERMS["water"] - {"consumption"}
    if "roads" in found and "water" in found and not tokens & water_only:
        found.discard("water")  # "alcohol consumption" is a road category, not water
    if _any([r"\bcollection efficiency\b", r"\bsolid waste\b"], lower):
        found.add("waste")
    return found


def detect_domain(question: str) -> str | None:
    """The single domain a question is about (water, roads, waste, census), else None.

    Used only to describe catalogue coverage alongside a refusal; never to answer.
    """
    text = (question or "").strip()
    if not text or len(text) > MAX_LENGTH:
        return None
    lower = " ".join(text.lower().split())
    domains = _domain({t.lower() for t in TOKEN.findall(text)}, lower)
    return domains.pop() if len(domains) == 1 else None


def _coverage_or_current(domain: str, text: str, lower: str) -> QuerySpec | PlanRefusal | None:
    """Availability questions -> data_coverage; an unnamed 'current/latest' value -> refusal."""
    if _any(AVAILABILITY, lower):
        return QuerySpec(intent="data_coverage", domain=domain, periods=(), question=text)
    named = bool(MONTH_YEAR.search(text)) if domain == "water" else bool(YEAR.search(text))
    if named:
        return None
    asks_value = _any(VALUE_WORDS[domain], lower)
    if _any(LATEST_PERIOD, lower) and not asks_value:
        return QuerySpec(intent="data_coverage", domain=domain, periods=(), question=text)
    if _any(CURRENT, lower) or _any(LATEST_PERIOD, lower):
        unit = "month and year (e.g. March 2026)" if domain == "water" else "edition year"
        return _refuse(
            "query.period_missing",
            f"Name the {unit}. 'Current' or 'latest' is never resolved to the newest local "
            "file: these are static published files, not live data. The coverage section "
            "lists the latest trusted period.",
        )
    return None


def parse(question: str) -> QuerySpec | PlanRefusal:
    text = (question or "").strip()
    if not text:
        return _refuse("query.empty", "The question is empty.")
    if len(text) > MAX_LENGTH:
        return _refuse("query.too_long", f"Questions are limited to {MAX_LENGTH} characters.")
    lower = " ".join(text.lower().split())
    if _any(INJECTION, lower):
        return _refuse(
            "query.prompt_injection",
            "The question contains instructions or commands. Only questions about the data are "
            "answered; text in a question is never executed or used to change settings.",
        )
    if _any(CAUSAL, lower):
        return _refuse(
            "query.causal",
            "Causal questions (why, effect, impact, did X reduce Y) cannot be substantiated by "
            "these descriptive tables, which record outcomes without causes.",
        )
    if _any(PREDICTIVE, lower) or any(int(y) > LATEST_YEAR for y in YEAR.findall(lower)):
        return _refuse(
            "query.predictive",
            "Forecasts and future periods are not supported; no forecasting method is approved.",
        )
    tokens = [t.lower() for t in TOKEN.findall(text)]
    domains = _domain(set(tokens), lower)
    if not domains:
        return _refuse(
            "query.out_of_scope",
            "Only BWSSB monthly water consumption and MoRTH million-plus city traffic-violation "
            "tables are covered.",
        )
    if len(domains) > 1:
        return _refuse(
            "query.cross_domain",
            f"The question mixes {sorted(domains)}; datasets from different domains are never "
            "combined (no identifier authority links them).",
        )
    domain = domains.pop()
    if domain in ("waste", "census"):
        return QuerySpec(intent="dataset_family", domain=domain, periods=(), question=text)
    early = _coverage_or_current(domain, text, lower)
    if early is not None:
        return early
    if _any(UNSUPPORTED_OPS, lower):
        return _refuse(
            "query.unsupported_operation",
            "Averages, trends and correlations are not implemented; only totals, rankings, "
            "a two-month city-total change and city lookups are available.",
        )
    if domain == "water":
        return _parse_water(text, lower, tokens)
    return _parse_roads(text, lower, tokens)


# --- water --------------------------------------------------------------------------------


def _parse_water(text: str, lower: str, tokens: list[str]) -> QuerySpec | PlanRefusal:
    if _any(WATER_BAD_UNITS, lower):
        return _refuse(
            "query.unit_unsupported",
            "Water answers are given only in megalitres (ML), connections, or litres per "
            "connection per day, as published or derived by a tested formula.",
        )
    months, years = _periods(text)
    known = WATER_VOCAB | set(MONTHS) | set(NUMBER_WORDS)
    unknown = sorted({t for t in tokens if t not in known and not t.isdigit()})
    if unknown:
        return _refuse(
            "query.unrecognised_terms",
            "The question contains terms this planner does not recognise. Ward-level lookups "
            "and named places are not supported for water; nothing is guessed.",
            unknown,
        )
    if re.search(r"\bward\s*(no\.?|number|#)?\s*\d+", lower):
        return _refuse(
            "query.unsupported_operation",
            "Single-ward lookups are not supported: ward numbers repeat and no ward-identifier "
            "authority is recorded. Ask for a city total or a ranking of published rows.",
        )
    stray = _stray_numbers(text, lower)
    if stray:
        return _refuse(
            "query.unrecognised_terms",
            "The question contains numbers that are neither a period nor a ranking size.",
            stray,
        )
    lpcd = bool(re.search(r"\bper connection\b", lower)) and bool(
        re.search(r"\b(per day|daily|a day|each day)\b", lower)
    )
    if not lpcd and _any([r"\blitres?\b", r"\blitre\b"], lower):
        return _refuse(
            "query.unit_unsupported",
            "Litres are only available as litres per connection per day; totals are in ML.",
        )
    wants_conn = bool(re.search(r"\bconnections?\b", lower)) and not lpcd
    wants_ml = _any([r"\bconsum\w*", r"\bml\b", r"\bmegalitres?\b", r"\busage\b", r"\bused\b",
                     r"\bhow much water\b"], lower)  # fmt: skip
    if lpcd:
        measure = "litres_per_connection_per_day"
    elif wants_conn and wants_ml:
        return _refuse(
            "query.metric_ambiguous", "Ask about consumption or connections, not both at once."
        )
    elif wants_conn:
        measure = "connections"
    elif wants_ml:
        measure = "consumption_ml"
    else:
        return _refuse(
            "query.metric_missing",
            "Say which measure: consumption (ML), connections, or litres per connection per day.",
        )
    if not months:
        return _refuse(
            "query.period_ambiguous" if years else "query.period_missing",
            "Water data is monthly: name the month and year (e.g. August 2025).",
        )
    ranking = _any([r"\b(top|highest|lowest|most|least|largest|smallest|biggest|rank\w*)\b"],
                   lower)  # fmt: skip
    changing = _any([r"\b(change[ds]?|difference|differ|increase[ds]?|decrease[ds]?|rise|fall|"
                     r"grow|grew)\b", r"\bfrom\b.*\bto\b"], lower)  # fmt: skip
    versus = _any([r"\b(against|versus|vs|volatil\w*|flag\w*)\b", r"\bcompared (with|to)\b"],
                  lower)  # fmt: skip
    assumptions: list[str] = []
    if ranking:
        if changing:
            return _refuse(
                "query.unsupported_operation",
                "Row-level month-to-month changes are not supported (rows are not matched "
                "across months); ask for the city-total change instead.",
            )
        if len(months) > 1 and not versus:
            return _refuse(
                "query.period_ambiguous",
                "A ranking covers one month; name one month, or ask to flag it against another.",
            )
        if len(months) > 1 and measure != "litres_per_connection_per_day":
            return _refuse(
                "query.unsupported_operation",
                "Reference months are only used to flag litres-per-connection-per-day rankings.",
            )
        rows = _any([r"\b(rows?|entr(y|ies)|records)\b"], lower)
        n = _top_n(lower)
        if n is None:
            singular = re.search(r"\bwhich (published )?(row|ward|entry|record)\b", lower)
            n = 1 if singular else 10
            assumptions.append(f"n = {n} ({'singular question' if singular else 'default'})")
        if not rows:
            assumptions.append(
                "Interpreted as a ranking of unique wards (no 'rows' wording); refused if "
                "ward numbers repeat."
            )
        order = "asc" if _any([r"\b(lowest|least|smallest)\b"], lower) else "desc"
        return QuerySpec(
            intent="water_rank_rows" if rows else "water_rank_wards",
            domain="water",
            periods=(months[0],),
            reference_periods=tuple(months[1:]),
            params={"measure": measure, "n": n, "order": order},
            assumptions=tuple(assumptions),
            question=text,
        )
    # Below this point the answer is a CITY TOTAL. Any reference to a ward or a row (other than
    # the explicit "all wards") would make it the answer to a different question, e.g. "the
    # consumption of the ward", "each ward", "per ward": refuse rather than return the total.
    scoped = re.sub(r"\b(across\s+)?all\s+(the\s+)?(published\s+)?wards\b", " ", lower)
    if re.search(r"\b(wards?|rows?|entr(y|ies)|records|unique|distinct)\b", scoped):
        return _refuse(
            "query.unsupported_operation",
            "Only city totals are available for this question type; per-ward, single-ward and "
            "per-row figures are not supported. Ask for a ranking of published rows instead.",
        )
    if changing or (versus and len(months) > 1):
        if len(months) != 2:
            return _refuse(
                "query.period_ambiguous" if len(months) > 2 else "query.period_missing",
                "A change needs exactly two months (earlier first).",
            )
        if measure == "litres_per_connection_per_day":
            return _refuse(
                "query.unsupported_operation",
                "Only city totals of consumption or connections can be compared between months.",
            )
        return QuerySpec(
            intent="water_month_change",
            domain="water",
            periods=tuple(months),
            params={"measure": measure},
            question=text,
        )
    if len(months) > 1:
        return _refuse(
            "query.period_ambiguous", "A total covers one month; name a single month and year."
        )
    if measure == "litres_per_connection_per_day":
        return _refuse(
            "query.unsupported_operation",
            "A city-wide litres-per-connection-per-day figure is not implemented; ask for a "
            "ranking of published rows instead.",
        )
    return QuerySpec(
        intent="water_total",
        domain="water",
        periods=(months[0],),
        params={"measure": measure},
        assumptions=("City total of all published rows (repeated ward numbers included).",),
        question=text,
    )


# --- roads --------------------------------------------------------------------------------


def _one_of(table: dict[str, list[str]], lower: str) -> list[str]:
    return [key for key, patterns in table.items() if _any(patterns, lower)]


def _city_phrases(text: str) -> list[str]:
    """Maximal runs of words outside the road vocabulary, as written (exact text)."""
    phrases, current = [], []
    for m in TOKEN.finditer(text):
        word = m.group(0)
        known = word.lower() in ROAD_KNOWN or word.isdigit()
        if known:
            if current:
                phrases.append(current)
                current = []
        else:
            current.append(m)
    if current:
        phrases.append(current)
    out = []
    for group in phrases:
        start, end = group[0].start(), group[-1].end()
        if end < len(text) and text[end] == ")":
            end += 1  # keep a closing parenthesis, e.g. "Allahabad (Prayagraj)"
        out.append(text[start:end])
    return out


def _parse_roads(text: str, lower: str, tokens: list[str]) -> QuerySpec | PlanRefusal:
    if _any(ROAD_BAD_UNITS, lower):
        return _refuse(
            "query.unit_unsupported",
            "Traffic answers are published counts and a share of the published Total row; rates "
            "per population, vehicle or road length are not in these tables.",
        )
    _, years = _periods(text)
    years = sorted(set(years))
    stray = _stray_numbers(text, lower)
    if stray:
        return _refuse(
            "query.unrecognised_terms",
            "The question contains numbers that are neither an edition year nor a ranking size.",
            stray,
        )
    if not years:
        return _refuse(
            "query.period_missing",
            "Name the edition year (e.g. 2019 or 2024).",
        )
    if len(years) > 1:
        return _refuse(
            "query.cross_edition",
            "Comparisons across MoRTH editions are not supported: column names and city labels "
            "differ between editions and no cited crosswalk is approved.",
            years,
        )
    categories = _one_of(ROAD_CATEGORIES, lower)
    metrics = _one_of(ROAD_METRICS, lower)
    if "grievous" in metrics or "minor" in metrics:
        metrics = [m for m in metrics if m != "total_injured"]
    if len(metrics) > 1 and "accidents" in metrics:
        metrics = [m for m in metrics if m != "accidents"]  # "killed in accidents" -> killed
    if not categories:
        return _refuse(
            "query.metric_missing",
            "Name the traffic-violation category (over-speeding, drunken driving, wrong side, "
            "red light, mobile phone, others); these tables have no all-violation total.",
        )
    if len(categories) > 1:
        return _refuse("query.metric_ambiguous", "Ask about one violation category.", categories)
    if not metrics:
        return _refuse(
            "query.metric_missing",
            "Say which count: accidents, persons killed, grievously injured, minor injury or "
            "total injured.",
        )
    if len(metrics) > 1:
        return _refuse("query.metric_ambiguous", "Ask about one count at a time.", metrics)
    ranking = _any([r"\b(top|highest|lowest|most|least|largest|rank\w*)\b",
                    r"\bwhich cit(y|ies)\b"], lower)  # fmt: skip
    cities = _city_phrases(text)
    params = {"category": categories[0], "metric": metrics[0]}
    if ranking:
        if _any([r"\b(lowest|least|smallest|fewest)\b"], lower):
            return _refuse(
                "query.unsupported_operation", "Only highest-first city rankings are implemented."
            )
        if cities:
            return _refuse(
                "query.unrecognised_terms",
                "A city ranking takes no city name; unrecognised terms were found.",
                cities,
            )
        n = _top_n(lower)
        assumptions = []
        if n is None:
            singular = re.search(r"\bwhich city\b", lower)
            n = 1 if singular else 10
            assumptions.append(f"n = {n} ({'singular question' if singular else 'default'})")
        return QuerySpec(
            intent="road_top_cities",
            domain="roads",
            periods=(years[0],),
            params={**params, "n": n},
            assumptions=tuple(assumptions),
            question=text,
        )
    comparing = _any([r"\b(compare[ds]?|comparison|versus|vs|between|difference|differ)\b"],
                     lower)  # fmt: skip
    if comparing and (len(cities) > 2 or any("," in c for c in cities)):
        return _refuse("query.entity_ambiguous", "Compare exactly two cities at a time.", cities)
    if comparing and len(cities) == 2:
        if cities[0].strip() == cities[1].strip():
            return _refuse("query.entity_ambiguous", "Name two different cities.", cities)
        return QuerySpec(
            intent="road_compare_cities",
            domain="roads",
            periods=(years[0],),
            params={**params, "cities": tuple(cities)},
            assumptions=(
                "City labels matched exactly as written (no alias table).",
                "Both cities from the same edition; difference = first city minus second.",
            ),
            question=text,
        )
    if not cities:
        return _refuse(
            "query.entity_missing", "Name one million-plus city, or ask for a ranking of cities."
        )
    if len(cities) > 1:
        return _refuse(
            "query.entity_ambiguous",
            "More than one place name was found; ask about one city at a time.",
            cities,
        )
    return QuerySpec(
        intent="road_city_value",
        domain="roads",
        periods=(years[0],),
        params={**params, "city": cities[0]},
        assumptions=("City label matched exactly as written (no alias table).",),
        question=text,
    )


__all__ = ["detect_domain", "parse"]
