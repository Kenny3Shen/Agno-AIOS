from datetime import datetime, timezone

from api.services.workflow_cron import _cron_due


def test_cron_due_every_minute():
    # last run 2 minutes ago, expression every minute → due
    now = datetime(2026, 1, 1, 12, 5, 0, tzinfo=timezone.utc).timestamp()
    last = datetime(2026, 1, 1, 12, 3, 0, tzinfo=timezone.utc).timestamp()
    assert _cron_due("* * * * *", last, now) is True


def test_cron_not_due_future():
    now = datetime(2026, 1, 1, 12, 0, 10, tzinfo=timezone.utc).timestamp()
    last = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).timestamp()
    # just fired at 12:00; next is 12:01
    assert _cron_due("* * * * *", last, now) is False


def test_invalid_cron():
    assert _cron_due("not a cron", 0, 1_700_000_000) is False
