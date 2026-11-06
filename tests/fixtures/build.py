"""Build the made-up fixture set: `python tests/fixtures/build.py [--scenario NAME] OUT_DIR`.

A scenario is any module in the scenarios dir exposing `build(target)`; the file stem is its name.
"""

import argparse
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))  # so scenarios can `import fixtures.formats`

SCENARIOS_DIR = HERE / "scenarios"


# The spec's fixture set and extras, each with the scenario that provides it
# (tests/fixtures/test_build.py checks it).
MANIFEST = {
    "cross-source project": "base",
    "date disagreement": "payments_cutover",
    "uncertain Hebrew passage": "onboarding_hebrew",
    "unnamed first-person speech": "people_aliases",
    "deleted Slack message": "slack_deleted_message",
    "edited Slack message": "slack_edited_message",
    "ambiguous project name": "projects_stable_ids",
    "stale item": "stale_and_ownerless",
    "ownerless item": "onboarding_hebrew",
    "failing extractor": "extractor_failure",
    "partial file": "recording_partial",
    "Slack history older than 30 days": "slack_history_older",
    "replayed conversation list": "slack_conversation_list",
    "project with no recording": "project_slack_only",
    "prompt-injection message": "slack_prompt_injection",
}


def discover(scenarios_dir: Path = SCENARIOS_DIR) -> dict:
    found = {}
    for path in sorted(scenarios_dir.glob("*.py")):
        if path.stem.startswith("_"):
            continue
        spec = importlib.util.spec_from_file_location(f"_scenario_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        if callable(getattr(module, "build", None)):
            found[path.stem] = module.build
    return found


def build(target: Path, scenario: str = "base", scenarios_dir: Path = SCENARIOS_DIR) -> None:
    scenarios = discover(scenarios_dir)
    scenario = scenario.replace(
        "-", "_"
    )  # the UI scenarios are named `payments-cutover`, `onboarding-hebrew`
    if scenario not in scenarios:
        raise KeyError(f"unknown scenario {scenario!r}; known: {', '.join(scenarios) or 'none'}")
    target.mkdir(parents=True, exist_ok=True)
    scenarios[scenario](target)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--scenario", default="base")
    parser.add_argument("--scenarios-dir", type=Path, default=SCENARIOS_DIR)
    args = parser.parse_args(argv)
    try:
        build(args.target, args.scenario, args.scenarios_dir)
    except KeyError as err:
        print(err.args[0], file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
