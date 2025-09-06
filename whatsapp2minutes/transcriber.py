"""
Author: Dr. Denys Dutykh (Khalifa University of Science and Technology, Abu Dhabi, UAE)
"""

import argparse
import json
import math
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta
from glob import glob
from typing import Iterable, Optional, Tuple
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

from .env import load_env, get_env
from .utils import compact_committee_name


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


def _extract_name_and_time(line: str) -> Tuple[Optional[str], Optional[str]]:
    m = _PATTERN_DASH.match(line) or _PATTERN_BRACKET.match(line)
    if not m:
        return None, None
    prefix_len = m.end()
    rest = line[prefix_len:]
    # Name can be followed by ':' for message
    name = None
    if ':' in rest:
        name = rest.split(':', 1)[0].strip()
        # remove common WhatsApp suffixes like "<name> created group" if present
        # but keep plain names
        name = re.sub(r"\s+(created|added|removed).*", "", name)
    return name or None, m.group('time')


def _minutes_of_day(time_str: str) -> Optional[int]:
    # Accept both 24h and 12h AM/PM
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
    # Histogram on 15-min bins
    bin_size = 15
    bins = Counter((m // bin_size) for m in minutes)
    best_bin, _ = max(bins.items(), key=lambda kv: kv[1])
    # Choose center of the busiest bin
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
    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for n in names:
        if n not in seen:
            uniq.append(n)
            seen.add(n)
    return uniq


def _build_prompts(committee_name: str, date_str: str, meeting_time: Optional[str], participants: list[str], raw_text: str, format_: str = "md") -> Tuple[str, str]:
    system = (
        "You are an expert minute-taker for official committee meetings. "
        "Rewrite raw WhatsApp chat into a formal, concise, and professional meeting record. "
        "Remove irrelevant, off-topic, or offensive content. Preserve factual decisions, action items, and key discussion points. "
        "Do not invent facts; if uncertain, mark as 'Not recorded'."
    )
    heading = "#" if format_ == "md" else ""
    participants_str = ", ".join(participants) if participants else "Not recorded"
    time_str = meeting_time or "Not recorded"
    user = (
        f"Produce an official meeting document for the '{committee_name}'.\n"
        f"Date: {date_str}\n"
        f"Approximate meeting time (local): {time_str}\n"
        f"Participants (inferred from messages, may be incomplete): {participants_str}\n\n"
        "Required sections (use Markdown if supported):\n"
        "- Title\n- Date\n- Meeting Time\n- Attendees\n- Agenda (if inferable)\n- Summary\n- Key Decisions\n- Action Items (assignee, due date if inferable)\n- Edited Transcript (polished, respectful, removing noise/offense)\n\n"
        "Guidelines:\n"
        "- Maintain formal and respectful tone.\n"
        "- Remove private or offensive content and non-meeting chatter.\n"
        "- Consolidate repeated points and clearly attribute if obvious.\n"
        "- Keep it concise and bureaucratically clear.\n\n"
        "Raw messages for the day are provided below. Treat them as source material, not as-is output.\n\n"
        "```chat\n" + raw_text.strip() + "\n```\n"
    )
    return system, user


def _http_post_json(url: str, headers: dict, payload: dict, timeout: float = 60.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, headers={"Content-Type": "application/json", **headers}, method="POST")

    class HttpRequestError(Exception):
        def __init__(self, url: str, status: Optional[int], headers: Optional[dict], body: Optional[str], reason: Optional[str] = None):
            snippet = (body or "").strip()
            if len(snippet) > 800:
                snippet = snippet[:800] + "..."
            msg = f"HTTP request failed: url={url} status={status} reason={reason} body={snippet}"
            super().__init__(msg)
            self.url = url
            self.status = status
            self.headers = headers or {}
            self.body = body
            self.reason = reason

    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return json.loads(body.decode("utf-8", errors="replace"))
    except HTTPError as e:
        try:
            err_body = e.read().decode("utf-8", errors="replace")
        except Exception:
            err_body = None
        raise HttpRequestError(url=url, status=e.code, headers=dict(e.headers or {}), body=err_body, reason=getattr(e, 'reason', None))
    except URLError as e:
        raise HttpRequestError(url=url, status=None, headers=None, body=None, reason=str(getattr(e, 'reason', e)))
    except Exception as e:
        raise HttpRequestError(url=url, status=None, headers=None, body=None, reason=str(e))


def _call_openai_chat(api_key: str, model: str, system: str, user: str, base_url: Optional[str] = None, temperature: float = 0.2, max_tokens: Optional[int] = None) -> str:
    url = (base_url.rstrip("/") if base_url else "https://api.openai.com/v1") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": float(temperature),
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)
    data = _http_post_json(url, headers, payload)
    return data["choices"][0]["message"]["content"].strip()


def _call_openrouter_chat(api_key: str, model: str, system: str, user: str, temperature: float = 0.2, max_tokens: Optional[int] = None) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Title": "WhatsApp2Minutes",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": float(temperature),
    }
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)
    data = _http_post_json(url, headers, payload)
    return data["choices"][0]["message"]["content"].strip()


def _call_anthropic_messages(api_key: str, model: str, system: str, user: str, max_tokens: int = 4096, temperature: float = 0.2) -> str:
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": model,
        "max_tokens": int(max_tokens),
        "temperature": float(temperature),
        "system": system,
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": user}]}
        ],
    }
    data = _http_post_json(url, headers, payload)
    # content is a list of blocks, join text blocks
    parts = []
    for block in data.get("content", []):
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts).strip()


def _choose_provider_call(provider: str):
    provider = (provider or "openai").lower()
    if provider == "openai":
        return "openai"
    if provider == "openrouter":
        return "openrouter"
    if provider == "anthropic":
        return "anthropic"
    # fallback
    return "openai"


def _sanitize_date_from_filename(path: str) -> Optional[str]:
    # Expect formats like <prefix>-YYYY-MM-DD.txt
    m = re.search(r"(\d{4}-\d{2}-\d{2})", os.path.basename(path))
    return m.group(1) if m else None


def _truncate_for_prompt(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    head = text[: max_chars - 2000]
    tail = "\n\n[... truncated due to length ...]\n"
    return head + tail


def transcribe_file(
    raw_path: str,
    out_dir: str,
    committee_name: str,
    provider: str,
    model: str,
    fmt: str = "md",
    overwrite: bool = False,
    dry_run: bool = False,
    max_prompt_chars: int = 120_000,
) -> Optional[str]:
    with open(raw_path, "r", encoding="utf-8", errors="ignore") as f:
        raw_text = f.read()

    header_lines = list(_iter_header_lines(raw_text.splitlines()))
    participants = _collect_participants(header_lines)
    meeting_time = _estimate_meeting_time(header_lines)
    date_str = _sanitize_date_from_filename(raw_path) or "Unknown"

    system, user = _build_prompts(committee_name, date_str, meeting_time, participants, _truncate_for_prompt(raw_text, max_prompt_chars), format_=fmt)

    compact_name = compact_committee_name(committee_name)
    ext = "md" if fmt == "md" else "txt"
    out_name = f"{compact_name}-MeetingTranscript-{date_str}.{ext}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, out_name)
    if os.path.exists(out_path) and not overwrite:
        return out_path

    if dry_run:
        return out_path

    # Dispatch to provider
    which = _choose_provider_call(provider)
    if which == "openai":
        api_key = get_env("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        base = get_env("OPENAI_BASE_URL")
        content = _call_openai_chat(api_key, model, system, user, base_url=base)
    elif which == "openrouter":
        api_key = get_env("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY not set")
        content = _call_openrouter_chat(api_key, model, system, user)
    elif which == "anthropic":
        api_key = get_env("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set")
        content = _call_anthropic_messages(api_key, model, system, user)
    else:
        raise RuntimeError(f"Unsupported provider: {provider}")

    with open(out_path, "w", encoding="utf-8") as out:
        out.write(content)
    return out_path


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Generate formal meeting transcripts from daily raw chat files using an LLM.")
    p.add_argument("--input-dir", dest="input_dir", default=os.path.join("output", "raw"), help="Directory with daily raw files.")
    p.add_argument("--output-dir", dest="output_dir", default=os.path.join("output", "transcripts"), help="Directory to write transcripts.")
    p.add_argument("--provider", dest="provider", default=None, help="LLM provider: openai, openrouter, or anthropic. Defaults to $LLM_PROVIDER or openai.")
    p.add_argument("--model", dest="model", default=None, help="Model name, e.g., gpt-4o. Defaults to $LLM_MODEL.")
    p.add_argument("--format", dest="fmt", default="md", choices=["md", "txt"], help="Output format (Markdown recommended).")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing transcript files.")
    p.add_argument("--dry-run", action="store_true", help="Do not call the API; just compute file names.")
    p.add_argument("--max-prompt-chars", dest="max_prompt_chars", type=int, default=120_000, help="Maximum characters from raw file to include in prompt.")
    return p


def main(argv: Optional[Iterable[str]] = None) -> int:
    load_env()  # load .env/.env.local if present
    args = _build_arg_parser().parse_args(argv)

    committee_name = get_env("COMMITTEE_NAME", "KU Math Seminar Committee") or "KU Math Seminar Committee"
    provider = args.provider or (get_env("LLM_PROVIDER") or "openai")
    model = args.model or (get_env("LLM_MODEL") or "gpt-4o")

    raw_files = sorted(glob(os.path.join(args.input_dir, "*.txt")))
    if not raw_files:
        print(f"No raw files found under {args.input_dir}")
        return 1

    os.makedirs(args.output_dir, exist_ok=True)
    written = 0
    skipped = 0
    for path in raw_files:
        try:
            out_path = transcribe_file(
                raw_path=path,
                out_dir=args.output_dir,
                committee_name=committee_name,
                provider=provider,
                model=model,
                fmt=args.fmt,
                overwrite=args.overwrite,
                dry_run=args.dry_run,
                max_prompt_chars=args.max_prompt_chars,
            )
            if os.path.exists(out_path):
                if args.overwrite:
                    written += 1
                else:
                    # It may have been pre-existing
                    if os.path.getmtime(out_path) >= os.path.getmtime(path):
                        skipped += 1
                    else:
                        written += 1
            print(f"Processed {os.path.basename(path)} -> {os.path.basename(out_path)}")
            # Light pacing to avoid rate limits when running for many days
            if not args.dry_run:
                time.sleep(0.3)
        except Exception as e:
            print(f"Error processing {path}: {e}")
    print(f"Done. Written/updated: {written}, skipped: {skipped}. Output: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
