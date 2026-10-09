from django.urls import path

from apps.insights.views import (
    phishing_email_check,
    phishing_url_check,
    quick_scan,
    speed_test,
    speed_test_pagespeed,
)

urlpatterns = [
    path("speed-test/", speed_test, name="insights-speed-test"),
    path(
        "speed-test/pagespeed/<str:job_id>/",
        speed_test_pagespeed,
        name="insights-speed-test-pagespeed",
    ),
    path("phishing-url/", phishing_url_check, name="insights-phishing-url"),
    path("phishing-email/", phishing_email_check, name="insights-phishing-email"),
    path("quick-scan/", quick_scan, name="insights-quick-scan"),
]
