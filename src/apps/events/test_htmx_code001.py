from datetime import timedelta

from allauth.account.models import EmailAddress
from cities_light.models import City, Country, Region
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.events.models import Event, EventRegistration
from apps.games.models import Game
from apps.players.models import Player


class HtmxCodeFunctionalRegressionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.country = Country.objects.create(
            name="HTMX Country", code2="HX", code3="HTX"
        )
        cls.region = Region.objects.create(
            name="HTMX Region",
            slug="htmx-region",
            country=cls.country,
        )
        cls.city = City.objects.create(
            name="HTMX City",
            slug="htmx-city",
            country=cls.country,
            region=cls.region,
        )
        cls.game = Game.objects.create(
            name="HTMX Game",
            slug="htmx-game",
            category=Game.Category.TCG,
        )
        cls.owner = Player.objects.create_user(
            username="htmx-owner", email="owner@htmx.test"
        )
        cls.player = Player.objects.create_user(
            username="htmx-player", email="player@htmx.test"
        )
        cls.other_player = Player.objects.create_user(
            username="htmx-other", email="other@htmx.test"
        )
        EmailAddress.objects.bulk_create([
            EmailAddress(
                user=user,
                email=user.email,
                primary=True,
                verified=True,
            )
            for user in (cls.owner, cls.player, cls.other_player)
        ])

    def create_event(self, suffix, *, capacity=2):
        now = timezone.now()
        return Event.objects.create(
            title=f"HTMX {suffix}",
            slug=f"htmx-{suffix}",
            organizer=self.owner,
            country=self.country,
            region=self.region,
            city=self.city,
            game=self.game,
            contact_email=f"{suffix}@htmx.test",
            start_at=now + timedelta(days=3),
            end_at=now + timedelta(days=3, hours=2),
            registration_opens_at=now - timedelta(days=1),
            registration_closes_at=now + timedelta(days=2),
            capacity=capacity,
        )

    def test_cancel_event_form_is_separate_and_targets_cancel_endpoint(self):
        event = self.create_event("form-contract")
        self.client.force_login(self.owner)

        response = self.client.get(
            reverse("my_events:edit", kwargs={"slug": event.slug})
        )
        html = response.content.decode()
        cancel_url = reverse(
            "my_events:cancel", kwargs={"slug": event.slug}
        )
        main_form_start = html.index('id="event-main-form"')
        main_form_end = html.index('</form>', main_form_start)
        cancel_form_start = html.index(f'action="{cancel_url}"')

        self.assertEqual(response.status_code, 200)
        self.assertLess(main_form_end, cancel_form_start)
        self.assertContains(response, 'form="event-main-form"')
        self.assertContains(response, f'hx-post="{cancel_url}"')
        self.assertContains(response, 'hx-confirm=')

    def test_full_status_is_consistent_on_detail_and_htmx_mutations(self):
        event = self.create_event("full-contract", capacity=1)
        self.client.force_login(self.player)

        register_response = self.client.post(
            reverse("event_register", kwargs={"slug": event.slug}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(register_response.status_code, 200)
        self.assertTemplateUsed(
            register_response, "events/partials/registration_button.html"
        )
        self.assertContains(register_response, "Event is full")
        self.assertNotContains(register_response, "Registration not available")
        self.assertEqual(
            register_response.context["registration_status"],
            Event.RegistrationStatus.FULL,
        )
        self.assertFalse(register_response.context["registration_open"])
        self.assertTrue(register_response.context["is_full"])
        self.assertEqual(register_response.context["confirmed_count"], 1)
        self.assertContains(
            register_response,
            f'action="{reverse("event_cancel_registration", kwargs={"slug": event.slug})}"',
        )

        detail_response = self.client.get(
            reverse("event_detail", kwargs={"slug": event.slug})
        )
        self.assertContains(detail_response, "Event is full")
        self.assertEqual(
            detail_response.context["registration_status"],
            Event.RegistrationStatus.FULL,
        )
        self.assertEqual(detail_response.context["confirmed_count"], 1)

        cancel_response = self.client.post(
            reverse(
                "event_cancel_registration", kwargs={"slug": event.slug}
            ),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(cancel_response.status_code, 200)
        self.assertContains(cancel_response, "Register for Event")
        self.assertEqual(
            cancel_response.context["registration_status"],
            Event.RegistrationStatus.OPEN,
        )
        self.assertTrue(cancel_response.context["registration_open"])
        self.assertFalse(cancel_response.context["is_full"])
        self.assertEqual(cancel_response.context["confirmed_count"], 0)
        self.assertContains(
            cancel_response,
            f'action="{reverse("event_register", kwargs={"slug": event.slug})}"',
        )

    def test_normal_registration_and_cancellation_use_http_redirects(self):
        event = self.create_event("normal-registration")
        self.client.force_login(self.player)
        detail_url = reverse("event_detail", kwargs={"slug": event.slug})

        register_response = self.client.post(
            reverse("event_register", kwargs={"slug": event.slug})
        )
        self.assertRedirects(
            register_response, detail_url, fetch_redirect_response=False
        )

        cancel_response = self.client.post(
            reverse(
                "event_cancel_registration", kwargs={"slug": event.slug}
            )
        )
        self.assertRedirects(
            cancel_response, detail_url, fetch_redirect_response=False
        )

    def test_normal_registration_error_redirects_to_complete_page(self):
        event = self.create_event("normal-error")
        EventRegistration.objects.create(event=event, player=self.player)
        self.client.force_login(self.player)
        detail_url = reverse("event_detail", kwargs={"slug": event.slug})

        response = self.client.post(
            reverse("event_register", kwargs={"slug": event.slug})
        )
        self.assertRedirects(response, detail_url, fetch_redirect_response=False)

        redirected = self.client.get(response.url)
        self.assertContains(redirected, "already registered")
        self.assertContains(redirected, "<!DOCTYPE html>", html=False)

    def test_event_cancel_preserves_htmx_and_normal_contracts(self):
        htmx_event = self.create_event("cancel-htmx")
        normal_event = self.create_event("cancel-normal")
        self.client.force_login(self.owner)
        cancel_url = reverse("my_events:index")

        htmx_response = self.client.post(
            reverse("my_events:cancel", kwargs={"slug": htmx_event.slug}),
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(htmx_response.status_code, 204)
        self.assertEqual(htmx_response.headers["HX-Redirect"], cancel_url)

        normal_response = self.client.post(
            reverse("my_events:cancel", kwargs={"slug": normal_event.slug})
        )
        self.assertRedirects(
            normal_response, cancel_url, fetch_redirect_response=False
        )

    def test_mutating_forms_have_normal_html_contracts(self):
        event = self.create_event("form-fallback")
        EventRegistration.objects.create(event=event, player=self.other_player)
        self.client.force_login(self.owner)

        detail_response = self.client.get(
            reverse("event_detail", kwargs={"slug": event.slug})
        )
        cancel_url = reverse(
            "my_events:cancel", kwargs={"slug": event.slug}
        )
        remove_url = reverse(
            "my_events:remove_participant",
            kwargs={
                "slug": event.slug,
                "reg_id": event.registrations.get().pk,
            },
        )

        self.assertContains(detail_response, 'method="post"')
        self.assertContains(detail_response, f'action="{cancel_url}"')
        self.assertContains(detail_response, f'action="{remove_url}"')

    def test_normal_participant_removal_uses_http_redirect(self):
        event = self.create_event("normal-removal")
        registration = EventRegistration.objects.create(
            event=event, player=self.other_player
        )
        self.client.force_login(self.owner)
        detail_url = reverse("event_detail", kwargs={"slug": event.slug})

        response = self.client.post(reverse(
            "my_events:remove_participant",
            kwargs={"slug": event.slug, "reg_id": registration.pk},
        ))

        self.assertRedirects(response, detail_url, fetch_redirect_response=False)
        registration.refresh_from_db()
        self.assertEqual(
            registration.status, EventRegistration.Status.CANCELLED
        )
