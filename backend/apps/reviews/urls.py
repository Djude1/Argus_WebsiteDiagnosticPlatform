from django.urls import path

from apps.reviews.views import (
    create_message,
    list_reviews,
    my_review,
    toggle_message_helpful,
    toggle_review_helpful,
)

urlpatterns = [
    path("", list_reviews, name="reviews-list"),
    path("mine/", my_review, name="reviews-mine"),
    path("<int:review_id>/messages/", create_message, name="reviews-create-message"),
    path("<int:review_id>/helpful/", toggle_review_helpful, name="reviews-helpful"),
    path(
        "messages/<int:message_id>/helpful/",
        toggle_message_helpful,
        name="reviews-message-helpful",
    ),
]
