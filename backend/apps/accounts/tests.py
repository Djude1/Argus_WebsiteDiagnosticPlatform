from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase


@override_settings(GOOGLE_OAUTH_CLIENT_ID="fake-client-id")
class GoogleLoginTests(APITestCase):
    def setUp(self):
        self.url = reverse("google-login")

    @patch("apps.accounts.views.id_token.verify_oauth2_token")
    def test_google_login_creates_new_user(self, mock_verify):
        mock_verify.return_value = {
            "email": "new@example.com",
            "email_verified": True,
            "given_name": "New",
            "family_name": "User",
        }

        response = self.client.post(self.url, {"credential": "fake-token"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        user = get_user_model().objects.get(username="new@example.com")
        self.assertEqual(user.email, "new@example.com")
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

    @patch("apps.accounts.views.id_token.verify_oauth2_token")
    def test_google_login_reuses_existing_user(self, mock_verify):
        get_user_model().objects.create_user(
            username="existing@example.com",
            email="existing@example.com",
        )
        mock_verify.return_value = {
            "email": "existing@example.com",
            "email_verified": True,
        }

        response = self.client.post(self.url, {"credential": "fake-token"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            get_user_model().objects.filter(username="existing@example.com").count(),
            1,
        )

    @patch("apps.accounts.views.id_token.verify_oauth2_token")
    def test_google_login_rejects_unverified_email(self, mock_verify):
        mock_verify.return_value = {
            "email": "unverified@example.com",
            "email_verified": False,
        }

        response = self.client.post(self.url, {"credential": "fake-token"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            get_user_model().objects.filter(username="unverified@example.com").exists()
        )

    @patch("apps.accounts.views.id_token.verify_oauth2_token")
    def test_google_login_rejects_invalid_token(self, mock_verify):
        mock_verify.side_effect = ValueError("Token expired")

        response = self.client.post(self.url, {"credential": "bad-token"}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_google_login_requires_credential(self):
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class GoogleLoginConfigTests(APITestCase):
    @override_settings(GOOGLE_OAUTH_CLIENT_ID="")
    def test_returns_503_when_client_id_missing(self):
        response = self.client.post(
            reverse("google-login"),
            {"credential": "any"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)

class EmailAuthTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_dev_login_route_is_removed(self):
        resp = self.client.post(
            "/api/auth/dev-login/",
            {"username": "dev-user"},
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 404)

    def test_register_creates_user(self):
        resp = self.client.post(
            "/api/auth/register/",
            {"email": "newuser@example.com", "password": "StrongPass123!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.assertTrue(User.objects.filter(username="newuser@example.com").exists())

    def test_register_duplicate_email_fails(self):
        from django.contrib.auth import get_user_model
        User = get_user_model()
        User.objects.create_user(username="dup@example.com", email="dup@example.com", password="pw")
        resp = self.client.post(
            "/api/auth/register/",
            {"email": "dup@example.com", "password": "AnotherPass123!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_email_login_returns_token(self):
        User = get_user_model()
        User.objects.create_user(
            username="logintest@example.com",
            email="logintest@example.com",
            password="MyPass999!",
        )
        resp = self.client.post(
            "/api/auth/email-login/",
            {"email": "logintest@example.com", "password": "MyPass999!"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.json())

    def test_email_login_wrong_password_fails(self):
        User = get_user_model()
        User.objects.create_user(
            username="badpw@example.com",
            email="badpw@example.com",
            password="correct",
        )
        resp = self.client.post(
            "/api/auth/email-login/",
            {"email": "badpw@example.com", "password": "wrong"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 400)
