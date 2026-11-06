import re

from fixtures.build import build
from support.cli import run_librarian

# One field per criterion of the spec's Real-source check, by section.
FIELDS = {
    "Sample set": 5,
    "Open items pass": 6,
    "Project status pass": 6,
    "Transcription pass": 4,
    "Import-twice check": 2,
}


def fixture_strings(root):
    found = set()
    for path in root.rglob("*"):
        if path.is_file():
            text = path.read_text(errors="ignore")
            found.update(re.findall(r'"([^"\\]{12,})"', text))
            found.update(line.strip() for line in text.splitlines() if len(line.strip()) >= 12)
    return found


def test_verify_writes_one_field_per_criterion(home):
    result = run_librarian(["verify"], home, env={"LIBRARIAN_NOW": "1700000000"})
    assert result.returncode == 0
    written = home / "verification" / "2023-11-14.md"
    assert result.stdout.strip() == str(written.resolve())
    sections = {}
    current = None
    for line in written.read_text().splitlines():
        if line.startswith("## "):
            current = sections.setdefault(line[3:], [])
        elif line.startswith("- ") and current is not None:
            current.append(line)
    assert {name: len(fields) for name, fields in sections.items()} == FIELDS


def test_verify_output_holds_no_fixture_text(tmp_path, home):
    for scenario in ("payments-cutover", "slack-hebrew", "onboarding-hebrew"):
        build(tmp_path / scenario, scenario)
    strings = set().union(*(fixture_strings(tmp_path / s) for s in ("payments-cutover", "slack-hebrew", "onboarding-hebrew")))
    assert len(strings) > 20
    run_librarian(["verify"], home)
    written = next((home / "verification").glob("*.md")).read_text()
    assert [s for s in strings if s in written] == []


def test_verify_does_not_overwrite_a_filled_in_file(home):
    env = {"LIBRARIAN_NOW": "1700000000"}
    run_librarian(["verify"], home, env=env)
    target = home / "verification" / "2023-11-14.md"
    target.write_text("filled in")
    again = run_librarian(["verify"], home, env=env)
    assert again.returncode == 1
    assert target.read_text() == "filled in"
