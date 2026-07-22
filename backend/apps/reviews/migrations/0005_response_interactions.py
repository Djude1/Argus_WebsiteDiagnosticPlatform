import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("reviews", "0004_reviewreport_reviewresponse_reviewrevision_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReviewResponseHelpful",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "response",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="helpful_marks",
                        to="reviews.reviewresponse",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="review_response_helpfuls",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.RemoveConstraint(
            model_name="reviewreport",
            name="uniq_review_reporter",
        ),
        migrations.AddField(
            model_name="reviewreport",
            name="response",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reports",
                to="reviews.reviewresponse",
            ),
        ),
        migrations.AddConstraint(
            model_name="reviewresponsehelpful",
            constraint=models.UniqueConstraint(
                fields=("response", "user"),
                name="uniq_response_helpful",
            ),
        ),
        migrations.AddConstraint(
            model_name="reviewreport",
            constraint=models.UniqueConstraint(
                condition=models.Q(("response__isnull", True)),
                fields=("review", "reporter"),
                name="uniq_review_reporter",
            ),
        ),
        migrations.AddConstraint(
            model_name="reviewreport",
            constraint=models.UniqueConstraint(
                condition=models.Q(("response__isnull", False)),
                fields=("response", "reporter"),
                name="uniq_response_reporter",
            ),
        ),
    ]
