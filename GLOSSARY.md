# The Librarian

A connected work memory bank. It imports work discussions from several sources, connects them, and serves the same records to Claude and to a person.

## Language

**Workspace**:
A sealed partition of the memory bank, such as "work". Every source, record and search belongs to exactly one workspace, and nothing crosses between workspaces.
_Avoid_: Profile, tenant, context

**Work computer**:
The Mac where the Librarian runs and where the real sources are reachable. Not the machine the Librarian is built on.
_Avoid_: Host, local machine
