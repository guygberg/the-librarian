# The Librarian: first useful outcome

Terms follow `GLOSSARY.md` (Workspace, Work computer, Source item, Record, Link, Person, Alias, Suggested link, Evidence, Basis, Person event, Freshness, Stale, Needs attention, Review list, Import).

## Problem Statement

My work lives in Slack threads, old Claude sessions and meeting recordings, some of them in Hebrew or a mix of Hebrew and English. To know what is open, what I am waiting on, what was decided and why, and where a project stands, I have to search all three by hand and I cannot tell what is current, what is only an intention, or what is stale. I cannot ask Claude, because it has no grounded, source-linked memory of my work. Summaries I could get elsewhere do not let me check them against the original discussion, and they may quietly disagree with each other.

## Solution

The Librarian is a local memory bank on my Work computer, in a sealed "work" Workspace. A manual Import fetches the Slack conversations I picked, my Claude sessions and my Drive meeting recordings, transcribes recordings locally, has Claude Code (headless) extract Records from them, and links those Records to each other and to their Evidence. The same Records are served two ways from one query core: a read-only `librarian` CLI plus a Claude Code skill, so Claude can answer "What are my open items?" and "Where does this project stand?" with cited, basis-labelled facts; and a polished local web UI (a dark single stream with a bottom source sheet and a Relations graph) for me to explore, drill down to the original source, and make my own corrections. Every view and answer shows Freshness, separates stated, inferred and confirmed, and never treats silence as completion. The Librarian never writes to any source system. It is built and tested on Linux against a made-up fixture set, then I check it against real sources on the Mac.

## User Stories

Importing and sources

1. As the person, I want to start an Import by hand from the CLI, so that nothing runs in the background without my knowing.
2. As the person, I want to start the same Import from a button in the UI, and only one Import to run at a time (a second start is refused and shows the running one's progress), so that I do not need a terminal and nothing is fetched or sent to Claude twice.
3. As the person, I want Import to run five saved stages (fetch, transcribe, normalise, extract, link), so that a failure resumes from the failed stage instead of redoing everything.
4. As the person, I want running Import twice to produce no duplicates, so that I can run it whenever I like.
5. As the person, I want only changed items to be re-extracted (decided by content hash), so that repeated Imports are fast and use little of my Claude allowance.
6. As the person, I want an edited Slack message stored as a new revision that keeps the old one, so that I can see what changed.
7. As the person, I want a failed item to record its stage and error while the rest continues, and only failed items retried next Import, so that one bad file does not block my work.
8. As the person, I want live per-source progress (fetched, transcribed, extracted, failed) in the CLI and in the UI import panel, so that I know what an Import is doing.
9. As the person, I want a per-run cap on extraction calls (default 200, settable), newest items first, with a clean stop and continuation next run, so that a first Import cannot exhaust my Claude seat.
10. As the person, I want a dry-run command that prints how many extraction calls an Import would make before anything is sent, so that I can decide first.
11. As the person, I want Slack and Claude sessions searchable before recordings finish transcribing, so that slow transcription never blocks me.

Slack

12. As the person, I want to pick which Slack conversations are imported (public, private, DM, group DM) from one saved list, so that nothing, including DMs, is imported automatically.
13. As the person, I want the CLI (`librarian slack pick`) and the UI import panel to edit that same list and show every conversation my login can see with name, kind and member count, so that picking is easy from either place.
14. As the person, I want the first Import of a picked conversation to cover the last 30 days, with "import older" per conversation after a dry-run count, so that history is a choice.
15. As the person, I want later Imports to fetch only newer items and re-check the last 7 days for edits and deletions, so that the memory stays accurate cheaply.
16. As the person, I want an unpicked conversation to keep its stored items, and a message later missing from Slack marked "gone from Slack" with its Evidence kept, so that history survives deletions.
17. As the person, I want a confirmed "forget this conversation" action that deletes its source items and any Record with no other Evidence, recorded as a Person event, so that I can remove a conversation entirely.
18. As the person, I want the importer to use only my own Slack login, read-only, never posting, reacting or marking anything read, so that source systems are never changed.
19. As the person, I want each Slack source item to keep its conversation name and kind, so that I see where it came from.
20. As the person, I want only picked conversations to reach Claude, and the import panel to say so next to the list, so that I decide what leaves the machine.

Claude sessions and recordings

21. As the person, I want my Claude sessions read from their `.jsonl` files and copied into the Librarian's store, so that they survive the roughly 30-day cleanup, with the Librarian's own output left out (tool calls and results of `librarian` commands, assistant text in turns that made such calls, and the Librarian clone's own project folder), so that the memory never confirms itself from its own echo.
22. As the person, I want recordings read from the synced Drive folder with a size check before transcribing, so that a not-yet-downloaded file waits or fails visibly instead of producing garbage.
23. As the person, I want recordings transcribed fully offline with whisper.cpp, using the ivrit.ai model for Hebrew and mixed recordings and the stock model for English, so that nothing is uploaded and nothing costs money.
24. As the person, I want the recording language taken from an explicit flag, else detected from the first 30 seconds, and overridable in the CLI, so that the right model is used.
25. As the person, I want transcripts with segment timestamps, so that I can find the original moment.
26. As the person, I want low-confidence passages flagged "low confidence" (never presented as errors or as fact), so that I know what to double-check.
27. As the person, I want a recording transcribed once per file hash, so that re-importing does not redo hours of work.

People, projects and linking

28. As the person, I want a Slack user id to link to its Person automatically, so that owners from Slack are right.
29. As the person, I want a text name in a session or recording to link only when it exactly matches one known Alias of exactly one Person, and otherwise become a Suggested link shown with the raw name and an "unconfirmed person" mark, so that guessed owners are never presented as facts.
30. As the person, I want accepting a suggestion to save the name as an Alias, so that it links automatically next time.
31. As the person, I want to fix a wrong person link by moving an Alias to another Person or splitting it off, from the person node's menu in Relations or from a Review list row, so that mistakes are correctable.
32. As the person, I want first-person lines in recordings to be "unknown speaker" until I set the speaker of a transcript segment by hand from the line in the source sheet, so that no one is blamed from a guess.
33. As the person, I want my hand-set speakers to survive re-transcription and re-extraction and to replace "unknown speaker" on the Records built from that segment, so that I fix it once.
34. As the person, I want "me" to mean the Slack login's user plus extra names I list at setup (such as a Hebrew spelling), so that my items are recognised.
35. As the person, I want Claude to be able to create a project during extraction, marked inferred and listed in the Review list until I confirm, rename or merge it from the project's status header, so that projects appear without silently becoming truth.
36. As the person, I want project merge, split and moving a Record to another project to be Person events that survive re-import, with a merged project keeping old names as aliases, so that corrections stick.
37. As the person, I want the importer to only suggest project merges, never perform them, so that I stay in control.
38. As the person, I want clear matches (exact project name or alias, known Slack user) linked automatically and unsure ones stored as Suggested links, so that the memory connects without false confidence.

Memory and trust

39. As the person, I want every Record to have at least one Evidence link with locator, short verbatim quote and role (supports, completes, contradicts), so that I can check any claim.
40. As the person, I want the importer to reject Records, ids, links and quotes that do not match the source text it sent, logging the rejection, so that fabricated references never enter the memory.
41. As the person, I want each Record to show lifecycle (open, pending, suspended, done, dropped, superseded), Basis (stated, inferred, confirmed) and, for action items, commitment (intention, request, commitment), so that I do not confuse an intention with a commitment.
42. As the person, I want an item never to count as done without completion Evidence or my own mark, so that silence is never treated as completion.
43. As the person, I want Records computed Stale at read time from per-kind thresholds (starting values 14 days for action items and blockers, 30 for open questions, never for decisions), configurable, so that old discussion is not treated as current.
44. As the person, I want contradicting Records to stay visible and linked on both sides, with their Evidence, until I resolve them, so that disagreement is shown, not hidden.
45. As the person, I want Records to keep their ids across re-extraction, so that my corrections and history stay attached.
46. As the person, I want a corrected Record that extraction no longer produces to stay, flagged "no longer found in sources", so that my work is not lost.
47. As the person, I want all my changes (mark done, reopen, change owner, accept or reject, merge, correct) stored as Person events with history, and shown on the item, so that I can see what I changed and when.
48. As the person, I want Freshness (last successful Import per source) at the top of every view, so that I always know how current I am looking.

Claude answering

49. As the person, I want Claude to answer "What are my open items?" from the same open-items query the UI uses (Needs attention, Waiting on others, Other open, each item with its group), so that Claude and the UI never show two different lists.
50. As the person, I want Claude to answer "Where does this project stand?" with status, owners, deadlines, latest decision and main blocker, each with its Evidence locator, so that I can verify it.
51. As the person, I want named read-only commands (open-items, project, changes, waiting, decision, blocked, search, show), so that Claude can answer "what changed since the last meeting", "what am I waiting on and who owns the next step", "why did we decide this" and "what is blocked".
52. As the person, I want every answer to carry records, evidence and freshness in one fixed envelope, so that answers are consistent and checkable.
53. As the person, I want the project resolved only when one match is clearly ahead, and otherwise candidates returned so Claude asks me which is meant, and every answer to name the project it used, so that Claude never answers about the wrong project.
54. As the person, I want "since the last meeting" to mean the latest recording about the project (latest overall if no project), with its date stated, falling back to the last 7 days and saying so, so that the baseline is explicit.
55. As the person, I want an answer to start with a warning when a source was never imported or its last Import is too old, so that I am not misled by missing data.
56. As the person, I want Claude to label each claim confirmed, stated or inferred and to say "stale", "contradicted" or "no evidence found" in plain words, so that uncertainty is visible.
57. As the person, I want Claude to be able to open the surrounding source passage for one Evidence locator (`show`), so that it can check a quote in context.
58. As the person, I want the answer commands to be read-only and the admin commands (import, slack pick, forget, backup, restore, serve, install-skill) to be for me alone, with the skill allowed to run only the answer commands and told never to act on source systems, treat intentions as commitments, treat unmentioned tasks as done, or present uncertain transcription as fact, and destructive admin commands to need an interactive confirmation, so that a prompt-injected Claude session cannot change or delete my records or start an Import.
59. As the person, I want Claude to suggest a change only in text ("this looks done, mark it in the UI?"), so that I make every change myself.

Web UI

60. As the person, I want the UI served only on localhost with no login, and the server to refuse requests from other web pages in my browser (wrong Host or Origin, missing per-run token), so that setup is trivial, the data stays local and no web page can start an Import, delete a conversation or read my memory.
61. As the person, I want a dark single stream headed by the date, a headline count ("N things need you, M waiting on someone else") and a progress line of items finished this week out of those done plus still open this week (week from Sunday 00:00), so that I see where I stand at a glance.
62. As the person, I want a project chip row (All work plus each project) that filters the stream, with a status header on top for a project (status summary, blockers, latest decisions, what changed since the last meeting), so that a project view is the same stream, not a separate maze.
63. As the person, I want kind tabs (Items, Decisions, Blockers, Questions, Done) under the chips, so that I can switch kind without leaving the stream.
64. As the person, I want items grouped under "Needs attention", "Waiting on others" and a collapsed "Other open", expandable in place, with project, owner, due date, Basis marker (inferred dashed, confirmed solid) and warnings such as "Sources disagree", "Transcription uncertain" or "Not mentioned since ...", so that the reason for attention is visible before I open it.
65. As the person, I want an expanded item to have Evidence and Relations tabs, so that I can see the supporting passages or the connections.
66. As the person, I want clicking an evidence quote to open a bottom source sheet showing the surrounding Slack thread, session passage or transcript window with the evidence line highlighted and an "Open original" action that works for all three sources (Slack: the permalink; a recording: the server streams the local file with HTTP range support into an in-page player seeked to the timestamp; a session: the copied `.jsonl` passage as a raw view), so that I reach the source without leaving context.
67. As the person, I want Hebrew quotes rendered right-to-left with an English gloss below (written by extraction and labelled as machine translation), uncertain words dotted-underlined with the gloss noting the uncertainty, and summaries in English, so that Hebrew content is readable and honest.
68. As the person, I want a Relations graph centred on the item that opens at 1 hop, expands to 2 or 3 hops with outer hops faded, filters by edge kind (belongs-to, owner, waiting-on, blocks, supersedes, related-to, mentions, evidence) and re-centres when I click a node, so that I can see everything an item relates to and how.
69. As the person, I want a search box on every view, focused with `/`, returning records first (items, decisions, projects, people) then raw source passages, with Hebrew matching including prefixed forms, and results opening in place, so that I can find anything fast.
70. As the person, I want the freshness line to open an import panel (per-source last Import and status, Import button, dry-run call count, Slack picker, failed items awaiting retry) and show progress during an Import, so that data control is one click away.
71. As the person, I want an "N to review" count by the freshness line opening a Review list with both sides, evidence and Accept / Reject per row, and a "suggested" marker inline on affected items, with suggestions never in Needs attention, so that unsure links never masquerade as facts.
72. As the person, I want to mark an item done, reopen it, change its owner, move it to another project and resolve a source disagreement (choose which Record holds, so the other becomes superseded, or mark both wrong) on the expanded item with history shown, none of which touches the source, so that my corrections live only in the Librarian.
73. As the person, I want a person to be a filter on owner and waiting-on and a node in Relations, with no person page, so that the UI stays small.
74. As the person, I want every view (project, kind tab, item, source sheet, review view) to have its own URL, so that I can return to and share a place.
75. As the person, I want exactly four moments of delight (progress line and headline update on done; a marker fading and the item settling when a suggestion or disagreement is resolved; a calm empty state "Nothing needs you today. Last import 09:12."; a dismissible "what changed since your last visit" strip on first open) and no sounds, confetti, badges, points or streaks, so that satisfaction comes from progress, not manipulation.

Setup, operation and verification

76. As the person, I want `librarian doctor` to list every missing piece (Python version, whisper.cpp, ffmpeg, the Whisper models and the voice-activity model with SHA-256 checks, `claude` login and the no-training gate, the vendored Slack skill folder and a saved login that can make one read call, data folder) with its fix, so that install problems are clear.
77. As the person, I want the Librarian never to download anything at run time and models copied in by hand, so that the data flow stays explicit and offline for transcription.
78. As the person, I want data in a git-ignored `data/` folder in the clone (overridable with `LIBRARIAN_HOME`), so that work data is never committed.
79. As the person, I want `librarian backup <folder>` and `librarian restore <archive>` (snapshot, sessions, Slack list, config; refusing to overwrite non-empty data and archives newer than the code), so that deleting the clone is survivable.
80. As the person, I want `librarian install-skill` to symlink the skill and add a PATH shim, so that `git pull` updates what Claude uses.
81. As the person, I want `librarian serve` to run in the foreground on `127.0.0.1:8765` (port by flag), so that nothing autostarts.
82. As the person, I want pending migrations to run on start after an automatic database backup (last 3 kept), so that updates are safe.
83. As the person, I want extraction runs to record model, Claude Code version, prompt and schema hashes and the raw result, and the extract stage to refuse to call Claude until setup records a Team or Enterprise account type and my confirmation that work usage rules allow it, so that results are traceable and no work content leaves the machine under a plan that may train on it.
84. As the person, I want a verification checklist (`librarian verify` template) with one field per real-source criterion (see Real-source check) holding counts and verdicts only, so that I can check real sources on the Mac and share results with agents on Linux without sharing work data.
85. As the person, I want the Librarian to hold work data only in a Workspace with its own storage and queries that never cross Workspaces, so that a future personal Workspace cannot mix in.

## Implementation Decisions

Architecture
- Python 3.11+ for CLI, importers, whisper.cpp wrapper, Claude extraction runner and HTTP server. One package, `pyproject.toml`, a venv from a pinned lockfile, one `librarian` console command, no global installs. Numbered SQL migrations applied on start. Pytest and ruff behind one `make check`.
- Storage: one SQLite file per Workspace; only "work" exists but every source, record and search is Workspace-scoped from day one. Search is FTS5 (BM25) over normalised text: niqqud (U+0591 to U+05C7) stripped, geresh, gershayim and maqaf unified, Hebrew prefixes (ו ה ב ל מ ש כ and combinations) handled by query expansion. No embeddings in v1 (later bge-m3 with sqlite-vec behind a seam). A trigram table is added only if real data shows a recall gap.
- One shared `librarian.query` core returns plain typed results. The CLI and HTTP handlers only format them and never open SQLite directly. The core takes one filter (kind, state, project, since, basis, person).
- The UI is static HTML, CSS and ES modules served by the Python server with a JSON API; no build step, no CDN, no Node. Any graph library is vendored.

Memory model (three layers)
- Source items: immutable; identity is Workspace plus the source's stable id (Slack channel and message ts; session id and message id; Drive file id and segment number). A content hash detects edits; an edit is a new revision keeping the old.
- Records: rebuildable, produced by extraction. Node kinds: source item, person, project (optional parent; a workstream is a sub-project), action item (owner, stated deadline), decision (with reasoning), blocker, open question. Completed work is a done action item; a dependency is an edge.
- Person events: append-only log. The current view is the extracted Record with events applied. Re-extraction never touches events.
- Edges are typed (belongs-to, owner, waiting-on, blocks, supersedes, related-to, mentions, evidence), each with Evidence and correctable by an event. A Record can belong to any number of projects; none belonging shows as unassigned. Superseded or dropped Records keep their edges.
- State: lifecycle (open, pending with who or what it waits on, suspended with who and reason if given, done, dropped, superseded); Basis; commitment level for action items. Stale is computed at read time. Done needs completion Evidence or the person's mark.
- Every Record keeps its id across re-extraction because Claude is shown the candidate projects' existing Records (chosen as in Pipeline) and returns same, updated or new per id. The importer validates every id, edge end and Evidence quote against what it sent and drops and logs failures. Edges are extracted in the same pass as Records.
- Open items (decided with the person): one query in `librarian.query` serves both the `open-items` command and the UI stream, so they cannot disagree. It returns three groups, each Record carrying a `group` field. **Needs attention**: open (not pending, not suspended) action items, blockers and open questions owned by the person through a confirmed or stated link, plus those with no owner. Stale, contradicted or uncertain flags only raise items already in this set and never add other people's items. An item whose owner is only a Suggested link stays out. **Waiting on others**: open items pending on another person. **Other open**: every other open item, shown collapsed below the other two groups in the stream. The headline counts the first two groups ("N things need you, M waiting on someone else"). The progress line is action items done this week out of (done this week + the person's still open), with the week starting Sunday 00:00 local time.

Pipeline
- At most one Import per Workspace, held by a lock in the data folder. A second start from the CLI or UI is refused with a message and the running Import's progress; the UI button then shows that progress. SQLite runs in WAL mode so `serve` reads during an Import.
- Stages: fetch, transcribe, normalise, extract, link; each saves output so a failure resumes there. Transcription is its own stage.
- Extraction units: one Slack thread (loose messages grouped per channel-day), one Claude session (windowed if very long, window size the implementer's choice), or a transcript window of about 15 minutes. Before each call the importer picks candidate projects from (1) projects already linked to earlier items of the same conversation, session or recording and (2) projects whose name or alias appears in the unit's text, and sends their open and recently changed Records, capped at a size the implementer picks; with no candidates it sends the project list only. Every Record quotes its exact source span.
- Extraction runs `claude -p` with `--output-format json --json-schema`, tools disabled (`--tools ""`, MCP denied, `--strict-mcp-config`), `--safe-mode`, `--no-session-persistence`, a turn and budget limit, input on stdin, telemetry and non-essential traffic disabled, and a pinned full model id. A chunk is accepted only when the result subtype is success and structured output is present; dates and enums are validated by the importer. `--bare` is not used under a subscription login. Pin the Claude Code version and re-test the lockdown after each update. Raw envelopes are kept. 2 to 4 workers with backoff on rate-limit and overload errors and a resumable per-chunk queue.
- No-training gate: setup records the work account type and a "work usage rules allow this" confirmation in config. The extract stage refuses to call `claude` until both are set to an allowed value (Team or Enterprise) and prints the fix. Without them `librarian import` still fetches and transcribes, makes zero extraction calls and exits non-zero with the reason. `doctor` reports it as a failing piece.
- Linking: clear matches automatic; unsure ones Suggested links; accept or reject is a Person event. Strict person matching and project handling as in the user stories. "Unknown speaker" for unnamed first-person recording lines.

Sources
- Slack: the importer calls the Slack Web API directly, reusing the existing skill's login, paging and retry (copied on the Mac to a vendor folder, not in this repo), and stores the raw API message as the Source item. Field names (`ts`, `thread_ts`, `user`, `text`, `files`) are assumed from the public API and validated at run time; a mismatch fails the item visibly. The permalink is not a field of the raw message: it is built from the workspace domain, channel id and `ts`, or fetched read-only with `chat.getPermalink`. History and reply checks page past 200. The picked-conversation list is stored in the Workspace; `channels.json` only seeds it on first run.
- Sessions: `.jsonl` files under the Claude projects folder, all projects except the Librarian clone's own project folder, with tool calls and tool results of `librarian` commands and assistant text in turns that made such calls dropped before storing evidence, referenced by session id plus line offset plus timestamp; role, timestamp and tool names assumed from Claude Code's format and validated at run time.
- Recordings: files named `<title> - date time - Recording` with no extension, MP4, in a synced Drive folder (the `My Drive/Google Meet/...` folders and a flat `Meet Recordings/` folder). Reference is file path plus timestamp. Not-yet-local files are detected by comparing size with size on disk.
- Transcription sits behind one `transcribe(file) -> segments` interface (whisper.cpp with Metal; ivrit.ai ggml model with language forced to `he` for Hebrew and mixed recordings; stock large-v3-turbo ggml with `en` for English). Output has segment timestamps and per-token probabilities. A segment is flagged low confidence when average log probability is below -1.0, no-speech probability above 0.6 or compression ratio above 2.4 (starting thresholds, unvalidated). A word is marked uncertain when its whisper.cpp token probability is below a configurable starting threshold (0.5, unvalidated), mapped onto the Evidence quote's span; extraction is told which words are uncertain so its English gloss can name them. Extraction returns the gloss for each Evidence quote and it is stored with the Evidence; other lines in the source sheet show no gloss. A voice-activity pre-pass reduces hallucination on silence. No diarization in v1; adding it later is one stage after transcription. `tools/transcription-benchmark/` stays for a later engine swap.

Claude interface
- Read-only CLI with JSON output on the query core; commands open-items, project, changes, waiting, decision, blocked, search, show. One answer envelope for all: `records` (kind, title, lifecycle, basis, commitment level, owner, stated deadline, project links), `evidence` (source type, locator, short quote, role, retrieval time), `freshness` (last successful Import per source, stale flag and last-evidence date per Record). Contradictions return both Records, linked. The CLI returns facts only; Claude writes the prose, so there is no second stored summary. Exact field names and command options are the implementer's choice.
- The skill's `allowed-tools` lists only `Bash(librarian <command>:*)` for the eight answer commands. Every answer command opens the database read-only. Destructive admin commands (forget, restore over data) need a confirmation typed at an interactive terminal and refuse when stdin is not a terminal. The skill tells Claude to cite locators, label Basis, say stale, contradicted or no evidence found, ask on ambiguous projects, and states the never-do list. It forbids import, serve, backup, restore, forget and any direct source access.

UI behaviours as in the stories, and the three approved mock states (see Verification). The UI is in English; Hebrew content renders right-to-left; evidence quotes stay in the original language with an English gloss.

Real-source check (the person runs it on the Mac after the fixtures pass)
- Sample set, the person's pick: at least one Slack conversation, one Claude session, one Hebrew recording, one mixed Hebrew and English recording, and two sources about one project.
- Open items pass: no false items, at least 8 of 10 real open items listed, misses written down, confirmed and inferred labels right, stale items marked stale.
- Project status pass: each claim marked right, wrong or unsupported; no wrong claims; every evidence link opens the right passage; the latest decision and the main blocker are named or declared missing; "cannot find it" counts as honest.
- Transcription pass: a 2 to 3 minute stretch is readable, names and numbers are right or flagged, timestamps are within about 10 seconds, a 1-hour recording finishes in under 30 minutes, timings recorded.
- Import-twice check: a second Import changes no counts and keeps the person's events.
- `librarian verify` writes a template with one field per criterion above and counts and verdicts only, never source text. Results are kept as counts-only files in `verification/<date>.md`.

Setup
- Data in a git-ignored `data/` folder in the clone, overridable with `LIBRARIAN_HOME`. whisper.cpp and ffmpeg are installed by the person through Homebrew; ffmpeg decodes the extensionless MP4/AAC recordings to 16 kHz mono WAV before transcription; the voice-activity model (a Silero ggml model, URL and SHA-256 documented) and the Whisper models are copied in by hand with documented URLs and SHA-256 hashes, verified by `doctor`. `backup` writes one dated archive (consistent SQLite snapshot, session copies, Slack list, config; not models or recordings); `restore` refuses a non-empty data folder unless told, and refuses an archive with a newer migration number. Docs warn against a Drive-synced backup folder. `install-skill` symlinks the skill folder into the user skills folder and adds a PATH shim in `~/.local/bin`. `serve` binds loopback only, rejects any request whose `Host` is not `127.0.0.1:<port>` or `localhost:<port>`, rejects writes whose `Origin` is not the same origin, accepts only `application/json` request bodies, and requires a random token generated per `serve` run that the page receives and sends on every API call (403 otherwise). Install is clone, `make install`, `librarian doctor`; update is `git pull`, `make install`.
- Implementer's choice: config file name and format and key names; the database and table names; the name and format of the "last visit" marker for the changes strip; the default per-source import staleness threshold (configurable); the session windowing size; the week boundary for the progress line; search ranking details among records; names of CLI flags not given here.

## Testing Decisions

- Good tests check external behaviour only: what the CLI prints, what the HTTP API returns, what the UI shows, what is on disk after an Import. They never assert on internal tables, module structure or prompts.
- Seams (the highest available): (1) the `librarian` CLI, covering Import, answer commands and admin commands against a temporary Workspace; (2) the HTTP JSON API plus static UI served by `librarian serve` over a fixture Workspace, driven in a real browser for the UI and mock states. Both sit on the one query core, so the core needs no separate seam. Real transcription, extraction and Slack are replaced by fakes behind their interfaces: transcription reads a sidecar transcript next to a placeholder audio file; extraction returns canned schema-valid JSON (and canned bad JSON, bad ids and invented quotes to test rejection); Slack replays recorded-shape JSON pages. Linux tests never call `claude -p`. The person confirmed both seams during the design review.
- Fixture set: made-up English, Hebrew and mixed data copying the real source formats, built by a script. It must include a cross-source project, a date disagreement between Slack and a recording, an uncertain Hebrew passage, unnamed first-person speech, a deleted Slack message, an edited Slack message, an ambiguous project name, a stale item and an item with no owner.
- A Mac-only smoke test runs the real whisper.cpp and Claude on one short clip. Its result is not required on Linux.
- Prior art: only the self-test of the transcription benchmark tool exists; the rest is new.
- Real-source check on the Mac follows the fixture tests: failures found there become new fixture cases. The criteria are in Implementation Decisions, Real-source check.

## Verification

This project is not gx, so entries use the project's own `librarian ...` commands, the fixture set and the Mac real-source check from the verification plan, not gx flow-catalog flows. Verify against a temporary Workspace folder (`LIBRARIAN_HOME` set to a temp folder) loaded with the fixture set. "Fixture" means the made-up set; "Mac check" means the person's real-source check, recorded in `verification/<date>.md` as counts only.

1. `librarian import` run by hand; exit 0, per-source counts printed. Fixture.
2. Import button in the UI import panel starts an Import, progress shows, counts match the CLI. Starting an Import from the UI while a CLI Import runs is refused, shows its progress, and makes no extra calls (call count unchanged); the UI keeps answering reads during the Import. New flow: UI import test.
3. Stage-resume test: fail the extract stage with a fake error, rerun; fetch and transcribe are not redone (stage counters). New fixture: failing extractor.
4. Run `librarian import` twice; record and source counts are identical and a Person event survives. Also done on the Mac.
5. Change one fixture message and rerun; only that item is re-extracted (call count 1). New fixture: edited message.
6. Edited message: `librarian show` lists both revisions. New fixture: edited message.
7. Failing item shows stage and error in the import panel and in the CLI; the next Import retries only it. New fixture: failing extractor.
8. Progress counters (fetched, transcribed, extracted, failed) present in CLI output and the panel.
9. `librarian import --max-calls 2`: exactly 2 calls, newest first, clean exit, next run continues. Flag name is the implementer's choice.
10. `librarian import --dry-run` prints the call count and makes no calls.
11. After the fake transcription stage is paused, `librarian search` finds Slack and session text.
12. `librarian slack pick` lists conversations with name, kind, member count; nothing is imported until picked. New fixture: replayed Slack conversation list.
13. A pick made in the UI panel appears in the CLI list and the reverse.
14. First Import covers 30 days only; `import older` shows a dry-run count first. New fixture: Slack history older than 30 days.
15. Re-check of 7 days picks up an edit and a deletion in the replayed pages.
16. Unpick keeps items; a deleted message shows "gone from Slack" with Evidence intact.
17. "Forget conversation" asks for confirmation, deletes its items and orphaned Records, and logs a Person event.
18. Fake Slack records no write calls (assert zero posts, reactions or marks).
19. Source item shows conversation name and kind in `show` output.
20. Fake extractor receives only items of picked conversations; the panel text says so.
21. Fixture sessions are copied into the store and still searchable after the original is removed. A fixture session holding a `librarian open-items` result plus a user line "the cutover moved to Dec 1" yields evidence from the user line only, and a stale fixture item stays stale. A session in the Librarian clone's own folder is skipped.
22. Placeholder recording smaller than its on-disk size is reported not-yet-local and not transcribed. New fixture: partial file.
23. Real engine only: Mac check, a Hebrew and a mixed recording transcribed with no network (transcription pass in the plan); Mac-only smoke test.
24. Fake transcription: language flag, detection fallback and CLI override choose the expected model (assert the call).
25. Transcript segments in `show` output have timestamps; Mac check: timestamps within about 10 seconds of the audio.
26. A low-confidence fixture segment is flagged; look check in the `source-sheet-hebrew` Mock state.
27. A recording transcribed twice with the same file hash runs the transcribe stage once.
28. Fixture Slack user id links to its Person with no review entry.
29. Fixture text name matching two Aliases becomes a Suggested link, shown with "unconfirmed person"; `librarian open-items` marks the owner as unconfirmed.
30. Accept the suggestion in the UI; rerun Import; the name links automatically.
31. Move and split an Alias from the person node's menu in Relations and from a Review list row; a Person event is logged and the next Import keeps it.
32. A first-person fixture line yields owner "unknown speaker" and a review entry.
33. Set the speaker from a transcript line in the source sheet; re-run transcription and extraction; the setting persists and the owner updates.
34. Fixture config lists "me" names, including a Hebrew spelling; items by those names show as Yours.
35. A fixture extraction that creates a new project shows it inferred in the Review list; confirm, rename, merge and split each work from the project's status header.
36. Merge two projects, rerun Import; the merge persists and the old name lands on the merged project.
37. Importer never merges on its own; a similar-name fixture yields only a suggestion.
38. Exact project-name fixture links automatically; a near-name fixture yields a Suggested link.
39. Every Record in a fixture `librarian project` answer has at least one Evidence entry with locator, quote and role.
40. Fixture extractor returns an invented quote, a bad id and a bad edge end; all are dropped and logged, none stored.
41. Record fields (lifecycle, basis, commitment) appear in answer JSON and in the expanded item; look check in `stream-expanded` (basis-inferred).
42. A fixture task with no completion evidence stays open; `librarian open-items` lists it.
43. A fixture item with old Evidence shows stale in answer JSON and in the UI; changing the threshold in config changes the result.
44. The date disagreement fixture shows both Records linked, in answer JSON and in the UI; look check in `stream-expanded`. On the expanded item, choosing one Record supersedes the other with a Person event, and "both wrong" marks both; the Import does not undo either. Moving a Record to another project works from the expanded item and survives an Import.
45. Re-extract with changed text; Record ids are unchanged. A fixture recording about a project that already exists from Slack re-uses the existing Record id and mints no new inferred project.
46. A corrected Record that the fake extractor stops producing is flagged "no longer found in sources".
47. Mark done, reopen and change owner in the UI; history appears on the item; Import does not undo them; `librarian changes` reflects them.
48. Freshness line present on every UI view and in every CLI answer; look check in `stream-expanded` (freshness).
49. `librarian open-items` on the fixture returns exactly the known open items (no false ones), each with its group (Needs attention, Waiting on others, Other open) and the same set the UI stream shows; a suggested-owner item is absent from Needs attention; the progress line matches the week rule. Mac check: no false items, at least 8 of 10 real ones, labels right, stale marked; real Claude session answers through the skill.
50. `librarian project <name>` returns status, owners, deadlines, latest decision, main blocker or "not found"; Mac check: no wrong claims and all evidence links work.
51. Each named command returns the envelope on the fixture; `changes`, `waiting`, `decision` and `blocked` have an expected-answer test each.
52. A schema check on the envelope from every command (records, evidence, freshness).
53. An ambiguous project fixture name returns candidates (name, parent, last activity); a clear winner returns one; the answer names the resolved project.
54. `librarian changes` states the meeting and date used; with no meeting it states the 7-day fallback. New fixture: a project with no recording.
55. With one source never imported, the answer starts with that fact.
56. Answer JSON carries basis and stale/contradicted flags; Mac check: Claude's wording in a real session.
57. `librarian show <locator>` returns the surrounding source items, with the evidence one marked.
58. The skill file's allowed list contains only the eight answer commands; each answer command opens the database read-only (a write attempt through it fails); `librarian forget` and `restore` over data refuse with no terminal on stdin; a prompt-injection fixture message changes no record.
59. Mac check: Claude suggests marking done only in text, via the installed skill.
60. `librarian serve` binds only 127.0.0.1 and the page loads without a login. A request with a foreign Host or Origin, a non-JSON write body, or no token gets 403 and changes nothing.
61. Look check in `stream-expanded` (date-line, headline, progress-line); marking an item done updates the count and line.
62. Look check in `stream-expanded` (project-filter); selecting a project shows the status header and filters the stream.
63. Kind tabs filter the stream; Done lists finished items with evidence.
64. Look check in `stream-expanded` (item-expanded, basis-inferred); warnings render as in the mock.
65. Look check in `stream-expanded` (expanded-tabs) and `relations-graph` (expanded-tabs).
66. Click an evidence quote; look check in `source-sheet-hebrew` (source-sheet, evidence-line). "Open original" works for all three: a Slack fixture message yields a permalink (the fixture raw message has no permalink field and still validates); a recording opens in the in-page player at the segment's timestamp, with range requests answered 206; a session opens its copied passage as a raw view.
67. Look check in `source-sheet-hebrew` (uncertain-underline, right-to-left quote and gloss); Hebrew quotes and gloss render correctly. The gloss is labelled as machine translation, and the `onboarding-hebrew` fixture's token probabilities put the underline on the uncertain word and the gloss names it.
68. Look check in `relations-graph` (relations-graph, hop-control); 1, 2 and 3 hops, edge-kind filter and click-to-re-centre work. The person approved this state as is.
69. Press `/` focuses search on every view; a Hebrew prefixed form (for example הפגישה for פגישה) finds the fixture record; records come before source passages; results open in place.
70. Freshness line opens the import panel with all listed parts; progress shows during an Import.
71. The "N to review" count opens the Review list; Accept and Reject work; the "suggested" marker shows inline; suggestions are absent from Needs attention.
72. Same as 47.
73. Owner and waiting-on filters by person work; Relations shows the person node; no person page route exists.
74. Each view reloads from its URL to the same state.
75. Delight moments each triggered by the fixture (done, resolve, empty state, first-open strip); none of the banned elements exist. New flow: UI delight test.
76. `librarian doctor` on a fixture machine with one piece missing names it and its fix; exit code non-zero. It covers ffmpeg, the VAD model hash, the Slack vendor folder and one saved-login read call, and the no-training gate. Mac check: all pieces pass.
77. A network-blocked run of the fake pipeline succeeds; no download code path is invoked at run time.
78. `data/` is git-ignored; `LIBRARIAN_HOME` moves it.
79. Backup then restore into an empty folder gives identical answers; restore refuses a non-empty folder and a newer archive.
80. `librarian install-skill` creates the symlink and shim; a second run is harmless.
81. `librarian serve --port` changes the port; the process stays in the foreground.
82. A migration test: an old database is backed up (last 3 kept), then migrated on start.
83. The extraction run record holds model, version, prompt hash, schema hash and the raw envelope. Real run only on the Mac check. Gate test: with the account type unset or set to Pro, `librarian import` fetches and transcribes, makes zero extraction calls and exits non-zero with the reason; `librarian doctor` fails on it.
84. `librarian verify` writes a template with one field per Real-source check criterion (sample-set minimum, open-items, project status, transcription, import-twice) and no source text (grep fixture strings in the output: none).
85. Queries given another Workspace name return nothing and never read the work file; a second fixture Workspace shares no results.

Mock states (stored mock directory `$(gx tickets root)/the-librarian/real-design/mocks/`; full path `/root/.local/share/gx/tickets/the-librarian/real-design/mocks/08-visual-direction.html`):

- `/root/.local/share/gx/tickets/the-librarian/real-design/mocks/08-visual-direction.html`, state `stream-expanded`, width 1100, fixture scenario `payments-cutover`, parts: date-line, headline, progress-line, project-filter, freshness, item-expanded, basis-inferred, expanded-tabs.
- `/root/.local/share/gx/tickets/the-librarian/real-design/mocks/08-visual-direction.html`, state `source-sheet-hebrew`, width 1100, fixture scenario `onboarding-hebrew`, parts: source-sheet, evidence-line, uncertain-underline.
- `/root/.local/share/gx/tickets/the-librarian/real-design/mocks/08-visual-direction.html`, state `relations-graph`, width 1100, fixture scenario `payments-cutover`, parts: expanded-tabs, relations-graph, hop-control.

New fixture scenarios to write (none exist yet): `payments-cutover` (Payments migration project; Slack "Nov 18" versus recording "Nov 25 to be safe" at 00:41:10; a blocker; a decision "Keep webhook v1"; person Raz; two uncited future items), `onboarding-hebrew` (Hebrew recording with the signup copy item, uncertain "Thursday" at 00:09:14 (its fixture transcript carries token probabilities for the uncertain words), an ownerless legal question not mentioned since Oct 22). Also to write: failing extractor, edited message, partial file, Slack history older than 30 days, replayed Slack conversation list, project with no recording, prompt-injection message, and the UI import, UI delight and UI Relations-graph tests.

## Out of Scope

- A personal Workspace, personal sources and a Workspace switcher.
- Writing to any source system (posting, editing, closing).
- Scheduled or background Imports.
- A native Mac app, multiple users, login.
- An MCP server (the shared query core allows it later).
- Paid or cloud transcription.
- Automatic speaker separation (diarization), a person page, and semantic or embedding search.
- Measured transcription accuracy and speed as an engine-selection gate: the engine was chosen without a benchmark; the real-source check is the first measurement.

## Further Notes

- Content of picked conversations, sessions and transcripts leaves the machine for the extraction step only, through the work Claude account. The no-training gate blocks extraction until the account type and the work usage rules (DMs included) are confirmed in setup. Only transcription is guaranteed local.
- Source field shapes for Slack and sessions were never seen, so they are assumed and validated at run time; fix mismatches as fixture cases.
- Hebrew and mixed-language extraction quality is untested. Transcription of Hebrew speech with English words, and of poor audio, is expected to be weaker.
- Research notes live on branches `research/local-transcription-engines`, `research/local-storage-and-search` and `research/claude-headless-extraction`.
- Real work data never reaches agents; the Mac check returns counts only.
