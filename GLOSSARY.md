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
