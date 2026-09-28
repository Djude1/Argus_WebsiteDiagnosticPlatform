from django.urls import path

from apps.mcp_access import views

# /api/mcp/ ：給 MCP 用戶端（Claude Code、Codex…）
mcp_urlpatterns = [
    path("", views.mcp_endpoint, name="mcp-endpoint"),
    path("reports/<str:token>/", views.mcp_report_download, name="mcp-report-download"),
]

# /api/mcp-access/ ：會員區「MCP 接入中心」頁面
manage_urlpatterns = [
    path("overview/", views.mcp_overview, name="mcp-access-overview"),
    path("keys/", views.mcp_create_key, name="mcp-access-key-create"),
    path("keys/<int:key_id>/revoke/", views.mcp_revoke_key, name="mcp-access-key-revoke"),
    path("connection/", views.mcp_connection_check, name="mcp-access-connection"),
]
