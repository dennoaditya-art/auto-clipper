from __future__ import annotations

from datetime import datetime, timedelta, timezone

from autoclip.publish import schedule_slot

UPLOAD = type(
    "U",
    (),
    {
        "slots": ("06:30", "12:30", "19:30", "21:00"),
        "utc_offset_hours": 7.0,
        "schedule_start": "",
        "schedule_interval_hours": 6.0,
    },
)
SETTINGS = type("S", (), {"upload": UPLOAD})()


def test_slots_are_local_wib_and_ascending():
    times = [schedule_slot(SETTINGS, i) for i in range(4)]
    moments = [datetime.fromisoformat(t.replace("Z", "+00:00")) for t in times]
    assert moments == sorted(moments)
    assert all(m > datetime.now(timezone.utc) for m in moments)
    for moment in moments:
        local = moment.astimezone(timezone(timedelta(hours=7)))
        assert local.strftime("%H:%M") in UPLOAD.slots


def test_after_last_slot_rolls_to_next_day():
    first = datetime.fromisoformat(schedule_slot(SETTINGS, 0).replace("Z", "+00:00"))
    last = datetime.fromisoformat(schedule_slot(SETTINGS, 3).replace("Z", "+00:00"))
    assert (last - first) < timedelta(hours=30)
