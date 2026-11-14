<!-- Author: Dr. Denys Dutykh (Mathematics Department, Khalifa University of Science and Technology, Abu Dhabi, UAE) -->

# WhatsApp2Minutes: the minutes of a committee from its WhatsApp chat

A committee that works through a WhatsApp group keeps its decisions in the chat. The Python package `whatsapp2minutes` turns the text export of such a chat into official documents: a splitter writes one file per day, a transcriber asks a large language model to turn each day into a formal meeting document (title, date, time, attendees, agenda, summary, decisions, action items, edited transcript), and a third command summarises the activity of the committee over the whole chat. It uses the standard library of Python only; the calls to the language model go through `urllib`.

The repository is at

https://github.com/dutykh/WhatsApp2Minutes

## Quick start

Export the chat from WhatsApp as text (without media), save it as `input/ChatData.txt`, and run, from the root of the repository:

```bash
python3 -m whatsapp2minutes --input input/ChatData.txt --output output
python3 -m whatsapp2minutes.transcriber --dry-run
export OPENAI_API_KEY=...        # or write it into .env.local
python3 -m whatsapp2minutes.transcriber
```

The first command writes one file per day into `output/raw/`, the second shows which transcripts would be written without calling any model, and the last one writes them into `output/transcripts/`. The folders `input/` and `output/` are ignored by git, so that the chat and the minutes never enter the repository.

The name of the committee gives the names of the files. Written into `.env.local` as

```text
COMMITTEE_NAME="Graduate Studies Committee"
```

it gives the daily files `GraduateStudiesCommitteeMeeting-YYYY-MM-DD.txt` and the transcripts `GraduateStudiesCommittee-MeetingTranscript-YYYY-MM-DD.md`. Without it, the splitter and the transcriber use the default name of the code, "KU Math Seminar Committee", and the statistics "Our Beloved Committee".

## A small example

A chat exported as

```text
10/18/22, 09:00 - Alice: Agenda for today: the seminar schedule
10/18/22, 09:05 - Bob: Sounds good
and a second line of Bob
[10/19/22, 08:30] Carol: Attached the document
Continuation line without header
10/19/22, 08:40 - Alice: Thank you
```

is split into `GraduateStudiesCommitteeMeeting-2022-10-18.txt`, holding the first three lines, and `GraduateStudiesCommitteeMeeting-2022-10-19.txt`, holding the last three, each line copied unchanged.

## The splitter

```text
python3 -m whatsapp2minutes [options]
```

| Option | Meaning |
| --- | --- |
| `-i PATH`, `--input PATH` | the chat export (default `input/ChatData.txt`) |
| `-o DIR`, `--output DIR` | output folder; the daily files go to `DIR/raw` (default `output`) |
| `--prefix NAME` | prefix of the file names (default: the compact name of the committee followed by `Meeting`) |
| `--encoding NAME` | encoding of the input and output (default `utf-8`) |
| `--date-order MODE` | reading of an ambiguous date: `auto` (default), `dmy`, `mdy` or `ymd` |

Both forms of message header that WhatsApp writes are recognised, `12/31/21, 9:00 PM - Name: Message` and `[12/31/21, 9:00 PM] Name: Message`, with times on 24 or 12 hours. Dates are written as `YYYY-MM-DD`: a date already in that form (or `YYYY/MM/DD`) is kept, a two-digit year from 00 to 68 means 2000 to 2068 and any other means 1900 to 1999, and when day and month could be swapped, `--date-order` decides. The mode `auto` looks at each date alone: it reads a number above 12 as the day and, when both are 12 or less, puts the day first, so that a chat whose dates put the month first needs `--date-order mdy`. A message of several lines stays with the date of its first line; the lines before the first header are skipped, and so is a header whose date cannot be read, with the lines that follow it, until the next valid header.

## The transcriber

```text
python3 -m whatsapp2minutes.transcriber [options]
```

For each daily file, the transcriber estimates the time of the meeting as the middle of the quarter of an hour that holds the most messages, lists the attendees from the senders of the day, and asks the model for a formal and respectful document with fixed sections, without the private, offensive or off-topic messages. The text of the day, cut at `--max-prompt-chars` characters, is sent to the chosen provider: OpenAI (`OPENAI_API_KEY`, and `OPENAI_BASE_URL` for a compatible server), OpenRouter (`OPENROUTER_API_KEY`) or Anthropic (`ANTHROPIC_API_KEY`). Nothing is redacted before the text leaves the machine.

| Option | Meaning |
| --- | --- |
| `--input-dir DIR` | the daily files (default `output/raw`) |
| `--output-dir DIR` | the transcripts (default `output/transcripts`) |
| `--provider NAME` | `openai`, `openrouter` or `anthropic` (default `$LLM_PROVIDER`, else `openai`) |
| `--model NAME` | the model, such as `gpt-4o` (default `$LLM_MODEL`) |
| `--format md\|txt` | Markdown (default) or plain text |
| `--overwrite` | write over existing transcripts, which are otherwise skipped |
| `--dry-run` | print the file names without calling any model |
| `--max-prompt-chars N` | at most N characters of the day in the request (default 120000) |
| `--state-file PATH` | the record of each day's outcome (default `OUTPUT-DIR/.transcriber_state.json`) |
| `--resume-failed` | process again only the days recorded as failed |

The record of outcomes keeps, for each day, the input and output files, the status (`success`, `failed` or `skipped`), the error if any, the provider, the model and the time of the update (UTC), so that `python3 -m whatsapp2minutes.transcriber --resume-failed` retries only what failed.

## The statistics

```text
python3 -m whatsapp2minutes.stats [--input-dir DIR] [--format text|md] [--save PATH]
```

The command reads the daily files (default `output/raw`) and prints, in a light-hearted tone, a short report on the life of the committee: the first and the latest day with messages, the number of days since the first one, the number of such days and the mean gap between them, the mean number of people writing and of messages on a day, the usual time of the meetings, the weekday and the month with the most meetings, and the day when the most people wrote. Each day with messages counts as one meeting. The option `--format md` gives the same report in Markdown, and `--save PATH` writes it into a file instead of printing it.

## Settings

The files `.env` and `.env.local` (both ignored by git) are read at the start, `.env.local` taking precedence over `.env`, and a variable already set in the environment over both; `.env.example` is a template. The variables are `COMMITTEE_NAME`, `LLM_PROVIDER`, `LLM_MODEL`, the three API keys and `OPENAI_BASE_URL`.

## Contents

| Path | Content |
| --- | --- |
| `whatsapp2minutes/__main__.py` | the command of the splitter, `python3 -m whatsapp2minutes` |
| `whatsapp2minutes/parser.py` | the splitter itself |
| `whatsapp2minutes/transcriber.py` | the transcriber and its command; `transcribe_main.py` is a second entry point to it |
| `whatsapp2minutes/stats.py` | the statistics and their command |
| `whatsapp2minutes/env.py`, `utils.py` | the reader of `.env` files and the compact name of the committee |
| `.env.example` | the template of the settings |

## Troubleshooting

When the days come out wrong, the order of day and month is probably the other one: run again with `--date-order mdy` (month first, as in the United States) or `--date-order dmy`. Strange characters call for the encoding of the export, such as `--encoding iso-8859-1`. Missing days, or too many files, mean that the export is not the plain text one or that its headers have another form than the two above.

## Requirements

Python 3.10 or newer, with no other package; the transcriber needs network access and the key of one provider.

## How to cite

The file [`CITATION.cff`](CITATION.cff) describes the package for citation, and GitHub turns it into a reference, in APA or BibTeX, through the "Cite this repository" button of the repository page.

## Licence

The code is free software under the GNU General Public License, version 3; the text is in [LICENSE](LICENSE).

## Author

Dr. Denys Dutykh, Mathematics Department, Khalifa University of Science and Technology, Abu Dhabi, United Arab Emirates (https://www.denys-dutykh.com/).
