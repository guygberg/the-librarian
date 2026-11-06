from datetime import datetime

from librarian.clock import utc_now_iso
from librarian.link.names import key


def test_utc_now_iso_is_timezone_aware_utc():
    stamp = utc_now_iso()
    assert stamp.endswith("+00:00")
    assert datetime.fromisoformat(stamp).utcoffset().total_seconds() == 0


def test_key_folds_case_and_whitespace_only():
    assert key("  Atlas \t Migration\n") == key("atlas migration") == "atlas migration"
    assert key("Atlas Migrations") != key("Atlas Migration")
