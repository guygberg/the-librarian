# Mission Control lime UI — review package

Revision tested: the commit this package is committed on (`git log -1 -- docs/review`). The
screens in `screens/` were captured from `librarian serve` over a temporary fixture Workspace,
by `tests/ui/test_journey.py`. The canonical reference, `docs/reference/mission-control-lime.html`,
was captured at the same two widths into `canonical/` for side-by-side review.

## Run it

```
librarian serve            # http://127.0.0.1:8765/   (loopback only; --port N to change)
```

Routes: `/` Today, `/items` (`?view=board`, filters in the URL), `/items/<id>` (`?tab=activity|sources|relations`),
`/people`, `/projects`, `/review`, `/import`. Nothing is deployed and the work-Mac installation is untouched.

To regenerate the screens (fixture Workspace, no real data):

```
LIBRARIAN_SHOTS=docs/review/screens .venv/bin/pytest tests/ui/test_journey.py
```

## Results

| Check | Result |
| --- | --- |
| `ruff check src tests tools` | pass |
| Full `pytest` | 490 passed, 2 skipped, 0 failed |
| `tests/ui/test_journey.py` (desktop 1280 and phone 390; plus recording at its timestamp on both) | 4 passed |
| HTTP security: foreign host refused, token required, origin and content-type checked on writes, media cookie only on media GET, loopback bind (`tests/server/test_serve.py`, `test_media.py`) | pass, part of the full run |

The journey covers: Today counts and the recommended item; List and Board; Project, Person, kind
and lifecycle filters; Overview, Activity, Sources and Relations; Evidence in the source sheet;
playing a recording at its timestamp; completing and undoing; People and Projects; accepting a
Review suggestion; Import with a dry run; reloading a deep URL.

## Screens

Product (`screens/<desktop|phone>-<name>.png`): today, items-list, items-board, item-detail,
source-sheet, relations, people, projects, review, import.

## How the product follows the canonical HTML

The pages use the canonical file's own markup and its stylesheet, copied unchanged into
`src/librarian/server/static/mission.css`. Product-only parts (source sheet, Relations graph,
Import, corrections) are in `app.css`, drawn with the same components.

Where the mock shows invented data, the same slot shows the nearest real thing:

| Mock | Product |
| --- | --- |
| Level, XP and streak panel | This week's progress: "N of M items finished this week" |
| Daily quests | Sources: Freshness per source, each opening Import |
| Tags page, tag chips, Tags filter | Projects |
| Suggestions | Review |
| "Status & priority" filter, "Priority" sort and badge | Lifecycle filter; "Ranked" (the query's own order); the item's first warning |
| New item, Add person, New tag buttons | Import (Records only come from sources); none on People and Projects |
| Sound toggle | Import button |
| Reset demo data, "Interactive mock" label | Import sources; date and Workspace |
| Checklist, private notes, "Latest conversation" | "Where it stands" facts; latest Evidence quote |
| Favorites tabs and stars | Left out |
| Source preview dialog | The bottom source sheet, with its own URL |

## Known limitations

- The mock's light mode paints buttons charcoal and is unreadable; `app.css` corrects that.
- "Other open" is no longer a collapsed group: open items are one ranked table (needs you,
  waiting, other open), 7 to a page, as in the mock.
- There is no person panel; a person's card opens the Items list narrowed to them.
- On the Board the Basis and Warning filters can be cleared from the banner but not changed;
  they are on the List toolbar.
- Two tests in the full run are skipped by their own markers; they are not part of this UI.
- Screens use the fixture Workspace; layout with a large real Workspace has not been captured.
