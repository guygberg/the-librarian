from librarian import config, gate
from librarian.tty import require_terminal

help = "Record the work account type, usage-rules confirmation and the names that mean you"


def add_arguments(parser):
    pass


def _ask(prompt: str, current: str, valid=None) -> str:
    """Empty answer keeps `current`; an invalid answer asks again. EOF aborts."""
    while True:
        shown = f" [{current}]" if current else ""
        try:
            answer = input(f"{prompt}{shown}: ").strip()
        except EOFError:
            raise SystemExit("librarian: setup aborted, nothing saved") from None
        answer = answer or current
        if answer and (valid is None or valid(answer)):
            return answer
        print("  not a valid answer")


def _yes_no(answer: str) -> bool:
    return answer.lower() in ("y", "yes", "n", "no")


def run(args, ctx):
    require_terminal()
    cfg = ctx.config
    account = _ask(
        f"Work account type ({', '.join(gate.ACCOUNT_TYPES)})",
        cfg.get("account_type", ""),
        lambda a: a.lower() in gate.ACCOUNT_TYPES,
    ).lower()
    current_yes = {True: "yes", False: "no"}.get(cfg.get("usage_rules_confirmed"), "")
    confirmed = _ask("Do your work usage rules allow this? (yes/no)", current_yes, _yes_no)
    names = ", ".join(cfg.get("me_names", []))
    try:
        extra = input(f"Extra names that mean you, comma separated [{names}]: ").strip()
    except EOFError:
        raise SystemExit("librarian: setup aborted, nothing saved") from None
    me_names = (
        [n.strip() for n in extra.split(",") if n.strip()] if extra else cfg.get("me_names", [])
    )
    config.save(
        {
            "account_type": account,
            "usage_rules_confirmed": confirmed.lower() in ("y", "yes"),
            "me_names": me_names,
        }
    )
    print(f"account type: {account}")
    print(f"usage rules allow this: {'yes' if confirmed.lower() in ('y', 'yes') else 'no'}")
    print(f"me names: {', '.join(me_names) or '(none)'}")
    status = gate.training_gate_status(config.load())
    print("extraction: allowed" if status.allowed else f"extraction: blocked, {status.reason}")
    return 0
