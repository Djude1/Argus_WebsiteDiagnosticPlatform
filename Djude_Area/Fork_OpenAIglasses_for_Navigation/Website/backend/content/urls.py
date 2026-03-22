from django.urls import path
from .views import SiteContentView, AppConfigView

urlpatterns = [
    path('',           SiteContentView.as_view(), name='site-content'),
    path('app-config/', AppConfigView.as_view(),  name='app-config'),
]
