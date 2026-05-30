from django.urls import path

from apps.insights.views import phishing_email_check, phishing_url_check, speed_test

urlpatterns = [
    path("speed-test/", speed_test, name="insights-speed-test"),
    path("phishing-url/", phishing_url_check, name="insights-phishing-url"),
    path("phishing-email/", phishing_email_check, name="insights-phishing-email"),
]
