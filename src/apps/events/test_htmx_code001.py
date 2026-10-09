from datetime import timedelta
from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlsplit

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

    def test_listing_feedback_survives_filter_and_pagination_partial_swaps(self):
        event = self.create_event("listing-feedback")
        for url, partial in (
            (reverse("events"), "events/_events_listing.html"),
            (reverse("games:game_detail", kwargs={"slug": self.game.slug}),
             "games/_game_events_listing.html"),
        ):
            with self.subTest(url=url):
                full = self.client.get(url)
                self.assertContains(full, "data-listing-feedback", count=1)
                self.assertContains(full, "data-listing-error", count=1)
                self.assertContains(full, "data-listing-loading", count=1)
                self.assertContains(full, 'hx-sync="this:replace"', count=1)
                filtered = self.client.get(
                    url, {"status": "upcoming", "page": "1"},
                    HTTP_HX_REQUEST="true",
                )
                self.assertTemplateUsed(filtered, partial)
                self.assertContains(filtered, event.title)
                # Feedback and its listener must not be duplicated on every swap.
                self.assertNotContains(filtered, "data-listing-feedback")
                self.assertNotContains(filtered, "data-listing-error")
                self.assertNotContains(filtered, "js/listings.js")

    def test_events_list_renders_for_anonymous_participant_and_organizer(self):
        event = self.create_event("authenticated-list")
        for user in (None, self.player, self.owner):
            self.client.logout()
            if user is not None:
                self.client.force_login(user)
            for headers in ({}, {"HTTP_HX_REQUEST": "true"}):
                with self.subTest(user=user, headers=headers):
                    response = self.client.get(reverse("events"), **headers)
                    self.assertContains(response, event.title)
                    self.assertTemplateUsed(
                        response,
                        "events/_events_listing.html" if headers else "events/events.html",
                    )

    def test_events_list_registration_annotation_is_specific_to_current_user(self):
        joined = self.create_event("own-registration", capacity=4)
        other = self.create_event("other-registration", capacity=4)
        cancelled = self.create_event("cancelled-registration", capacity=4)
        for event, player, status in (
            (joined, self.player, EventRegistration.Status.CONFIRMED),
            (joined, self.other_player, EventRegistration.Status.CONFIRMED),
            (other, self.other_player, EventRegistration.Status.CONFIRMED),
            (cancelled, self.player, EventRegistration.Status.CANCELLED),
        ):
            EventRegistration.objects.create(event=event, player=player, status=status)
        self.client.force_login(self.player)
        for headers in ({}, {"HTTP_HX_REQUEST": "true"}):
            with self.subTest(headers=headers):
                response = self.client.get(reverse("events"), **headers)
                self.assertEqual(response.status_code, 200)
                events = {event.pk: event for event in response.context["events"]}
                self.assertEqual(events[joined.pk].user_registration_status, "CONFIRMED")
                self.assertEqual(events[joined.pk].participants_count, 2)
                self.assertIsNone(events[other.pk].user_registration_status)
                self.assertIsNone(events[cancelled.pk].user_registration_status)

    def test_events_initial_selection_preserves_explicit_all_status(self):
        for params, expected in (
            ({}, "upcoming"),
            ({"status": ""}, ""),
            ({"status": "completed"}, "completed"),
        ):
            with self.subTest(params=params):
                response = self.client.get(reverse("events"), params)
                self.assertEqual(response.context["current_status"], expected)
                self.assertContains(response, f"status: '{expected}'")

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

    def test_my_events_history_requires_own_registration(self):
        event = self.create_event("cancelled-membership", capacity=5)
        EventRegistration.objects.create(event=event, player=self.player,
                                         status=EventRegistration.Status.CANCELLED)
        EventRegistration.objects.create(event=event, player=self.other_player)
        self.client.force_login(self.player)
        for status, count in (("", 1), ("ACTIVE", 0), ("CANCELED", 1)):
            response = self.client.get(reverse("my_events:index"),
                                       {"tab": "registered", "status": status})
            self.assertEqual(response.context["participating_page"].paginator.count, count)

    def test_my_events_counts_all_confirmed_participants_after_reregistration(self):
        event = self.create_event("reregistered", capacity=5)
        EventRegistration.objects.create(event=event, player=self.player,
                                         status=EventRegistration.Status.CANCELLED)
        EventRegistration.objects.create(event=event, player=self.player)
        EventRegistration.objects.create(event=event, player=self.other_player)
        self.client.force_login(self.player)
        response = self.client.get(reverse("my_events:index"), {"tab": "registered"})
        page = response.context["participating_page"]
        self.assertEqual(page.paginator.count, 1)
        self.assertEqual(page.object_list[0].participants_count, 2)
        self.assertEqual(page.object_list[0].user_registration_status, "CONFIRMED")

    def cancel_from_my_events(self, event, **params):
        self.client.force_login(self.player)
        return self.client.post(
            reverse("event_cancel_registration", kwargs={"slug": event.slug}),
            {"source": "my-events", "tab": "registered", **params},
            HTTP_HX_REQUEST="true",
        )

    def test_my_events_cancel_keeps_history_in_complete_block(self):
        event = self.create_event("last-registration")
        registration = EventRegistration.objects.create(event=event, player=self.player)
        response = self.cancel_from_my_events(event)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "events/partials/_my_events_content.html")
        self.assertContains(response, "Registrations (1)")
        self.assertContains(response, "Registration canceled")
        self.assertContains(response, "Event active")
        self.assertEqual(response.context["participating_page"].paginator.count, 1)
        self.assertNotContains(response, "Cancel registration")
        self.assertNotContains(response, "participants-badge-count")
        self.assertNotContains(response, "<html")
        registration.refresh_from_db()
        self.assertEqual(registration.status, EventRegistration.Status.CANCELLED)

    def test_my_events_cancel_clamps_last_page_and_preserves_filters(self):
        events = [self.create_event(f"pagination-{number}") for number in range(13)]
        for event in events:
            EventRegistration.objects.create(event=event, player=self.player)
        self.client.force_login(self.player)
        params = {"tab": "registered", "part_page": "2", "q": "pagination", "status": "ACTIVE"}
        before = self.client.get(reverse("my_events:index"), params)
        last = before.context["participating_page"].object_list[0]
        response = self.cancel_from_my_events(last, **params)
        page = response.context["participating_page"]
        self.assertEqual(page.number, 1)
        self.assertEqual(page.paginator.count, 12)
        self.assertEqual(len(page.object_list), 12)
        self.assertEqual(response.context["q"], "pagination")
        self.assertEqual(response.context["status"], "ACTIVE")
        self.assertEqual(response.context["active_tab"], "registered")

    def test_my_events_cancel_last_filtered_result(self):
        selected = self.create_event("search-match")
        other = self.create_event("outside-filter")
        for event in (selected, other):
            EventRegistration.objects.create(event=event, player=self.player)
        response = self.cancel_from_my_events(selected, q="search-match", status="ACTIVE")
        self.assertContains(response, "Registrations (2)")
        self.assertContains(response, "No events found with the applied filters.")
        self.assertEqual(EventRegistration.objects.filter(
            player=self.player, status=EventRegistration.Status.CONFIRMED).count(), 1)

    def test_my_events_cancel_rejected_keeps_registration(self):
        event = self.create_event("started-event")
        registration = EventRegistration.objects.create(event=event, player=self.player)
        Event.objects.filter(pk=event.pk).update(start_at=timezone.now() - timedelta(hours=1))
        response = self.cancel_from_my_events(event)
        self.assertEqual(response.status_code, 400)
        self.assertTemplateUsed(response, "events/partials/_my_events_content.html")
        self.assertEqual(response.context["participating_page"].paginator.count, 1)
        self.assertTrue(response.context["registration_error"])
        registration.refresh_from_db()
        self.assertEqual(registration.status, EventRegistration.Status.CONFIRMED)

    def test_my_events_cancel_without_javascript_returns_to_filtered_listing(self):
        event = self.create_event("normal-my-events")
        EventRegistration.objects.create(event=event, player=self.player)
        self.client.force_login(self.player)
        response = self.client.post(
            reverse("event_cancel_registration", kwargs={"slug": event.slug}),
            {"source": "my-events", "tab": "registered", "q": "A & B", "part_page": "2"},
        )
        self.assertRedirects(response, reverse("my_events:index") +
                             "?tab=registered&q=A+%26+B&part_page=2")

    def test_my_events_cancel_cannot_cancel_another_players_registration(self):
        event = self.create_event("other-player-only")
        registration = EventRegistration.objects.create(event=event, player=self.other_player)
        response = self.cancel_from_my_events(event)
        self.assertEqual(response.status_code, 400)
        registration.refresh_from_db()
        self.assertEqual(registration.status, EventRegistration.Status.CONFIRMED)

    def test_my_events_registration_categories_are_exclusive_and_complete(self):
        cases = (
            ("active", "ACTIVE", "CONFIRMED", "ACTIVE"),
            ("completed", "COMPLETED", "CONFIRMED", "COMPLETED"),
            ("withdrawn", "ACTIVE", "CANCELLED", "CANCELED"),
            ("withdrawn-completed", "COMPLETED", "CANCELLED", "CANCELED"),
            ("event-canceled", "CANCELED", "CANCELLED", "CANCELED"),
            ("canceled-confirmation", "CANCELED", "CONFIRMED", "CANCELED"),
        )
        expected = {"ACTIVE": set(), "COMPLETED": set(), "CANCELED": set()}
        for name, event_status, registration_status, category in cases:
            event = self.create_event(name)
            Event.objects.filter(pk=event.pk).update(status=event_status)
            EventRegistration.objects.create(event=event, player=self.player,
                                             status=registration_status)
            expected[category].add(event.pk)
        unrelated = self.create_event("unrelated")
        EventRegistration.objects.create(event=unrelated, player=self.other_player)
        self.client.force_login(self.player)
        found = set()
        for status, ids in expected.items():
            with self.subTest(status=status):
                response = self.client.get(reverse("my_events:index"),
                                           {"tab": "registered", "status": status})
                rows = list(response.context["participating_page"])
                self.assertEqual({row.pk for row in rows}, ids)
                self.assertTrue(all(row.participation_status == status for row in rows))
                self.assertFalse(found.intersection(ids))
                found.update(ids)
                self.assertEqual(response.context["participating_total"], len(cases))
        response = self.client.get(reverse("my_events:index"), {"tab": "registered"})
        self.assertEqual({row.pk for row in response.context["participating_page"]}, found)
        self.assertContains(response, "Event canceled")
        self.assertContains(response, "Event completed")
        self.assertNotContains(response, "canceled by you")

    def test_my_events_reregistration_uses_current_membership_without_duplicate_rows(self):
        event = self.create_event("repeat-history", capacity=5)
        for _ in range(3):
            EventRegistration.objects.create(event=event, player=self.player,
                                             status="CANCELLED")
        EventRegistration.register(event=event, player=self.player)
        EventRegistration.register(event=event, player=self.other_player)
        self.client.force_login(self.player)
        for status, count in (("", 1), ("ACTIVE", 1), ("CANCELED", 0)):
            response = self.client.get(reverse("my_events:index"),
                                       {"tab": "registered", "status": status})
            page = response.context["participating_page"]
            self.assertEqual(page.paginator.count, count)
            if count:
                self.assertEqual(page[0].participants_count, 2)
                self.assertEqual(page[0].participation_status, "ACTIVE")
                self.assertContains(response, "Cancel registration")

    def test_my_events_event_cancellation_and_removal_preserve_history(self):
        from apps.events.services import cancel_event, cancel_registration_for_actor
        canceled = self.create_event("owner-cancels")
        removed = self.create_event("owner-removes")
        for event in (canceled, removed):
            EventRegistration.register(event=event, player=self.player)
        cancel_event(canceled)
        registration = removed.registrations.get(player=self.player)
        cancel_registration_for_actor(registration=registration, actor=self.owner)
        self.client.force_login(self.player)
        response = self.client.get(reverse("my_events:index"),
                                   {"tab": "registered", "status": "CANCELED"})
        self.assertEqual(response.context["participating_page"].paginator.count, 2)
        self.assertContains(response, "Event canceled")
        self.assertContains(response, "Registration canceled")
        self.assertNotContains(response, "Cancel registration")
        self.assertTrue(all(row.participants_count == 0
                            for row in response.context["participating_page"]))

    def test_my_events_organizing_filters_event_status_and_totals_ignore_search(self):
        events = []
        for status in Event.Status.values:
            event = self.create_event(f"organizing-{status.lower()}")
            Event.objects.filter(pk=event.pk).update(status=status)
            events.append(event)
        self.client.force_login(self.owner)
        for status in Event.Status.values:
            response = self.client.get(reverse("my_events:index"),
                                       {"status": status, "q": status.lower()})
            self.assertEqual(response.context["organizing_page"].paginator.count, 1)
            self.assertEqual(response.context["organizing_total"], 3)
            self.assertEqual(response.context["participating_total"], 0)
        EventRegistration.register(event=events[0], player=self.owner)
        response = self.client.get(reverse("my_events:index"))
        self.assertEqual(response.context["participating_total"], 1)

    def test_my_events_filter_and_pagination_links_preserve_search_text(self):
        class Links(HTMLParser):
            def __init__(self):
                super().__init__()
                self.urls = []
            def handle_starttag(self, tag, attrs):
                if tag == "a":
                    href = dict(attrs).get("href", "")
                    if href.startswith("?tab="):
                        self.urls.append(href)
        for text in ("Audit & Dragons", "C++ #1", "Épée 東京"):
            self.game.name = text
            self.game.save(update_fields=["name"])
            # Both title and game searches are supported; these rows match game.
            for number in range(13):
                event = self.create_event(f"encoded-{len(text)}-{number}")
                EventRegistration.objects.create(event=event, player=self.owner)
            self.client.force_login(self.owner)
            for tab in ("organizing", "registered"):
                response = self.client.get(reverse("my_events:index"), {"tab": tab, "q": text})
                links = Links()
                links.feed(response.content.decode())
                search_links = [url for url in links.urls if "q=" in url]
                self.assertTrue(search_links)
                for url in search_links:
                    params = parse_qs(urlsplit(unescape(url)).query)
                    self.assertEqual(params["q"], [text])
                next_url = next(url for url in search_links if "page=2" in url and f"tab={tab}" in url)
                second = self.client.get(reverse("my_events:index") + next_url)
                page_key = "organizing_page" if tab == "organizing" else "participating_page"
                self.assertEqual(second.context[page_key].number, 2)
                self.assertEqual(second.context["q"], text)
                self.assertContains(response, 'href="?tab=organizing"')
                self.assertContains(response, 'href="?tab=registered"')
            EventRegistration.objects.all().delete()
            Event.objects.all().delete()

    def test_my_events_invalid_parameters_normalize_and_pages_remain_valid(self):
        event = self.create_event("invalid-params")
        EventRegistration.objects.create(event=event, player=self.player)
        self.client.force_login(self.player)
        response = self.client.get(reverse("my_events:index"),
                                   {"tab": "unknown", "status": "UNKNOWN", "org_page": "broken"})
        self.assertEqual(response.context["active_tab"], "organizing")
        self.assertEqual(response.context["status"], "")
        self.assertEqual(response.context["organizing_page"].number, 1)
        response = self.client.get(reverse("my_events:index"),
                                   {"tab": "registered", "part_page": "999"})
        self.assertEqual(response.context["participating_page"].number, 1)
