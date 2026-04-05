from django.urls import path
from .views import (
    SiteContentView, AppConfigView,
    ImpactFeedbackCreateView, AppAnnouncementsView,
    WebsiteAnnouncementsView,
)

urlpatterns = [
    path('',                       SiteContentView.as_view(),          name='site-content'),
    path('app-config/',            AppConfigView.as_view(),            name='app-config'),
    path('impact-feedback/',       ImpactFeedbackCreateView.as_view(), name='impact-feedback'),
    path('announcements/',         AppAnnouncementsView.as_view(),     name='app-announcements'),
    path('website-announcements/', WebsiteAnnouncementsView.as_view(), name='website-announcements'),
]
