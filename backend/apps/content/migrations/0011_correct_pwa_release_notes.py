from django.db import migrations

OLD_NOTES = (
    "首次 PWA 釋出：可在 Chrome / Edge / Safari 「加到主畫面」"
    "後離線使用，含登入、掃描列表、互動報告與購點功能。"
)
NEW_NOTES = (
    "首次 PWA 釋出：可在 Chrome / Edge / Safari 安裝至裝置；"
    "離線時僅提供介面與使用者主動收藏的去識別化報告摘要，登入、付款與完整報告仍需連線。"
)


def correct_release_notes(apps, schema_editor):
    app_release = apps.get_model("content", "AppRelease")
    app_release.objects.filter(
        version="1.0.0",
        platform="pwa",
        release_notes=OLD_NOTES,
    ).update(release_notes=NEW_NOTES)


def restore_release_notes(apps, schema_editor):
    app_release = apps.get_model("content", "AppRelease")
    app_release.objects.filter(
        version="1.0.0",
        platform="pwa",
        release_notes=NEW_NOTES,
    ).update(release_notes=OLD_NOTES)


class Migration(migrations.Migration):
    dependencies = [
        ("content", "0010_seed_real_milestones"),
    ]

    operations = [
        migrations.RunPython(correct_release_notes, restore_release_notes),
    ]
