# 📜 WhatsApp2Minutes

Tools to convert WhatsApp chats into official meeting minutes and transcripts.

## 👤 Author

**Dr. Denys Dutykh**
Khalifa University of Science and Technology, Abu Dhabi, UAE

This repository includes a lightweight parser that splits a WhatsApp chat export into one file per day and a transcriber that turns each day into a formal meeting transcript using an LLM. No external dependencies are required; HTTP calls use Python's standard library.

## ✨ Features (Current)

- Split chat by day: Creates `output/raw/<Prefix>-YYYY-MM-DD.txt` files, one per date.
- Smart prefix: File prefix derives from `COMMITTEE_NAME` (e.g., "KU Math Seminar Committee" → `KUMathSeminarCommitteeMeeting`). `--prefix` flag can override.
- WhatsApp formats: Supports both `date, time - ...` and `[date, time] ...` formats from WhatsApp exports.
- 🧵 Multiline messages: Preserved and grouped under the date of their first line.
- 📅 Ambiguous dates: Heuristic and `--date-order` option (`auto`/`dmy`/`mdy`/`ymd`).
- 🖋️ LLM transcriber: Generates Markdown meeting documents (Title, Date, Meeting Time, Attendees, Agenda, Summary, Key Decisions, Action Items, Edited Transcript) with formal, respectful tone and removal of offensive/off-topic content.
- 🔁 Resume support: Tracks per-day outcomes in a state file and can retry only failed days.
 - 📊 Fun stats: Prints a lighthearted statistics summary (first/last meeting, total meetings, averages, busiest month, etc.).

## 🧰 Requirements

- Python 3.10+ (uses modern typing and stdlib only)

## 🧩 Project Layout

```
.
├── input/
│   └── ChatData.txt              # your WhatsApp export (default path)
├── output/
│   ├── raw/                      # generated daily files (created on first run)
│   └── transcripts/              # generated Markdown transcripts
├── whatsapp2minutes/
│   ├── __main__.py               # CLI: python -m whatsapp2minutes (splitter)
│   ├── env.py                    # simple .env loader
│   ├── parser.py                 # daily splitter
│   ├── transcriber.py            # LLM-based transcript generator
│   ├── transcribe_main.py        # CLI: python -m whatsapp2minutes.transcriber
│   └── utils.py                  # shared helpers
│   └── stats.py                  # fun statistics CLI
├── .env.example                  # template for local env
├── .env.local                    # your local overrides (git-ignored)
├── LICENSE
└── README.md
```

## 🚀 Quick Start

1) Put your exported chat text at `input/ChatData.txt` (or pass a custom path with `--input`).

2) Optionally set your committee name in `.env.local` (derived prefix):

```
COMMITTEE_NAME="KU Math Seminar Committee"
```

3) Run the splitter:

```
python -m whatsapp2minutes --input input/ChatData.txt --output output
```

4) Find results under `output/raw/` as:

```
KUMathSeminarCommitteeMeeting-YYYY-MM-DD.txt
```

## 🛠️ Splitter CLI Reference

Command:

```
python -m whatsapp2minutes [options]
```

Options:

- `-i, --input <path>`: Path to WhatsApp chat export (text). Default: `input/ChatData.txt`.
- `-o, --output <dir>`: Output directory. Daily files go to `<dir>/raw`. Default: `output`.
- `--prefix <name>`: Filename prefix. If omitted, derived from `COMMITTEE_NAME` (see Environment) as a compact form plus "Meeting".
- `--encoding <name>`: Input/output encoding. Default: `utf-8`.
- `--date-order <mode>`: Interpretation for ambiguous day/month in slash/dash dates. One of `auto` (default), `dmy`, `mdy`, `ymd`.

Exit code: `0` on success.

## 🖋️ Transcriber CLI Reference

Command:

```
python -m whatsapp2minutes.transcriber [options]
```

What it does:
- Reads each `*.txt` produced by the splitter under `output/raw/`.
- Estimates meeting time using a message-time histogram (15-minute bins).
- Infers attendees from message headers (deduplicated).
- Builds a strict prompt to produce a formal, respectful document with required sections.
- Calls your configured LLM and writes Markdown to `output/transcripts/CompactCommitteeName-MeetingTranscript-YYYY-MM-DD.md`.

Options:
- `--input-dir <dir>`: Directory with raw daily files. Default: `output/raw`.
- `--output-dir <dir>`: Directory for transcripts. Default: `output/transcripts`.
- `--provider <name>`: `openai`, `openrouter`, or `anthropic`. Defaults to `$LLM_PROVIDER` or `openai`.
- `--model <name>`: Model name (e.g., `gpt-4o`). Defaults to `$LLM_MODEL`.
- `--format md|txt`: Output format. Default: `md`.
- `--overwrite`: Overwrite existing transcript files.
- `--dry-run`: Compute filenames and print actions, but do not call an API.
 - `--max-prompt-chars <n>`: Limit raw content included in the prompt (default: 120000 chars).
 - `--state-file <path>`: Path to the state file used to track outcomes (default: `<output-dir>/.transcriber_state.json`).
 - `--resume-failed`: Retry only days previously recorded as failed in the state file.

### 🔁 State & Resume

- The transcriber maintains a JSON state file (default: `<output-dir>/.transcriber_state.json`) with per-day outcomes.
- Each record includes: `input`, `output`, `status` (`success|failed|skipped`), `error` (if any), `provider`, `model`, and `updated_at` (UTC).
- Resume only failed days:

```
python -m whatsapp2minutes.transcriber --resume-failed
```

- Use a custom state file location:

```
python -m whatsapp2minutes.transcriber --state-file output/.transcriber_state.json
```

## Parsing Details

- Supported headers:
  - `12/31/21, 9:00 PM - Name: Message`
  - `[12/31/21, 9:00 PM] Name: Message`

- Time formats: 24-hour (`09:00`) and 12-hour (`9:00 AM/PM`).

- Date normalization:
  - Converts to `YYYY-MM-DD`.
  - Explicit `YYYY-MM-DD` / `YYYY/MM/DD` is honored directly.
  - Two-digit years map to 19xx/20xx using a common pivot (00–68 → 2000–2068, else 1900–1999).
  - When day/month is ambiguous, `--date-order` applies; `auto` uses a simple heuristic (e.g., values >12 disambiguate).

- Multiline messages: Lines following a header line belong to the same message until the next header; all such lines are grouped under that date.

- Preamble lines: Any lines before the first recognized message header are skipped.

- Unparseable headers: If a header is detected but its date cannot be normalized, that header (and following lines until a valid header) are skipped. This is rare on clean exports; if you see unexpected gaps, check `--date-order` and encoding.

## Output

- Destination: `<output>/raw/` (created if missing).
- Naming: `<Prefix>-YYYY-MM-DD.txt` where `<Prefix>` is either `--prefix` or derived from `COMMITTEE_NAME` (`KUMathSeminarCommitteeMeeting` by default).
- Contents: Raw lines from the original export for that date, unchanged.

## 🔐 Environment

- Files:
  - `.env` (optional, shared) and `.env.local` (local, git-ignored) are read automatically.
  - See `.env.example` for a template.

- Variables:
  - `COMMITTEE_NAME`: Used to derive the output file prefix and transcript names. Example: `"KU Math Seminar Committee"` → `KUMathSeminarCommitteeMeeting` and `KUMathSeminarCommittee-...`.
  - `LLM_PROVIDER`, `LLM_MODEL`: Defaults for the transcriber.
  - API keys: `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`.

Precedence: Existing process environment → `.env.local` → `.env`.

## 📄 Examples

Input snippet:

```
10/18/22, 09:00 - Alice: Agenda for today...
10/18/22, 09:05 - Bob: Sounds good
[10/19/22, 08:30] Carol: Attached the document
Continuation line without header
```

Resulting files:

```
output/raw/KUMathSeminarCommitteeMeeting-2022-10-18.txt
output/raw/KUMathSeminarCommitteeMeeting-2022-10-19.txt
```

Transcriber (dry run):

```
python -m whatsapp2minutes.transcriber --input-dir output/raw --output-dir output/transcripts --dry-run
```

Transcriber (generate):

```
export OPENAI_API_KEY=...  # or set in .env.local
python -m whatsapp2minutes.transcriber --input-dir output/raw --output-dir output/transcripts
```

## 🧭 End-to-End

1) Split the chat:

```
python -m whatsapp2minutes --input input/ChatData.txt --output output
```

2) Generate transcripts:

```
python -m whatsapp2minutes.transcriber --input-dir output/raw --output-dir output/transcripts
```

## 🧩 Troubleshooting

- Wrong day/month split: Re-run with `--date-order dmy` or `--date-order mdy` to match your locale.
- Encoding issues (weird characters): Try `--encoding iso-8859-1` (or your export’s encoding).
- Missing days or too many files: Ensure your export is the plain text format and matches one of the supported header styles.

## 🗺️ Roadmap (Next)

- Add configurable templates for transcript sections and styling.
- Add per-day metadata caching and resume/skip logic.
- Optional redaction rules prior to LLM call.

## License

See `LICENSE`.

## 📊 Fun Stats

Get a lighthearted snapshot of your committee’s activity:

Command:

```
python -m whatsapp2minutes.stats --input-dir output/raw --format md
```

Options:
- `--input-dir <dir>`: Directory with raw daily files. Default: `output/raw`.
- `--format text|md`: Output format (plain text or Markdown). Default: `text`.
- `--save <path>`: Save stats to a file instead of printing.

Example output (text):

```
Committee vitality report for KU Math Seminar Committee (a.k.a. we do things):

- First recorded meeting: 2023-02-01
- Latest recorded meeting: 2025-09-06
- Committee age: 948 days and counting
- Total meetings: 312
- On average: one meeting every 2.12 days
- Average attendance: 3.1 people per meeting
- Average chatter: 19.4 messages per meeting
- Preferred rendezvous: around 12:15 (coffee optional)
- Favorite weekday: Tuesday (statistically speaking)
- Busiest month: 2024-11
- Record attendance: 7 brave souls on 2025-07-24

TL;DR: the committee is alive, caffeinated, and meeting with admirable regularity.
```
