"""CSV parsing + validation. Pure functions: no database, no filesystem layout."""
from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass, field


class CsvValidationError(Exception):
    """The file cannot be imported. ``problems`` holds user-readable reasons."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass
class ParsedCurve:
    frequencies: list[float]
    magnitudes: list[float]
    warnings: list[str] = field(default_factory=list)


_HEADER_RE = re.compile(r"^\s*(?P<name>[A-Za-z ]+?)\s*\[\s*(?P<unit>[^\]]*?)\s*\]\s*$")
MAX_REPORTED_ROW_PROBLEMS = 5


def _check_header(header: list[str], expected_freq_unit: str, expected_mag_unit: str) -> list[str]:
    problems: list[str] = []
    if len(header) < 2:
        return [f"Header must have two columns 'Frequency [{expected_freq_unit}],Magnitude [{expected_mag_unit}]', found {len(header)}"]
    for col, label, unit in ((header[0], "frequency", expected_freq_unit), (header[1], "magnitude", expected_mag_unit)):
        m = _HEADER_RE.match(col)
        if not m or not m["name"].lower().startswith(label[:4]):
            problems.append(f"Column '{col.strip()}' is not recognised as a {label} column")
        elif m["unit"].lower() != unit.lower():
            # Never silently reinterpret units: 15 [um] would otherwise be compared to 15 mm.
            problems.append(f"Incompatible {label} unit [{m['unit']}]; expected [{unit}]")
    if len(header) > 2:
        problems.append(f"Unexpected extra columns: {', '.join(h.strip() or '<blank>' for h in header[2:])}")
    return problems


def parse_curve_csv(raw: bytes, freq_unit: str = "Hz", mag_unit: str = "mm") -> ParsedCurve:
    """Parse a ``Frequency [Hz],Magnitude [mm]`` file.

    Fatal problems raise :class:`CsvValidationError`. Recoverable oddities
    (unsorted rows, blank lines) are returned as ``warnings``.
    """
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise CsvValidationError(["File is not valid UTF-8 text"]) from None
    if "\x00" in text:
        raise CsvValidationError(["File looks binary, not CSV text"])

    rows = list(csv.reader(io.StringIO(text)))
    # drop completely blank lines but remember it
    non_blank = [(i + 1, r) for i, r in enumerate(rows) if any(c.strip() for c in r)]
    warnings: list[str] = []
    if len(non_blank) != len(rows):
        warnings.append("Blank lines were ignored")
    if not non_blank:
        raise CsvValidationError(["File is empty"])

    _, header = non_blank[0]
    problems = _check_header(header, freq_unit, mag_unit)
    if problems:
        raise CsvValidationError(problems)

    freqs: list[float] = []
    mags: list[float] = []
    bad: list[str] = []
    n_bad = 0
    for line_no, row in non_blank[1:]:
        if len(row) != 2:
            n_bad += 1
            if len(bad) < MAX_REPORTED_ROW_PROBLEMS:
                bad.append(f"line {line_no}: expected 2 values, found {len(row)}")
            continue
        try:
            f, m = float(row[0]), float(row[1])
        except ValueError:
            n_bad += 1
            if len(bad) < MAX_REPORTED_ROW_PROBLEMS:
                bad.append(f"line {line_no}: non-numeric value ({row[0]!r}, {row[1]!r})")
            continue
        if not (math.isfinite(f) and math.isfinite(m)):
            n_bad += 1
            if len(bad) < MAX_REPORTED_ROW_PROBLEMS:
                bad.append(f"line {line_no}: NaN/infinite value")
            continue
        if f < 0:
            n_bad += 1
            if len(bad) < MAX_REPORTED_ROW_PROBLEMS:
                bad.append(f"line {line_no}: negative frequency {f}")
            continue
        if m < 0:
            n_bad += 1
            if len(bad) < MAX_REPORTED_ROW_PROBLEMS:
                bad.append(f"line {line_no}: negative magnitude {m} (magnitude is expected to be >= 0)")
            continue
        freqs.append(f)
        mags.append(m)

    if n_bad:
        more = f" (+{n_bad - len(bad)} more)" if n_bad > len(bad) else ""
        # An invalid row means we cannot know whether the dropped row held the peak,
        # so the whole file is rejected rather than partially imported.
        raise CsvValidationError([f"{n_bad} invalid row(s): " + "; ".join(bad) + more])
    if not freqs:
        raise CsvValidationError(["No data rows after the header"])

    if len(set(freqs)) != len(freqs):
        dup = sorted({f for f in freqs if freqs.count(f) > 1})[:5]
        raise CsvValidationError([f"Duplicate frequencies: {', '.join(str(d) for d in dup)}"])

    if any(b < a for a, b in zip(freqs, freqs[1:])):
        order = sorted(range(len(freqs)), key=lambda i: freqs[i])
        freqs = [freqs[i] for i in order]
        mags = [mags[i] for i in order]
        warnings.append("Rows were not sorted by frequency and have been sorted")

    return ParsedCurve(freqs, mags, warnings)
