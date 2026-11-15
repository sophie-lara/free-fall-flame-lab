"""Exact-value lookup of reviewed table rows named by the numbers in a question.

Rules (agreed with the reviewer):
- rows are returned only when the question gives two or more numbers and every one of
  them matches a different value in the same row; partial matches return nothing;
- matching is exact after normalizing number format (0.5 equals 0.50);
- a percentage may match a mole fraction (21% ↔ 0.21) and vice versa, and every such
  conversion is reported with the match;
- a hint word next to a number (atm, oxygen, CO2, flow, …) restricts which column it
  may match; species named in the question (CO2, He, methanol, …) must appear in the
  row's fuel/suppressant/diluent/agent columns when the row has such columns.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

NUMBER = re.compile(r"(?<![\w.\-])(\d+(?:\.\d+)?)(\s*%)?(?![\d.]|-\d)")
WORD = re.compile(r"[A-Za-z][A-Za-z0-9/]*|\d+(?:\.\d+)?%?")

# hint word -> column categories it may refer to
HINTS: dict[str, set[str]] = {
    "atm": {"pressure"},
    "pressure": {"pressure"},
    "kpa": {"pressure"},
    "p": {"pressure"},
    "o2": {"oxygen"},
    "oxygen": {"oxygen"},
    "xo2": {"oxygen"},
    "co2": {"suppressant", "co2"},
    "xco2": {"suppressant"},
    "he": {"suppressant", "inert"},
    "helium": {"suppressant", "inert"},
    "xhe": {"suppressant"},
    "sf6": {"suppressant"},
    "xsf6": {"suppressant"},
    "suppressant": {"suppressant"},
    "flow": {"flow"},
    "cm/s": {"flow"},
    "velocity": {"flow"},
    "diameter": {"diameter"},
    "d0": {"diameter"},
    "mm": {"diameter", "thickness"},
    "thickness": {"thickness"},
    "co": {"co"},
    "ppm": {"co"},
}
SPECIES = {
    "co2": "co2",
    "he": "he",
    "helium": "he",
    "sf6": "sf6",
    "n2": "n2",
    "nitrogen": "n2",
    "xe": "xe",
    "xenon": "xe",
    "heptane": "c7h16",
    "c7h16": "c7h16",
    "methanol": "ch3oh",
    "ch3oh": "ch3oh",
}
SPECIES_FIELDS = re.compile(r"fuel|suppressant|diluent|agent|inert", re.I)
FRACTION_CATEGORIES = {"oxygen", "suppressant", "co2", "inert"}


def category(field: str, label: str) -> set[str]:
    text = f"{field} {label}".lower()
    found: set[str] = set()
    if "pressure" in text or "(atm)" in text:
        found.add("pressure")
    if re.search(r"oxygen|\bxo2\b|\bo2\b|initial_oxygen|final_oxygen", text):
        found.add("oxygen")
    if "suppressant" in text or re.search(r"\bx(co2|he|sf6)\b", text):
        found.add("suppressant")
    if re.search(r"co2", text) and "suppressant" not in text:
        found.add("co2")
    if re.search(r"(^|_)co($|_|\b)|\bco \(ppm\)", text):
        found.add("co")
    if "flow" in text:
        found.add("flow")
    if "diameter" in text:
        found.add("diameter")
    if "thickness" in text:
        found.add("thickness")
    if "inert" in text:
        found.add("inert")
    return found


def _decimal(text: str) -> Decimal | None:
    try:
        return Decimal(text).normalize()
    except InvalidOperation:
        return None


def _value_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return _decimal(repr(value))
    if isinstance(value, str) and re.fullmatch(r"-?\d+(?:\.\d+)?", value.strip()):
        return _decimal(value.strip())
    return None


# Units follow the number they qualify ("0.85 atm"); quantity words may precede or follow it
# ("oxygen 0.25", "0.25 oxygen"). A hint never reaches across another number.
# Species words only qualify a number before them ("0.70 He"); "He 0.24" names a row.
UNIT_WORDS = {"atm", "kpa", "mm", "cm/s", "ppm", "co2", "he", "helium", "sf6"}


def _is_number(word: str) -> bool:
    return bool(re.fullmatch(r"\d+(?:\.\d+)?%?", word))


def _owner(words: list[str], hint: int) -> int | None:
    """The number a hint word belongs to: the closest one; on a tie, the one before it."""
    best: tuple[int, int] | None = None
    for i, w in enumerate(words):
        if _is_number(w):
            key = (abs(i - hint), 0 if i < hint else 1)
            if best is None or key < best:
                best, owner = key, i
    return owner if best is not None else None


def _nearest_hint(words: list[str], position: int) -> set[str]:
    for distance in (1, 2):
        for step in (1, -1):
            i = position + step * distance
            if not 0 <= i < len(words):
                continue
            between = words[min(i, position) + 1 : max(i, position)]
            if any(_is_number(w) for w in between) or _is_number(words[i]):
                continue
            word = words[i]
            if (
                word in HINTS
                and (step == 1 or word not in UNIT_WORDS)
                and _owner(words, i) == position
            ):
                return HINTS[word]
    return set()


def parse_query(question: str) -> tuple[list[dict[str, Any]], set[str]]:
    """Numbers with their nearby hint categories, and species named in the question."""
    words = [w.lower() for w in WORD.findall(question)]
    species = {SPECIES[w] for w in words if w in SPECIES}
    numbers = []
    for match in NUMBER.finditer(question):
        token = match.group(1)
        position = next((i for i, w in enumerate(words) if w.rstrip("%") == token.lower()), None)
        hints: set[str] = set()
        if position is not None:
            hints = _nearest_hint(words, position)
        value = _decimal(token)
        if value is not None:
            numbers.append(
                {"text": token, "value": value, "percent": bool(match.group(2)), "hints": hints}
            )
    return numbers, species


def _candidates(number: dict[str, Any], values: list[dict[str, Any]]) -> list[tuple[int, str]]:
    """(value index, conversion note or '') for row values this number may match."""
    found = []
    for index, v in enumerate(values):
        target = _value_decimal(v["value"])
        if target is None:
            continue
        cats = category(v["field"], v["label"] or "")
        if number["hints"] and not (number["hints"] & cats):
            continue
        unit = (v.get("unit") or "").lower()
        is_percent_column = "%" in unit
        q = number["value"]
        if number["percent"]:
            if is_percent_column and q == target:
                found.append((index, ""))
            elif not is_percent_column and cats & FRACTION_CATEGORIES:
                if (q / 100).normalize() == target:
                    found.append(
                        (
                            index,
                            f"{number['text']}% matched as mole fraction {target} ({v['field']})",
                        )
                    )
            continue
        if q == target:
            found.append((index, ""))
        elif is_percent_column and q < 1 and (q * 100).normalize() == target:
            found.append(
                (
                    index,
                    f"{number['text']} matched as {target}% ({v['field']}, converted from "
                    "a fraction)",
                )
            )
    return found


def _assign(
    options: list[list[tuple[int, str]]], used: frozenset[int] = frozenset()
) -> list[tuple[int, str]] | None:
    if not options:
        return []
    for index, note in options[0]:
        if index in used:
            continue
        rest = _assign(options[1:], used | {index})
        if rest is not None:
            return [(index, note), *rest]
    return None


def _species_ok(species: set[str], values: list[dict[str, Any]]) -> bool:
    # Field names only: a column labelled "Fuel Sample Material" is a material, not a fuel.
    columns = [v for v in values if SPECIES_FIELDS.search(str(v["field"]))]
    if not species or not columns:
        return True
    present = set()
    for v in columns:
        text = re.sub(r"[^a-z0-9]", "", str(v["value"]).lower())
        present |= {s for s in species if s in text}
    return bool(present)


def match_rows(question: str, rows: list[dict[str, Any]], limit: int = 20) -> list[dict[str, Any]]:
    numbers, species = parse_query(question)
    if len(numbers) < 2:
        return []
    matches = []
    for row in rows:
        values = row["values"]
        if not _species_ok(species, values):
            continue
        assignment = _assign([_candidates(n, values) for n in numbers])
        if assignment is None:
            continue
        matched = [
            {
                "query": n["text"] + ("%" if n["percent"] else ""),
                "field": values[i]["field"],
                "value": values[i]["value"],
                "conversion": note or None,
            }
            for n, (i, note) in zip(numbers, assignment, strict=True)
        ]
        matches.append({**row, "match": matched})
    return matches[:limit]
