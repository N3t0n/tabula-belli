import re
from urllib.parse import urlsplit

from allauth.account.models import EmailAddress
from django.contrib.auth import get_user
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.players.models import Player


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class AccountFlowTest(TestCase):
    password = 'StrongFlowTestPass123!'

    def assert_branded_page(self, response, text):
        self.assertContains(response, text)
        self.assertContains(response, 'css/output.css')
        self.assertContains(response, 'Tabula Belli')
        self.assertNotContains(response, '<h2>Menu:</h2>')

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
