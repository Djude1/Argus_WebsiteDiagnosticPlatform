from django.apps import AppConfig


class McpAccessConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.mcp_access"
    label = "mcp_access"
    verbose_name = "MCP 接入"
