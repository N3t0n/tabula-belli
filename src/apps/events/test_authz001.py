from datetime import timedelta

from allauth.account.models import EmailAddress
from cities_light.models import City, Country, Region
from django.contrib.auth.models import AnonymousUser
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event, EventRegistration
from apps.events.policies import can_manage_event
from apps.games.models import Game
from apps.players.models import Player


class EventAuthorizationMatrixTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.country = Country.objects.create(
            name="AUTHZ Country", code2="AZ", code3="ATZ"
        )
        cls.region = Region.objects.create(
            name="AUTHZ Region", slug="authz-region", country=cls.country
        )
        cls.city = City.objects.create(
            name="AUTHZ City",
            slug="authz-city",
            country=cls.country,
            region=cls.region,
        )
        cls.game = Game.objects.create(
            name="AUTHZ Game", slug="authz-game", category=Game.Category.TCG
        )
        cls.owner = Player.objects.create_user(
            username="authz-owner", email="owner@authz.test"
        )
        cls.non_owner = Player.objects.create_user(
            username="authz-non-owner", email="non-owner@authz.test"
        )
        cls.staff = Player.objects.create_user(
            username="authz-staff", email="staff@authz.test", is_staff=True
        )
        cls.superuser = Player.objects.create_superuser(
            username="authz-superuser",
            email="superuser@authz.test",
            password="test-pass",
        )
        cls.participant = Player.objects.create_user(
            username="authz-participant", email="participant@authz.test"
        )
        EmailAddress.objects.bulk_create([
            EmailAddress(
                user=user,
                email=user.email,
                primary=True,
                verified=True,
            )
            for user in (
                cls.owner,
                cls.non_owner,
                cls.staff,
                cls.superuser,
                cls.participant,
            )
        ])

    @property
    def roles(self):
        return [
            ("anonymous", None),
            ("non_owner", self.non_owner),
            ("owner", self.owner),
            ("staff_non_owner", self.staff),
            ("superuser", self.superuser),
        ]

    def create_event(self, suffix, organizer=None):
        now = timezone.now()
        return Event.objects.create(
            title=f"AUTHZ {suffix}",
            slug=f"authz-{suffix}",
            organizer=organizer or self.owner,
            country=self.country,
            region=self.region,
            city=self.city,
            game=self.game,
            contact_email=f"{suffix}@authz.test",
            start_at=now + timedelta(days=3),
            end_at=now + timedelta(days=3, hours=2),
            capacity=10,
        )

    def login_as(self, user):
        self.client.logout()
        if user is not None:
            self.client.force_login(user)

    def test_event_management_policy_is_owner_or_superuser(self):
        event = self.create_event("policy")

        self.assertFalse(can_manage_event(AnonymousUser(), event))
        self.assertFalse(can_manage_event(self.non_owner, event))
        self.assertTrue(can_manage_event(self.owner, event))
        self.assertFalse(can_manage_event(self.staff, event))
        self.assertTrue(can_manage_event(self.superuser, event))

    def test_edit_event_authorization_matrix(self):
        expected_statuses = {
            "anonymous": 302,
            "non_owner": 403,
            "owner": 200,
            "staff_non_owner": 403,
            "superuser": 200,
        }

        for role, user in self.roles:
            with self.subTest(role=role):
                event = self.create_event(f"edit-{role}")
                self.login_as(user)

                response = self.client.get(
                    reverse("my_events:edit", kwargs={"slug": event.slug})
                )

                self.assertEqual(response.status_code, expected_statuses[role])
                if role == "anonymous":
                    self.assertIn(reverse("account_login"), response.url)

    def test_cancel_event_authorization_matrix(self):
        expected_statuses = {
            "anonymous": 302,
            "non_owner": 403,
            "owner": 204,
            "staff_non_owner": 403,
            "superuser": 204,
        }

        for role, user in self.roles:
            with self.subTest(role=role):
                event = self.create_event(f"cancel-{role}")
                registration = EventRegistration.objects.create(
                    event=event, player=self.participant
                )
                self.login_as(user)

                response = self.client.post(
                    reverse("my_events:cancel", kwargs={"slug": event.slug}),
                    HTTP_HX_REQUEST="true",
                )

                event.refresh_from_db()
                registration.refresh_from_db()
                self.assertEqual(response.status_code, expected_statuses[role])
                if role in {"owner", "superuser"}:
                    self.assertEqual(event.status, Event.Status.CANCELED)
                    self.assertEqual(
                        registration.status, EventRegistration.Status.CANCELLED
                    )
                    self.assertFalse(
                        event.registrations.filter(
                            status=EventRegistration.Status.CONFIRMED
                        ).exists()
                    )
                    self.assertEqual(
                        response.headers["HX-Redirect"],
                        reverse("my_events:index"),
                    )
                else:
                    self.assertEqual(event.status, Event.Status.ACTIVE)
                    self.assertEqual(
                        registration.status, EventRegistration.Status.CONFIRMED
                    )

    def test_private_participants_and_controls_follow_policy(self):
        expected_private_access = {
            "anonymous": False,
            "non_owner": False,
            "owner": True,
            "staff_non_owner": False,
            "superuser": True,
        }

        for role, user in self.roles:
            with self.subTest(role=role):
                event = self.create_event(f"participants-{role}")
                registration = EventRegistration.objects.create(
                    event=event, player=self.participant
                )
                edit_url = reverse(
                    "my_events:edit", kwargs={"slug": event.slug}
                )
                cancel_url = reverse(
                    "my_events:cancel", kwargs={"slug": event.slug}
                )
                remove_url = reverse(
                    "my_events:remove_participant",
                    kwargs={"slug": event.slug, "reg_id": registration.pk},
                )
                self.login_as(user)

                response = self.client.get(
                    reverse("event_detail", kwargs={"slug": event.slug})
                )

                has_access = expected_private_access[role]
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["can_manage_event"], has_access)
                if has_access:
                    self.assertContains(response, self.participant.email)
                    self.assertContains(response, edit_url)
                    self.assertContains(response, cancel_url)
                    self.assertContains(response, remove_url)
                else:
                    self.assertNotContains(response, self.participant.email)
                    self.assertNotContains(response, edit_url)
                    self.assertNotContains(response, cancel_url)
                    self.assertNotContains(response, remove_url)

    def test_remove_participant_authorization_matrix(self):
        expected_statuses = {
            "anonymous": 302,
            "non_owner": 403,
            "owner": 200,
            "staff_non_owner": 403,
            "superuser": 200,
        }

        for role, user in self.roles:
            with self.subTest(role=role):
                event = self.create_event(f"remove-{role}")
                registration = EventRegistration.objects.create(
                    event=event, player=self.participant
                )
                self.login_as(user)

                response = self.client.post(
                    reverse(
                        "my_events:remove_participant",
                        kwargs={
                            "slug": event.slug,
                            "reg_id": registration.pk,
                        },
                    ),
                    HTTP_HX_REQUEST="true",
                )

                registration.refresh_from_db()
                self.assertEqual(response.status_code, expected_statuses[role])
                expected_registration_status = (
                    EventRegistration.Status.CANCELLED
                    if role in {"owner", "superuser"}
                    else EventRegistration.Status.CONFIRMED
                )
                self.assertEqual(
                    registration.status, expected_registration_status
                )

    def test_staff_owner_can_perform_all_management_actions(self):
        staff_event = self.create_event("staff-owner", organizer=self.staff)
        staff_registration = EventRegistration.objects.create(
            event=staff_event, player=self.participant
        )
        self.client.force_login(self.staff)

        edit_response = self.client.get(
            reverse("my_events:edit", kwargs={"slug": staff_event.slug})
        )
        detail_response = self.client.get(
            reverse("event_detail", kwargs={"slug": staff_event.slug})
        )
        remove_response = self.client.post(
            reverse(
                "my_events:remove_participant",
                kwargs={
                    "slug": staff_event.slug,
                    "reg_id": staff_registration.pk,
                },
            ),
            HTTP_HX_REQUEST="true",
        )

        staff_registration.refresh_from_db()
        self.assertEqual(edit_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, self.participant.email)
        self.assertEqual(remove_response.status_code, 200)
        self.assertEqual(
            staff_registration.status, EventRegistration.Status.CANCELLED
        )

        cancel_event = self.create_event("staff-owner-cancel", organizer=self.staff)
        cancel_response = self.client.post(
            reverse("my_events:cancel", kwargs={"slug": cancel_event.slug}),
            HTTP_HX_REQUEST="true",
        )
        cancel_event.refresh_from_db()
        self.assertEqual(cancel_response.status_code, 204)
        self.assertEqual(cancel_event.status, Event.Status.CANCELED)

    def test_remove_participant_preserves_cross_event_idor_protection(self):
        event_a = self.create_event("idor-a")
        event_b = self.create_event("idor-b")
        registration_b = EventRegistration.objects.create(
            event=event_b, player=self.participant
        )
        self.client.force_login(self.owner)

        response = self.client.post(
            reverse(
                "my_events:remove_participant",
                kwargs={"slug": event_a.slug, "reg_id": registration_b.pk},
            )
        )

        registration_b.refresh_from_db()
        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            registration_b.status, EventRegistration.Status.CONFIRMED
        )

    def test_registration_rules_remain_role_independent(self):
        actors = [self.non_owner, self.owner, self.staff, self.superuser]

        for actor in actors:
            with self.subTest(actor=actor.username):
                event = self.create_event(f"register-{actor.username}")
                self.client.force_login(actor)

                response = self.client.post(
                    reverse("event_register", kwargs={"slug": event.slug}),
                    HTTP_HX_REQUEST="true",
                )

                self.assertEqual(response.status_code, 200)
                self.assertTrue(
                    EventRegistration.objects.filter(
                        event=event,
                        player=actor,
                        status=EventRegistration.Status.CONFIRMED,
                    ).exists()
                )

    def test_own_cancellation_cannot_target_another_players_registration(self):
        for actor in [self.staff, self.superuser]:
            with self.subTest(actor=actor.username):
                event = self.create_event(f"own-cancel-{actor.username}")
                registration = EventRegistration.objects.create(
                    event=event, player=self.participant
                )
                self.client.force_login(actor)

                response = self.client.post(
                    reverse(
                        "event_cancel_registration", kwargs={"slug": event.slug}
                    ),
                    HTTP_HX_REQUEST="true",
                )

                registration.refresh_from_db()
                self.assertEqual(response.status_code, 400)
                self.assertEqual(
                    registration.status, EventRegistration.Status.CONFIRMED
                )
