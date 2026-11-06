import json
from collections import Counter

from librarian import db
from librarian.extract import runs

help = "Print extraction runs with their rejection counts and reasons (read-only)"


def add_arguments(parser):
    parser.add_argument(
        "--json", action="store_true", help="full records, including the raw envelope"
    )


def run(args, ctx):
    try:
        conn = db.connect_ro(ctx.workspace)
    except db.SchemaOutdated as err:
        message = f"{err}; run `librarian serve` or `librarian import` to update it"
        print(json.dumps({"error": {"code": "schema_outdated", "message": message}}))
        return 1
    with conn:
        found = runs.list_runs(conn, ctx.workspace)
    if args.json:
        print(json.dumps(found, indent=2, ensure_ascii=False))
        return 0
    for r in found:
        reasons = ", ".join(
            f"{n} {reason}" for reason, n in Counter(x["reason"] for x in r["rejected"]).items()
        )
        print(
            f"{r['id']}\t{r['unit_key']}\t{r['model']}\t{r['claude_code_version']}"
            f"\taccepted {r['accepted_records']}\trejected {len(r['rejected'])}"
            + (f" ({reasons})" if reasons else "")
        )
        for x in r["rejected"]:
            print(f"    {x['piece']}: {x['reason']} {x['detail']}".rstrip())
    return 0
