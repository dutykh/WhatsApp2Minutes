"""
Author: Dr. Denys Dutykh (Khalifa University of Science and Technology, Abu Dhabi, UAE)
"""

import argparse
import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timezone
from glob import glob
from statistics import mean
from typing import Iterable, Optional

from .env import load_env, get_env


# Recognize WhatsApp header lines (same styles as in parser/transcriber)
_PATTERN_DASH = re.compile(
    r"^(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}),\s*"
    r"(?P<time>\d{1,2}:\d{2}(?:\s?[APMapm]{2})?)\s*-\s*"
)
_PATTERN_BRACKET = re.compile(
    r"^\[\s*(?P<date>\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}[/-]\d{1,2}[/-]\d{1,2}),\s*"
    r"(?P<time>\d{1,2}:\d{2}(?:\s?[APMapm]{2})?)\s*\]\s*"
)


def _iter_header_lines(lines: Iterable[str]):
    for line in lines:
        if _PATTERN_DASH.match(line) or _PATTERN_BRACKET.match(line):
            yield line.rstrip("\n")


def _extract_name_and_time(line: str):
    m = _PATTERN_DASH.match(line) or _PATTERN_BRACKET.match(line)
    if not m:
        return None, None
    prefix_len = m.end()
    rest = line[prefix_len:]
    name = None
    if ':' in rest:
        name = rest.split(':', 1)[0].strip()
        name = re.sub(r"\s+(created|added|removed).*", "", name)
    return name or None, m.group('time')


def _minutes_of_day(time_str: str) -> Optional[int]:
    for fmt in ("%H:%M", "%I:%M %p", "%I:%M%p"):
        try:
            t = datetime.strptime(time_str.strip(), fmt)
            return t.hour * 60 + t.minute
        except ValueError:
            continue
    return None


def _estimate_meeting_time(header_lines: list[str]) -> Optional[str]:
    minutes: list[int] = []
    for line in header_lines:
        _, t = _extract_name_and_time(line)
        if t is None:
            continue
        m = _minutes_of_day(t)
        if m is not None:
            minutes.append(m)
    if not minutes:
        return None
    bin_size = 15
    bins = Counter((m // bin_size) for m in minutes)
    best_bin, _ = max(bins.items(), key=lambda kv: kv[1])
    center_min = best_bin * bin_size + bin_size // 2
    h = center_min // 60
    mm = center_min % 60
    return f"{h:02d}:{mm:02d}"


def _collect_participants(header_lines: list[str]) -> list[str]:
    names = []
    for line in header_lines:
        n, _ = _extract_name_and_time(line)
        if n:
            names.append(n)
    seen = set()
    uniq = []
    for n in names:
        if n not in seen:
            uniq.append(n)
            seen.add(n)
    return uniq


def _sanitize_date_from_filename(path: str) -> Optional[date]:
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1), "%Y-%m-%d").date()
    except ValueError:
        return None


@dataclass
class DailyStat:
    meeting_date: date
    message_count: int
    participant_count: int
    meeting_time: Optional[str]


def compute_stats(input_dir: str) -> dict:
    files = sorted(glob(os.path.join(input_dir, "*.txt")))
    if not files:
        raise FileNotFoundError(f"No raw files found under {input_dir}")

    daily: list[DailyStat] = []
    times_counter: Counter[str] = Counter()
    weekday_counter: Counter[int] = Counter()
    month_meetings: Counter[str] = Counter()

    for path in files:
        d = _sanitize_date_from_filename(path)
        if d is None:
            continue
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        headers = list(_iter_header_lines(text.splitlines()))
        msg_count = len(headers)
        participants = _collect_participants(headers)
        t = _estimate_meeting_time(headers)
        if t:
            times_counter[t] += 1
        weekday_counter[d.weekday()] += 1
        month_meetings[d.strftime("%Y-%m")] += 1
        daily.append(DailyStat(meeting_date=d, message_count=msg_count, participant_count=len(participants), meeting_time=t))

    if not daily:
        raise RuntimeError("No parsable daily stats were found.")

    daily.sort(key=lambda x: x.meeting_date)
    first = daily[0].meeting_date
    last = daily[-1].meeting_date
    today = datetime.now(timezone.utc).date()
    num_meetings = len(daily)
    total_days_running = (today - first).days + 1
    span_days = max(0, (last - first).days)
    avg_gap_days = (span_days / (num_meetings - 1)) if num_meetings > 1 else None
    avg_attendance = mean([d.participant_count for d in daily]) if daily else 0.0
    avg_msgs = mean([d.message_count for d in daily]) if daily else 0.0
    most_common_time = times_counter.most_common(1)[0][0] if times_counter else None
    most_active_weekday_idx, _ = max(weekday_counter.items(), key=lambda kv: kv[1])
    weekday_name = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][most_active_weekday_idx]
    busiest_month, _ = max(month_meetings.items(), key=lambda kv: kv[1])
    top_attendance = max(daily, key=lambda d: d.participant_count)

    return {
        "first_meeting": first,
        "last_meeting": last,
        "today": today,
        "days_running": total_days_running,
        "meetings_count": num_meetings,
        "avg_gap_days": avg_gap_days,
        "avg_attendance": avg_attendance,
        "avg_messages": avg_msgs,
        "popular_meeting_time": most_common_time,
        "popular_weekday": weekday_name,
        "busiest_month": busiest_month,
        "top_attendance_day": top_attendance.meeting_date,
        "top_attendance_count": top_attendance.participant_count,
    }


def _format_stats_text(stats: dict, committee_name: str) -> str:
    parts: list[str] = []
    parts.append(f"Committee vitality report for {committee_name} (a.k.a. we do things):")
    parts.append("")
    parts.append(f"- First recorded meeting: {stats['first_meeting']:%Y-%m-%d}")
    parts.append(f"- Latest recorded meeting: {stats['last_meeting']:%Y-%m-%d}")
    parts.append(f"- Committee age: {stats['days_running']} days and counting")
    parts.append(f"- Total meetings: {stats['meetings_count']}")
    if stats.get("avg_gap_days") is not None:
        parts.append(f"- On average: one meeting every {stats['avg_gap_days']:.2f} days")
    if stats.get("avg_attendance") is not None:
        parts.append(f"- Average attendance: {stats['avg_attendance']:.1f} people per meeting")
    if stats.get("avg_messages") is not None:
        parts.append(f"- Average chatter: {stats['avg_messages']:.1f} messages per meeting")
    if stats.get("popular_meeting_time"):
        parts.append(f"- Preferred rendezvous: around {stats['popular_meeting_time']} (coffee optional)")
    parts.append(f"- Favorite weekday: {stats['popular_weekday']} (statistically speaking)")
    parts.append(f"- Busiest month: {stats['busiest_month']}")
    parts.append(
        f"- Record attendance: {stats['top_attendance_count']} brave souls on {stats['top_attendance_day']:%Y-%m-%d}"
    )
    parts.append("")
    parts.append("TL;DR: the committee is alive, caffeinated, and meeting with admirable regularity.")
    return "\n".join(parts)


def _format_stats_md(stats: dict, committee_name: str) -> str:
    parts: list[str] = []
    parts.append(f"## 📊 Committee Stats — {committee_name}")
    parts.append("")
    parts.append(f"- 🗓️ First recorded meeting: **{stats['first_meeting']:%Y-%m-%d}**")
    parts.append(f"- 🆕 Latest recorded meeting: **{stats['last_meeting']:%Y-%m-%d}**")
    parts.append(f"- 🧭 Committee age: **{stats['days_running']} days** and counting")
    parts.append(f"- 🧑‍⚖️ Total meetings: **{stats['meetings_count']}**")
    if stats.get("avg_gap_days") is not None:
        parts.append(f"- ⏱️ On average: **one meeting every {stats['avg_gap_days']:.2f} days**")
    if stats.get("avg_attendance") is not None:
        parts.append(f"- 👥 Average attendance: **{stats['avg_attendance']:.1f}** people per meeting")
    if stats.get("avg_messages") is not None:
        parts.append(f"- 💬 Average chatter: **{stats['avg_messages']:.1f}** messages per meeting")
    if stats.get("popular_meeting_time"):
        parts.append(f"- ⏰ Preferred rendezvous: **around {stats['popular_meeting_time']}** (coffee optional)")
    parts.append(f"- 📆 Favorite weekday: **{stats['popular_weekday']}**")
    parts.append(f"- 📈 Busiest month: **{stats['busiest_month']}**")
    parts.append(
        f"- 🏆 Record attendance: **{stats['top_attendance_count']}** on **{stats['top_attendance_day']:%Y-%m-%d}**"
    )
    parts.append("")
    parts.append(
        "> TL;DR: the committee is alive, caffeinated, and meeting with admirable regularity."
    )
    return "\n".join(parts)


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Print fun statistics about the committee based on raw daily files.")
    p.add_argument("--input-dir", dest="input_dir", default=os.path.join("output", "raw"), help="Directory with daily raw files.")
    p.add_argument("--format", dest="fmt", default="text", choices=["text", "md"], help="Output format (text or Markdown).")
    p.add_argument("--save", dest="save_path", default=None, help="Optional file to save output to.")
    return p


def main(argv: Optional[Iterable[str]] = None) -> int:
    load_env()
    args = _build_arg_parser().parse_args(argv)
    committee_name = get_env("COMMITTEE_NAME", "Our Beloved Committee") or "Our Beloved Committee"
    stats = compute_stats(args.input_dir)
    content = (
        _format_stats_md(stats, committee_name)
        if args.fmt == "md"
        else _format_stats_text(stats, committee_name)
    )
    if args.save_path:
        parent = os.path.dirname(args.save_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(args.save_path, "w", encoding="utf-8") as f:
            f.write(content)
    else:
        print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

