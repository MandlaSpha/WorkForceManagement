from wfm_engine.attention import QueueWeek, attention


def week(name: str = "Q", **over: object) -> QueueWeek:
    facts = {
        "queue_id": 1,
        "queue": name,
        "has_forecast": True,
        "assumptions_confirmed": True,
        "intervals_known": 100,
        "under_intervals": 0,
        "scheduled_total": 50,
        "roster_published": True,
    }
    return QueueWeek(**{**facts, **over})  # type: ignore[arg-type]


class TestUnderStaffing:
    def test_a_covered_queue_has_nothing_to_report(self) -> None:
        assert attention([week()]) == []

    def test_a_quarter_or_more_short_is_critical(self) -> None:
        # 25 of 100 is exactly the line; 24 is below it.
        assert attention([week(under_intervals=25)])[0].severity == "critical"
        assert attention([week(under_intervals=24)])[0].severity == "warning"

    def test_says_how_many_in_plain_words(self) -> None:
        item = attention([week("Retentions", under_intervals=164, intervals_known=336)])[0]
        assert item.text == "Retentions: 164 under-staffed intervals"
        assert (item.kind, item.count) == ("understaffed", 164)

    def test_one_is_singular(self) -> None:
        assert attention([week("Sales", under_intervals=1)])[0].text == (
            "Sales: 1 under-staffed interval"
        )


class TestNoForecast:
    def test_nothing_is_claimed_about_a_queue_with_no_forecast(self) -> None:
        # Its roster, assumptions and shortfall mean nothing without a requirement.
        items = attention(
            [week(has_forecast=False, under_intervals=40, assumptions_confirmed=False)]
        )
        assert [(i.kind, i.severity) for i in items] == [("no_forecast", "warning")]


class TestSmallerThings:
    def test_unconfirmed_assumptions_are_noted(self) -> None:
        item = attention([week(assumptions_confirmed=False)])[0]
        assert (item.kind, item.severity) == ("assumptions", "info")

    def test_a_draft_roster_is_noted_only_when_someone_is_rostered(self) -> None:
        assert attention([week(roster_published=False, scheduled_total=0)]) == []
        item = attention([week(roster_published=False, scheduled_total=10)])[0]
        assert item.kind == "draft_roster"

    def test_a_published_roster_is_not_mentioned(self) -> None:
        assert attention([week(roster_published=True)]) == []


class TestOrder:
    def test_most_serious_first_then_biggest_then_by_name(self) -> None:
        items = attention(
            [
                week("A", queue_id=1, assumptions_confirmed=False),  # info
                week("B", queue_id=2, under_intervals=10),  # warning, 10
                week("C", queue_id=3, under_intervals=50),  # critical, 50
                week("D", queue_id=4, under_intervals=30),  # critical, 30
                week("E", queue_id=5, has_forecast=False),  # warning, 0
            ]
        )
        assert [i.queue for i in items] == ["C", "D", "B", "E", "A"]

    def test_no_queues_means_no_items(self) -> None:
        assert attention([]) == []
