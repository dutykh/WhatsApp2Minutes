"""
Author: Dr. Denys Dutykh (Khalifa University of Science and Technology, Abu Dhabi, UAE)
"""

import argparse
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, Optional, Tuple

from .env import load_env, get_env
from .utils import default_meeting_prefix_from_name


# Compile patterns for WhatsApp export formats
# 1) Dash style: 12/31/21, 9:00 PM - Name: Message
_PATTERN_DASH = re.compile(
    r"^(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}),\s*"
    r"(?P<time>\d{1,2}:\d{2}(?:\s?[APMapm]{2})?)\s*-\s*"
)

# 2) Bracket style: [12/31/21, 9:00 PM] Name: Message
_PATTERN_BRACKET = re.compile(
    r"^\[\s*(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}),\s*"
    r"(?P<time>\d{1,2}:\d{2}(?:\s?[APMapm]{2})?)\s*\]\s*"
)


@dataclass
class Options:
    input_path: str
    output_dir: str
    prefix: str = "KUMathSeminarCommitteeMeeting"
    encoding: str = "utf-8"
    date_order: str = "auto"  # one of: auto, dmy, mdy, ymd


def _try_parse_dt(date_str: str, time_str: str) -> Optional[datetime]:
    """Try parsing WhatsApp timestamp strings across common locales.

    Returns a datetime or None.
    """
    ts = f"{date_str}, {time_str}"
    fmts = [
        # Day-Month-Year
        "%d/%m/%y, %H:%M",
        "%d/%m/%y, %I:%M %p",
        "%d/%m/%Y, %H:%M",
        "%d/%m/%Y, %I:%M %p",
        "%d-%m-%y, %H:%M",
        "%d-%m-%y, %I:%M %p",
        "%d-%m-%Y, %H:%M",
        "%d-%m-%Y, %I:%M %p",
        # Month-Day-Year
        "%m/%d/%y, %H:%M",
        "%m/%d/%y, %I:%M %p",
        "%m/%d/%Y, %H:%M",
        "%m/%d/%Y, %I:%M %p",
        "%m-%d-%y, %H:%M",
        "%m-%d-%y, %I:%M %p",
        "%m-%d-%Y, %H:%M",
        "%m-%d-%Y, %I:%M %p",
        # Year-Month-Day
        "%Y/%m/%d, %H:%M",
        "%Y/%m/%d, %I:%M %p",
        "%Y-%m-%d, %H:%M",
        "%Y-%m-%d, %I:%M %p",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(ts, fmt)
        except ValueError:
            continue
    return None


def _extract_ts(line: str) -> Optional[Tuple[str, str]]:
    """If line starts a new WhatsApp message, return (date_str, time_str)."""
    m = _PATTERN_DASH.match(line)
    if m:
        return m.group("date"), m.group("time")
    m = _PATTERN_BRACKET.match(line)
    if m:
        return m.group("date"), m.group("time")
    return None


def _detect_slash_order(sample_dates: Iterable[str]) -> str:
    """Heuristically detect date order for dd/mm/yy vs mm/dd/yy.

    Returns 'dmy' or 'mdy'. If ambiguous, default to 'dmy'.
    """
    dmy_votes = 0
    mdy_votes = 0
    for ds in sample_dates:
        parts = re.split(r"[/-]", ds)
        if len(parts) != 3:
            continue
        a, b, c = parts
        try:
            a_i, b_i = int(a), int(b)
        except ValueError:
            continue
        # if first > 12, it's definitely day
        if a_i > 12 and b_i <= 12:
            dmy_votes += 1
        # if second > 12, it's definitely day as second -> m/d/y
        elif b_i > 12 and a_i <= 12:
            mdy_votes += 1
    if mdy_votes > dmy_votes:
        return "mdy"
    return "dmy"


def _normalize_date(date_str: str, preferred_order: str = "auto") -> Optional[str]:
    """Convert date string to YYYY-MM-DD using preferred order when ambiguous.

    Supports dates with '/' or '-' separators.
    """
    sep = "/" if "/" in date_str else "-"
    parts = date_str.split(sep)
    if len(parts) != 3:
        return None

    # Identify ymd by presence of 4-digit first part
    if len(parts[0]) == 4:
        y, m, d = parts
    else:
        # We need to choose between dmy and mdy
        if preferred_order not in {"auto", "dmy", "mdy"}:
            preferred_order = "auto"
        # Auto-detect using heuristic on the single value
        order = preferred_order
        if preferred_order == "auto":
            order = _detect_slash_order([date_str])
        if order == "mdy":
            m, d, y = parts
        else:
            d, m, y = parts

    # Normalize year to 4-digit
    try:
        yi = int(y)
        mi = int(m)
        di = int(d)
        if yi < 100:
            yi += 2000 if yi <= 68 else 1900
        return f"{yi:04d}-{mi:02d}-{di:02d}"
    except ValueError:
        return None


def split_file_by_day(
    input_path: str,
    output_dir: str,
    prefix: str = "KUMathSeminarCommitteeMeeting",
    encoding: str = "utf-8",
    date_order: str = "auto",
) -> Dict[str, int]:
    """Split a WhatsApp exported chat into one file per date.

    Returns a dict mapping YYYY-MM-DD -> line count written.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")

    raw_dir = os.path.join(output_dir, "raw")
    os.makedirs(raw_dir, exist_ok=True)

    # Accumulate per date to avoid many open handles; 1MB is fine.
    per_date_lines: Dict[str, list[str]] = defaultdict(list)

    current_date_norm: Optional[str] = None

    with open(input_path, "r", encoding=encoding, errors="ignore") as f:
        for line in f:
            if not line:
                continue
            ts = _extract_ts(line)
            if ts is not None:
                date_str, time_str = ts
                # try full datetime parse first (more reliable for ambiguous dates)
                dt = _try_parse_dt(date_str, time_str)
                if dt is not None:
                    current_date_norm = dt.strftime("%Y-%m-%d")
                else:
                    current_date_norm = _normalize_date(date_str, preferred_order=date_order)
                # If normalization failed, skip this line (rare)
                if current_date_norm is None:
                    continue
            # If we have not yet found a first valid message, skip preamble lines
            if current_date_norm is None:
                continue
            per_date_lines[current_date_norm].append(line)

    # Write out per-date files
    counts: Dict[str, int] = {}
    for date_key, lines in sorted(per_date_lines.items()):
        out_path = os.path.join(raw_dir, f"{prefix}-{date_key}.txt")
        with open(out_path, "w", encoding=encoding) as out:
            out.writelines(lines)
        counts[date_key] = len(lines)
    return counts


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Split a WhatsApp chat export into one file per date under output/raw."
        )
    )
    p.add_argument(
        "--input",
        "-i",
        dest="input_path",
        default=os.path.join("input", "ChatData.txt"),
        help="Path to WhatsApp chat export (text file).",
    )
    p.add_argument(
        "--output",
        "-o",
        dest="output_dir",
        default="output",
        help="Output folder (raw files go to <output>/raw).",
    )
    p.add_argument(
        "--prefix",
        dest="prefix",
        default=None,
        help=(
            "Filename prefix for per-day files (default derives from COMMITTEE_NAME)."
        ),
    )
    p.add_argument(
        "--encoding",
        dest="encoding",
        default="utf-8",
        help="Input/output file encoding.",
    )
    p.add_argument(
        "--date-order",
        dest="date_order",
        default="auto",
        choices=["auto", "dmy", "mdy", "ymd"],
        help=(
            "Date interpretation when ambiguous (auto tries to infer). "
            "Only used for slash/dash dates that are not clearly ymd."
        ),
    )
    return p


def main(argv: Optional[Iterable[str]] = None) -> int:
    # Load environment from .env/.env.local (non-intrusive)
    load_env()
    args = _build_arg_parser().parse_args(argv)
    opts = Options(
        input_path=args.input_path,
        output_dir=args.output_dir,
        prefix=(
            args.prefix
            if args.prefix is not None
            else _default_prefix_from_env()
        ),
        encoding=args.encoding,
        date_order=args.date_order,
    )
    counts = split_file_by_day(
        input_path=opts.input_path,
        output_dir=opts.output_dir,
        prefix=opts.prefix,
        encoding=opts.encoding,
        date_order=opts.date_order,
    )
    # Simple summary
    print(f"Wrote {len(counts)} daily files to {os.path.join(opts.output_dir, 'raw')}")
    for day, n in sorted(counts.items()):
        print(f"  {day}: {n} lines")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _default_prefix_from_env() -> str:
    name = get_env("COMMITTEE_NAME", "KU Math Seminar Committee") or "KU Math Seminar Committee"
    return default_meeting_prefix_from_name(name)
