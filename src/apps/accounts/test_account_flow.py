import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.players.models import Player


class FormMarkupParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fields = {}
        self.ids = set()
        self.duplicate_ids = set()

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        identifier = attributes.get('id')
        if identifier:
            if identifier in self.ids:
                self.duplicate_ids.add(identifier)
            self.ids.add(identifier)
        if tag == 'input' and attributes.get('name'):
            self.fields[attributes['name']] = attributes


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AccountFlowTest(TestCase):
    password = 'StrongFlowTestPass123!'

    def assert_branded_page(self, response, text):
        self.assertContains(response, text)
        self.assertContains(response, 'css/output.css')
        self.assertContains(response, 'Tabula Belli')
        self.assertNotContains(response, '<h2>Menu:</h2>')

    def test_login_rotates_csrf_and_rejects_stale_form_tokens(self):
        user = Player.objects.create_user(
            username='csrf-review', email='csrf@accounts.test', password=self.password,
        )
        EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
        client = Client(enforce_csrf_checks=True)
        url = reverse('account_login')
        response = client.get(url, secure=True)
        parser = FormMarkupParser()
        parser.feed(response.content.decode())
        stale_token = parser.fields['csrfmiddlewaretoken']['value']
        credentials = {'login': user.username, 'password': self.password}
        response = client.post(url, {**credentials, 'csrfmiddlewaretoken': stale_token},
                               secure=True, HTTP_ORIGIN='https://testserver')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_user(client).pk, user.pk)
        response = client.post(url, {**credentials, 'csrfmiddlewaretoken': stale_token},
                               secure=True, HTTP_ORIGIN='https://testserver')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(get_user(client).pk, user.pk)
        response = client.post(reverse('account_logout'), {
            'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
        }, secure=True, HTTP_ORIGIN='https://testserver')
        self.assertEqual(response.status_code, 302)
        response = client.get(url, secure=True)
        parser = FormMarkupParser()
        parser.feed(response.content.decode())
        response = client.post(url, {**credentials,
            'csrfmiddlewaretoken': parser.fields['csrfmiddlewaretoken']['value'],
        }, secure=True, HTTP_ORIGIN='https://testserver')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(get_user(client).pk, user.pk)

    def test_logout_get_shows_confirmation_without_ending_the_session(self):
        user = Player.objects.create_user(
            username='logout-review', email='logout@accounts.test', password=self.password,
        )
        self.client.force_login(user)
        response = self.client.get(reverse('account_logout'))
        self.assert_branded_page(response, 'Sign out?')
        self.assertContains(response, 'Stay signed in')
        self.assertContains(response, reverse('accounts:profile'))
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        self.assertEqual(get_user(self.client).pk, user.pk)

    def test_logout_confirmation_requires_csrf_and_preserves_safe_next_redirect(self):
        user = Player.objects.create_user(
            username='logout-post', email='logout-post@accounts.test', password=self.password,
        )
        client = Client(enforce_csrf_checks=True)
        client.force_login(user)
        next_url = reverse('events')
        response = client.get(reverse('account_logout'), {'next': next_url})
        self.assertContains(response, f'name="next" value="{next_url}"')
        rejected = client.post(reverse('account_logout'), {'next': next_url})
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(get_user(client).pk, user.pk)
        response = client.post(reverse('account_logout'), {
            'next': next_url,
            'csrfmiddlewaretoken': client.cookies['csrftoken'].value,
        })
        self.assertRedirects(response, next_url, fetch_redirect_response=False)
        self.assertFalse(get_user(client).is_authenticated)

    def test_signup_email_and_confirmation_require_post(self):
        response = self.client.post(reverse('account_signup'), {
            'username': 'new-flow-user', 'email': 'new-flow@accounts.test',
            'password1': self.password, 'password2': self.password,
        }, follow=True)
        self.assert_branded_page(response, 'Check your inbox')
        user = Player.objects.get(username='new-flow-user')
        address = EmailAddress.objects.get(user=user)
        self.assertFalse(address.verified)
        self.assertFalse(get_user(self.client).is_authenticated)
        message = mail.outbox[0]
        self.assertEqual(message.subject, '[Tabula Belli] Confirm your email address')
        self.assertNotIn('example.com', message.body)
        self.assertEqual(message.alternatives[0].mimetype, 'text/html')
        html = message.alternatives[0].content
        self.assertIn('Confirm my email', html)
        url = urlsplit(re.search(r'https?://[^\s]+', message.body).group()).path
        self.assertIn(url, message.body)
        self.assertIn(url, html)
        response = self.client.get(url)
        self.assert_branded_page(response, 'Confirm my email')
        self.assertContains(response, 'name="csrfmiddlewaretoken"')
        address.refresh_from_db()
        self.assertFalse(address.verified)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 302)
        address.refresh_from_db()
        self.assertTrue(address.verified)
        self.client.post(reverse('account_login'), {
            'login': user.username, 'password': self.password,
        })
        self.assertEqual(get_user(self.client).pk, user.pk)

    def test_invalid_confirmation_has_a_styled_recovery_route(self):
        response = self.client.get(reverse('account_confirm_email', args=['invalid']))
        self.assert_branded_page(response, 'expired or is invalid')
        self.assertContains(response, reverse('account_login'))
        self.assertNotContains(response, '>Confirm my email</button>')

    def test_reset_email_form_token_and_new_password(self):
        user = Player.objects.create_user(
            username='flow-reset', email='reset@accounts.test', password=self.password,
        )
        EmailAddress.objects.create(user=user, email=user.email, primary=True, verified=True)
        response = self.client.get(reverse('account_reset_password'))
        self.assert_branded_page(response, 'Send reset link')
        response = self.client.post(reverse('account_reset_password'), {'email': user.email}, follow=True)
        self.assert_branded_page(response, 'If this email address is linked')
        message = mail.outbox[0]
        self.assertEqual(message.subject, '[Tabula Belli] Reset your password')
        self.assertNotIn('example.com', message.body)
        self.assertIn('Choose a new password', message.alternatives[0].content)
        reset_url = re.search(r'https?://[^\s]+', message.body).group()
        response = self.client.get(reset_url, follow=True)
        self.assert_branded_page(response, 'Save new password')
        parser = FormMarkupParser()
        parser.feed(response.content.decode())
        for name in ('password1', 'password2'):
            self.assertIn('form-control', parser.fields[name].get('class', '').split())
        new_password = 'ChangedFlowTestPass456!'
        response = self.client.post(response.request['PATH_INFO'], {
            'password1': new_password, 'password2': new_password,
        }, follow=True)
        self.assert_branded_page(response, 'Password updated')
        user.refresh_from_db()
        self.assertTrue(user.check_password(new_password))
        response = self.client.get(reset_url, follow=True)
        self.assert_branded_page(response, 'Request a new reset link')

    def test_reset_missing_email_has_same_visible_result(self):
        user = Player.objects.create_user(username='flow-existing', email='exists@accounts.test')
        outcomes = []
        for email in [user.email, 'missing@accounts.test']:
            response = self.client.post(reverse('account_reset_password'), {'email': email}, follow=True)
            outcomes.append((response.status_code, response.content))
        self.assertEqual(outcomes[0], outcomes[1])

    def test_invalid_login_preserves_identifier_and_remember_but_not_password(self):
        response = self.client.post(reverse('account_login'), {
            'login': 'portfolio-reader', 'password': 'InvalidEnteredPassword123!',
            'remember': 'on',
        })
        self.assertEqual(response.status_code, 200)
        parser = FormMarkupParser()
        parser.feed(response.content.decode())
        self.assertEqual(parser.fields['login']['value'], 'portfolio-reader')
        self.assertIn('checked', parser.fields['remember'])
        self.assertNotIn('value', parser.fields['password'])
        self.assertFalse(get_user(self.client).is_authenticated)

    def test_invalid_signup_preserves_public_fields_and_links_password_error(self):
        response = self.client.post(reverse('account_signup'), {
            'username': 'portfolio-reader', 'email': 'reader@accounts.test',
            'password1': self.password, 'password2': 'DifferentPassword456!',
        })
        self.assertEqual(response.status_code, 200)
        parser = FormMarkupParser()
        parser.feed(response.content.decode())
        self.assertEqual(parser.fields['username']['value'], 'portfolio-reader')
        self.assertEqual(parser.fields['email']['value'], 'reader@accounts.test')
        self.assertFalse(parser.duplicate_ids)
        for name in ('password1', 'password2'):
            self.assertEqual(parser.fields[name]['id'], f'id_{name}')
            self.assertNotIn('value', parser.fields[name])
        invalid = [field for field in parser.fields.values() if field.get('aria-invalid') == 'true']
        self.assertTrue(invalid)
        for field in invalid:
            for reference in field['aria-describedby'].split():
                self.assertIn(reference, parser.ids)
        self.assertFalse(Player.objects.filter(username='portfolio-reader').exists())
        self.assertEqual(len(mail.outbox), 0)
