"""登入事件同時間戳記時，後台仍必須先列出較新的事件。"""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import LoginEvent


class LoginEventOrderingTests(APITestCase):
    def test_same_timestamp_returns_last_created_event_first(self):
        user = get_user_model().objects.create_user(username="ordering-user")
        admin = get_user_model().objects.create_user(username="ordering-admin", is_staff=True)
        timestamp = timezone.now()
        with patch("django.utils.timezone.now", return_value=timestamp):
            LoginEvent.objects.create(user=user, method=LoginEvent.Method.PASSWORD)
            LoginEvent.objects.create(user=user, method=LoginEvent.Method.GOOGLE)

        self.client.force_authenticate(admin)
        response = self.client.get(reverse("admin-user-login-events", args=[user.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [event["method"] for event in response.data["events"]],
            [LoginEvent.Method.GOOGLE, LoginEvent.Method.PASSWORD],
        )
