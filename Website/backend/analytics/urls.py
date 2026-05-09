from django.urls import path
from .views import TrackPageView

urlpatterns = [
    path('track/', TrackPageView.as_view(), name='track-pageview'),
]
