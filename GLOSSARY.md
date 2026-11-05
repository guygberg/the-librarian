# The Librarian

A connected work memory bank. It imports work discussions from several sources, connects them, and serves the same records to Claude and to a person.

## Language

**Workspace**:
A sealed partition of the memory bank, such as "work". Every source, record and search belongs to exactly one workspace, and nothing crosses between workspaces.
_Avoid_: Profile, tenant, context

**Work computer**:
The Mac where the Librarian runs and where the real sources are reachable. Not the machine the Librarian is built on.
_Avoid_: Host, local machine

**Source item**:
One raw unit from a source, such as a Slack message, a Claude session passage or a transcript segment. Never edited by the Librarian.
_Avoid_: Document, raw record

**Record**:
A thing the Librarian extracted from source items, such as a project, action item, decision, blocker or open question. Records can be rebuilt; the person's changes to them are kept apart.
_Avoid_: Entry, note

**Link**:
A typed connection between two records, or between a record and a source item (its evidence). Links carry their own evidence and history.
_Avoid_: Relation, reference

**Person**:
Someone who owns, requests or is mentioned in work, including the person using the Librarian. Known by one or more aliases.
_Avoid_: User, contact

**Alias**:
A name or id a source uses for a person, such as a Slack user id or a first name in a transcript. One alias belongs to one person.
_Avoid_: Nickname, handle

**Suggested link**:
A link the importer is unsure about. It waits in the review list and never counts as confirmed until the person accepts it.
_Avoid_: Pending match, guess

**Evidence**:
The link from a record to a source item that supports, completes or contradicts it, with a locator and a short verbatim quote. Every record has at least one.
_Avoid_: Citation, proof

**Basis**:
How firmly a record's state is known: stated (a source says it), inferred (Claude concluded it) or confirmed (the person confirmed it in the Librarian).
_Avoid_: Confidence, certainty

**Person event**:
An entry in the append-only log of the person's own changes: a status change, correction, merge, dismissal, speaker setting, or accepted or rejected suggestion. Re-import never touches it.
_Avoid_: Edit, override

**Freshness**:
When each source was last imported successfully. Shown on every view and in every answer.
_Avoid_: Sync status

**Stale**:
A record with no recent evidence, computed when read from per-kind thresholds. It is not a stored state, and it never means done.
_Avoid_: Old, expired

**Needs attention**:
The stream group of open items that want the person: their own open action items, open items with no owner, and any open item that is stale, contradicted or flagged uncertain. Items waiting on someone else and suggested links are not in it.
_Avoid_: Inbox, todo

**Review list**:
The place where every suggested link and every inferred project waits for the person to accept, reject or rename it.
_Avoid_: Queue, inbox

**Import**:
One manual run of the five stages (fetch, transcribe, normalise, extract, link) over the sources. Idempotent: it updates and never duplicates.
_Avoid_: Sync, scrape
