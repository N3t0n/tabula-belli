from importlib.util import find_spec
from io import StringIO

from allauth.account.models import EmailAddress
from cities_light.models import City, Country
from django.conf import settings
from django.contrib.auth import get_user
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import NoReverseMatch, reverse

from apps.players.models import Player
from apps.players.management.commands.seed_users import Command as SeedUsersCommand


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
)
class AuthenticationFlowTest(TestCase):
    password = 'StrongTestPass123!'
    seed_password = 'TestPass123!'
    signup_username = 'signup_user'
    signup_email = 'signup.user@example.com'

    def create_signup_user(self, *, verify=True):
        response = self.client.post(reverse('account_signup'), {
            'username': self.signup_username,
            'email': self.signup_email,
            'password1': self.password,
            'password2': self.password,
        })
        self.assertEqual(response.status_code, 302)
        user = Player.objects.get(username=self.signup_username)
        if verify:
            EmailAddress.objects.filter(user=user).update(verified=True)
        return user

    def create_seed_user(self, username='horus_lupercal'):
        seed_user = next(
            user for user in SeedUsersCommand.get_seed_users()
            if user['username'] == username
        )
        geoname_id, city_name, country_code = seed_user['location']
        country = Country.objects.create(
            name=f'{country_code} Test Country',
            name_ascii=f'{country_code} Test Country',
            slug=f'{country_code.lower()}-test-country',
            geoname_id=9990000 + geoname_id,
            code2=country_code,
            code3=f'{country_code}X',
            continent='EU',
            tld=f'.{country_code.lower()}',
            phone='1',
        )
        City.objects.create(
            name=city_name,
            name_ascii=city_name,
            slug=f'{username}-city',
            geoname_id=geoname_id,
            display_name=f'{city_name}, {country_code}',
            country=country,
        )
        call_command('seed_users', stdout=StringIO())
        return Player.objects.get(username=username)

    def assert_login(self, identifier, user, password=None):
        response = self.client.post(reverse('account_login'), {
            'login': identifier,
            'password': password or self.password,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_user(self.client).pk, user.pk)

    def assert_password_reset_email(self, email):
        response = self.client.post(reverse('account_reset_password'), {
            'email': email,
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            [recipient.lower() for recipient in mail.outbox[0].to],
            [email.lower()],
        )

    def test_signup_user_can_login_by_username(self):
        user = self.create_signup_user()
        self.client.logout()

        self.assert_login(user.username, user)

    def test_signup_user_can_login_by_email_case_insensitively(self):
        user = self.create_signup_user()
        self.client.logout()

        self.assert_login(user.email.upper(), user)

    def test_seed_user_can_login_by_username(self):
        user = self.create_seed_user()

        self.assert_login(user.username, user, self.seed_password)

    def test_seed_user_can_login_by_email(self):
        user = self.create_seed_user()

        self.assert_login(user.email.lower(), user, self.seed_password)

    def test_seed_repairs_email_address_without_duplicates(self):
        user = self.create_seed_user()
        EmailAddress.objects.filter(user=user).delete()

        call_command('seed_users', stdout=StringIO())
        call_command('seed_users', stdout=StringIO())

        email_addresses = EmailAddress.objects.filter(user=user)
        self.assertEqual(email_addresses.count(), 1)
        email_address = email_addresses.get()
        self.assertEqual(email_address.email, user.email)
        self.assertTrue(email_address.primary)
        self.assertTrue(email_address.verified)

    def test_logout_ends_authenticated_session(self):
        self.create_signup_user()

        response = self.client.post(reverse('account_logout'))

        self.assertEqual(response.status_code, 302)
        self.assertFalse(get_user(self.client).is_authenticated)

    def test_password_reset_recognizes_signup_email(self):
        user = self.create_signup_user()
        self.client.logout()

        self.assert_password_reset_email(user.email)

    def test_password_reset_recognizes_seed_email(self):
        user = self.create_seed_user(username='rogal_dorn')

        self.assert_password_reset_email(user.email)

    def test_google_login_flow_is_not_exposed(self):
        with self.assertRaises(NoReverseMatch):
            reverse('google_login')

        response = self.client.get('/accounts/google/login/')
        self.assertEqual(response.status_code, 404)

    def test_residual_custom_backend_is_not_part_of_authentication(self):
        self.assertNotIn(
            'apps.players.backends.EmailOrUsernameBackend',
            settings.AUTHENTICATION_BACKENDS,
        )
        self.assertIsNone(find_spec('apps.players.backends'))
