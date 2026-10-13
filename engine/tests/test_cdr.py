from datetime import datetime

import pytest

from wfm_engine.cdr import (
    CallRowError,
    agent_login,
    parse_call_row,
    parse_duration_s,
    parse_timestamp,
)


def good_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "Call ID": 70450076,
        "Call Type": "INBOUND",
        "Queue": "QueueA",
        "Agent": "Test Agent (Agent007)",
        "Start Time": "2026-05-31 19:54:17",
        "Queue Time": "2026-05-31 19:54:40",
        "Agent Time": "2026-05-31 19:54:54",
        "Hangup Time": "2026-05-31 19:57:51",
        "Call Duration": "00:03:34",
        "Agent Duration": "00:02:57",
        "Queue Wait Time": "0:00:14",
        "Disposition Duration": "00:00:20",
        "Total Hold Duration": "00:00:05",
        "Call Status": "Agent",
        "Hangup By": "user",
    }
    row.update(overrides)
    return row


class TestDurations:
    @pytest.mark.parametrize(
        ("text", "seconds"),
        [
            ("00:00:00", 0),
            ("0:07:05", 425),  # the ACD sometimes drops the leading zero of the hour
            ("00:03:34", 214),
            ("01:00:01", 3601),
            ("100:00:00", 360000),
        ],
    )
    def test_reads_hh_mm_ss(self, text: str, seconds: int) -> None:
        assert parse_duration_s(text) == seconds

    @pytest.mark.parametrize("blank", [None, "", "   "])
    def test_blank_is_none_not_zero(self, blank: object) -> None:
        assert parse_duration_s(blank) is None

    @pytest.mark.parametrize("bad", ["abc", "12:61:00", "00:00", "-1:00:00", 12.5, 90])
    def test_rejects_anything_else(self, bad: object) -> None:
        with pytest.raises(CallRowError) as caught:
            parse_duration_s(bad)
        assert caught.value.code == "duration.unreadable"


class TestTimestamps:
    def test_reads_the_acd_format(self) -> None:
        assert parse_timestamp("2026-05-31 21:43:04") == datetime(2026, 5, 31, 21, 43, 4)

    def test_the_all_zero_date_means_no_value(self) -> None:
        assert parse_timestamp("0000-00-00 00:00:00") is None

    @pytest.mark.parametrize("blank", [None, "", "  "])
    def test_blank_is_none(self, blank: object) -> None:
        assert parse_timestamp(blank) is None

    def test_a_real_datetime_loses_zone_and_microseconds(self) -> None:
        assert parse_timestamp(datetime(2026, 5, 1, 8, 0, 0, 999)) == datetime(2026, 5, 1, 8, 0, 0)

    @pytest.mark.parametrize("bad", ["31/05/2026 21:43", "2026-13-01 00:00:00", 12345])
    def test_rejects_anything_else(self, bad: object) -> None:
        with pytest.raises(CallRowError) as caught:
            parse_timestamp(bad)
        assert caught.value.code == "timestamp.unreadable"


class TestAgentLogin:
    def test_takes_the_agent_number_out_of_the_display_string(self) -> None:
        assert agent_login("Jane Doe (Agent124)") == "Agent124"

    def test_keeps_a_bare_login(self) -> None:
        assert agent_login("jane.doe") == "jane.doe"

    @pytest.mark.parametrize("blank", [None, "", "  ", 5])
    def test_blank_is_none(self, blank: object) -> None:
        assert agent_login(blank) is None


class TestParseCallRow:
    def test_reads_a_good_row(self) -> None:
        row = parse_call_row(good_row())
        assert row.call_id == 70450076
        assert row.call_type == "INBOUND"
        assert row.queue == "QueueA"
        assert row.agent_login == "Agent007"
        assert row.start_at == datetime(2026, 5, 31, 19, 54, 17)
        assert (row.wait_s, row.talk_s, row.wrap_s, row.hold_s) == (14, 177, 20, 5)
        assert row.hangup_by == "USER"

    def test_an_abandoned_call_has_no_agent_time_or_agent(self) -> None:
        row = parse_call_row(
            good_row(
                **{
                    "Agent": None,
                    "Agent Time": "0000-00-00 00:00:00",
                    "Agent Duration": "00:00:00",
                    "Call Status": "Abandoned",
                }
            )
        )
        assert row.agent_at is None
        assert row.agent_login is None
        assert row.talk_s == 0

    def test_the_caller_phone_number_is_never_read(self) -> None:
        row = parse_call_row(good_row(**{"Phone Number": "27000000000", "Caller Number": "x"}))
        assert "27000000000" not in repr(row)

    @pytest.mark.parametrize(
        ("overrides", "code"),
        [
            ({"Call ID": None}, "call_id.missing"),
            ({"Call ID": "abc"}, "call_id.unreadable"),
            ({"Call ID": 0}, "call_id.unreadable"),
            ({"Call Type": ""}, "call_type.missing"),
            ({"Queue": None}, "queue.missing"),
            ({"Call Status": " "}, "status.missing"),
            ({"Start Time": None}, "start_time.missing"),
            ({"Start Time": "0000-00-00 00:00:00"}, "start_time.missing"),
            ({"Start Time": "yesterday"}, "timestamp.unreadable"),
        ],
    )
    def test_names_the_reason_it_cannot_read_a_row(
        self, overrides: dict[str, object], code: str
    ) -> None:
        with pytest.raises(CallRowError) as caught:
            parse_call_row(good_row(**overrides))
        assert caught.value.code == code

    def test_an_error_never_carries_the_cell_value(self) -> None:
        with pytest.raises(CallRowError) as caught:
            parse_call_row(good_row(**{"Call ID": "08212x4567"}))
        assert "08212x4567" not in str(caught.value)


class TestOptionalCellsDoNotLoseACall:
    """A real call is a real call. The real May report has an inbound call, abandoned the instant
    it started, whose wait is written as "-0:00:23". The deck counts it as offered and abandoned,
    so the importer must keep it, clear the one bad cell and say so."""

    def test_a_negative_wait_is_cleared_and_reported(self) -> None:
        row = parse_call_row(
            good_row(**{"Queue Wait Time": "-0:00:23", "Call Status": "Abandoned"})
        )
        assert row.wait_s is None
        assert row.call_id == 70450076
        assert row.warnings == ("queue_wait.negative",)

    def test_an_unreadable_cell_is_cleared_and_reported(self) -> None:
        row = parse_call_row(good_row(**{"Queue Wait Time": "soon", "Hangup Time": "yesterday"}))
        assert (row.wait_s, row.hangup_at) == (None, None)
        assert row.warnings == ("hangup_time.unreadable", "queue_wait.unreadable")

    def test_good_rows_have_no_warnings(self) -> None:
        assert parse_call_row(good_row()).warnings == ()

    def test_a_warning_never_carries_the_cell_value(self) -> None:
        row = parse_call_row(good_row(**{"Queue Wait Time": "0821234567"}))
        assert "0821234567" not in repr(row)
