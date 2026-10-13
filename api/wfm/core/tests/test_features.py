"""The feature switch: switching a module off for a customer that no longer pays for it."""

from __future__ import annotations

from typing import Any

import pytest
from django.apps import apps
from django.test import Client

from wfm.accounts.models import Role, User
from wfm.audit.models import Action, AuditEvent
from wfm.core.features import (
    REGISTRY,
    Feature,
    FeaturesMisconfiguredError,
    enabled_features,
    is_enabled,
    parse_features,
)


class TestParsing:
    def test_all_means_every_feature(self) -> None:
        assert parse_features("all") == frozenset(Feature)

    def test_none_means_no_optional_feature(self) -> None:
        assert parse_features("none") == frozenset()

    def test_a_list_enables_exactly_those(self) -> None:
        assert parse_features(" telephony , forecasting ") == {
            Feature.TELEPHONY,
            Feature.FORECASTING,
        }

    def test_an_unknown_name_stops_everything_and_lists_the_real_ones(self) -> None:
        with pytest.raises(FeaturesMisconfiguredError, match="unknown feature") as caught:
            parse_features("telephony,forecastin")
        assert "forecastin" in str(caught.value)
        assert "forecasting" in str(caught.value)  # the known names are listed

    def test_a_blank_value_is_refused_rather_than_guessed(self) -> None:
        # Blank could mean "all" or "none"; guessing wrong either gives away or removes a module.
        with pytest.raises(FeaturesMisconfiguredError, match="empty"):
            parse_features("  ")

    def test_a_feature_cannot_be_on_without_what_it_needs(self) -> None:
        with pytest.raises(FeaturesMisconfiguredError, match="'forecasting' needs telephony"):
            parse_features("forecasting")

    def test_names_are_exact_not_guessed(self) -> None:
        with pytest.raises(FeaturesMisconfiguredError):
            parse_features("Telephony")


class TestTheRegistryItselfIsSound:
    def test_every_feature_is_described(self) -> None:
        assert set(REGISTRY) == set(Feature)

    def test_dependencies_are_real_and_never_circular(self) -> None:
        for feature, info in REGISTRY.items():
            assert all(r in REGISTRY for r in info.requires)
            seen: set[Feature] = set()
            stack = list(info.requires)
            while stack:
                needed = stack.pop()
                assert needed != feature, f"{feature} depends on itself"
                if needed not in seen:
                    seen.add(needed)
                    stack.extend(REGISTRY[needed].requires)

    @pytest.mark.parametrize("feature", list(Feature))
    def test_each_feature_can_be_turned_on_with_its_dependencies(self, feature: Feature) -> None:
        needed = {feature}
        stack = [feature]
        while stack:
            for r in REGISTRY[stack.pop()].requires:
                if r not in needed:
                    needed.add(r)
                    stack.append(r)
        assert parse_features(",".join(f.value for f in needed)) == needed


class TestStartup:
    def test_a_bad_setting_stops_the_application_from_starting(self, settings: Any) -> None:
        settings.WFM_FEATURES = "telephony,bogus"
        with pytest.raises(FeaturesMisconfiguredError):
            apps.get_app_config("core").ready()

    def test_a_good_setting_starts_normally(self, settings: Any) -> None:
        settings.WFM_FEATURES = "telephony"
        apps.get_app_config("core").ready()
        assert enabled_features() == {Feature.TELEPHONY}


@pytest.mark.django_db
class TestEnforcement:
    @staticmethod
    def signed_in(role: Role) -> Client:
        user = User.objects.create_user(username=f"u-{role.value}", password="x", role=role)
        client = Client()
        client.force_login(user)
        return client

    def test_a_switched_off_feature_is_refused_even_for_an_admin(self, settings: Any) -> None:
        settings.WFM_FEATURES = "telephony"  # forecasting is not paid for
        response = self.signed_in(Role.ADMIN).get("/api/v1/forecasting/versions")
        assert (response.status_code, response.json()["code"]) == (403, "feature.disabled")

    def test_other_features_keep_working(self, settings: Any) -> None:
        settings.WFM_FEATURES = "telephony"
        response = self.signed_in(Role.PLANNER).get("/api/v1/telephony/months")
        assert response.status_code == 200

    def test_a_role_that_may_not_use_it_learns_nothing_about_the_plan(self, settings: Any) -> None:
        # The role check comes first, so an agent gets the ordinary refusal, audited.
        settings.WFM_FEATURES = "none"
        response = self.signed_in(Role.AGENT).get("/api/v1/forecasting/versions")
        assert response.json()["code"] == "auth.forbidden"
        assert AuditEvent.objects.filter(action=Action.ACCESS_DENIED).count() == 1

    def test_switching_a_feature_off_and_on_again_loses_nothing(self, settings: Any) -> None:
        from wfm.telephony.tests.workbooks import Call, upload, workbook_bytes

        planner = self.signed_in(Role.PLANNER)
        call = Call(1, "QueueA", "Agent", "2026-05-04 09:00:00", wait=1, talk=10)
        planner.post("/api/v1/telephony/imports", {"file": upload(workbook_bytes([call]))})
        before = planner.get("/api/v1/telephony/months").json()

        settings.WFM_FEATURES = "none"
        assert planner.get("/api/v1/telephony/months").status_code == 403
        settings.WFM_FEATURES = "all"

        assert planner.get("/api/v1/telephony/months").json() == before == {"months": ["2026-05"]}

    def test_sign_in_still_works_with_everything_off(self, settings: Any) -> None:
        settings.WFM_FEATURES = "none"
        assert self.signed_in(Role.PLANNER).get("/api/v1/auth/me").status_code == 200


@pytest.mark.django_db
class TestTellingTheUi:
    def test_me_lists_the_features_that_are_on(self, settings: Any) -> None:
        settings.WFM_FEATURES = "telephony,forecasting"
        user = User.objects.create_user(username="p", password="x", role=Role.PLANNER)
        client = Client()
        client.force_login(user)
        assert client.get("/api/v1/auth/me").json()["features"] == ["telephony", "forecasting"]

    def test_is_enabled_treats_core_as_always_on(self, settings: Any) -> None:
        settings.WFM_FEATURES = "none"
        assert is_enabled("core") is True
        assert is_enabled(Feature.TELEPHONY) is False
