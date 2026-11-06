import argparse
import importlib
import pkgutil
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from librarian import commands, config, paths


@dataclass(frozen=True)
class Context:
    workspace: str
    home: Path
    workspace_dir: Path
    config: dict[str, Any]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="librarian")
    parser.add_argument("--workspace", default=paths.DEFAULT_WORKSPACE)
    sub = parser.add_subparsers(dest="command", metavar="<command>")
    for info in pkgutil.iter_modules(commands.__path__):
        module = importlib.import_module(f"{commands.__name__}.{info.name}")
        cmd = sub.add_parser(info.name.replace("_", "-"), help=module.help)
        module.add_arguments(cmd)
        cmd.set_defaults(run=module.run)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "run", None):
        parser.print_help()
        return 0
    ctx = Context(
        workspace=args.workspace,
        home=paths.data_home(),
        workspace_dir=paths.workspace_dir(args.workspace),
        config=config.load(),
    )
    return args.run(args, ctx)


if __name__ == "__main__":
    sys.exit(main())
