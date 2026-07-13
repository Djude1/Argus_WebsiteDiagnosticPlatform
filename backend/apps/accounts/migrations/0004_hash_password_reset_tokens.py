from django.db import migrations, models


def invalidate_plaintext_tokens(apps, schema_editor):
    PasswordResetToken = apps.get_model("accounts", "PasswordResetToken")
    PasswordResetToken.objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_passwordresettoken"),
    ]

    operations = [
        migrations.RenameField(
            model_name="passwordresettoken",
            old_name="token",
            new_name="token_digest",
        ),
        migrations.AlterField(
            model_name="passwordresettoken",
            name="token_digest",
            field=models.CharField(db_index=True, max_length=64, unique=True),
        ),
        migrations.RunPython(invalidate_plaintext_tokens, migrations.RunPython.noop),
    ]
