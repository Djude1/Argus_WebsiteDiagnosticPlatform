from django.urls import path
from .views import (
    IntersectionHeartbeatView,
    IntersectionInfoView,
    IntersectionWaitReportView,
    TrackPageView,
)

urlpatterns = [
    path('track/', TrackPageView.as_view(), name='track-pageview'),
    path('intersections/wait/',      IntersectionWaitReportView.as_view(), name='intersection-wait-report'),
    path('intersections/heartbeat/', IntersectionHeartbeatView.as_view(),  name='intersection-heartbeat'),
    path('intersections/info/',      IntersectionInfoView.as_view(),       name='intersection-info'),
]
