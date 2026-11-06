import argparse

from librarian import doctor

help = "Check every install piece (read-only) and print each missing one with its fix; exits 1 if any fail"

DESCRIPTION = f"""\
Checks: Python, ffmpeg, whisper.cpp (at least {'.'.join(map(str, doctor.MIN_WHISPER_CPP))}, and `--vad` accepted),
the Whisper and voice-activity models, the `claude` login, the no-training gate, the vendored Slack skill
folder (config `slack_vendor_dir`, default <data>/vendor/slack) with one Slack read call, and the data folder.

Models are never downloaded: copy them in by hand. Each model's name, URL and expected SHA-256 are in
models.manifest.json in the repo; an empty hash is reported as a failure until you run `shasum -a 256` and record it.
"""


def add_arguments(parser):
    parser.description = DESCRIPTION
    parser.formatter_class = argparse.RawDescriptionHelpFormatter


def run(args, ctx):
    checks = doctor.run_checks(ctx.config)
    for check in checks:
        if check.ok:
            print(f"ok    {check.name}" + (f" ({check.detail})" if check.detail else ""))
        else:
            print(f"FAIL  {check.name}: {check.detail}\n      fix: {check.fix}")
    return 0 if all(c.ok for c in checks) else 1
