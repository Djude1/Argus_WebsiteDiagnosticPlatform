from django.urls import path

from apps.reviews.views import (
    list_reviews,
    my_review,
    report_response,
    report_review,
    reviews_summary,
    toggle_response_helpful,
    toggle_review_helpful,
)

urlpatterns = [
    path("", list_reviews, name="reviews-list"),
    path("summary/", reviews_summary, name="reviews-summary"),
    path("mine/", my_review, name="reviews-mine"),
    path("<int:review_id>/helpful/", toggle_review_helpful, name="reviews-helpful"),
    path("<int:review_id>/report/", report_review, name="reviews-report"),
    path(
        "responses/<int:response_id>/helpful/",
        toggle_response_helpful,
        name="reviews-response-helpful",
    ),
    path(
        "responses/<int:response_id>/report/",
        report_response,
        name="reviews-response-report",
    ),
]
