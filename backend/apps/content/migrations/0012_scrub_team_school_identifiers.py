"""清除團隊成員的學校識別資訊（學號、學校 email），改填 GitHub 帳號。

比賽規定不得暴露學校相關訊息，故：
- student_id 清空（欄位保留供後台內部識別，但公開 API 不再輸出）
- email 清空（聯絡資訊改放工程師標準公開身份 GitHub）
- github_url 填入各成員帳號

同時 AlterField student_id 的 help_text 為中性描述（移除學號範例字樣）。
以 name 為鍵比對成員（student_id 即將清空，無法再當鍵）。
reverse 時不刪除（沿用 0009 慣例，避免回滾誤刪後台已編輯的真實資料）。
"""

from django.db import migrations, models


# 以 name 為鍵（student_id 清空後無法當冪等鍵）
MEMBER_SCRUB = [
    {"name": "侯雨利", "github_url": "https://github.com/Djude1"},
    {"name": "羅建凱", "github_url": "https://github.com/SmallLoOwO"},
    {"name": "李仕傑", "github_url": "https://github.com/XiuJie2"},
    {"name": "曾子睿", "github_url": "https://github.com/ZengAnatoly"},
]


def scrub(apps, schema_editor):
    Member = apps.get_model("content", "TeamMember")
    for data in MEMBER_SCRUB:
        Member.objects.filter(name=data["name"]).update(
            student_id="",
            email="",
            github_url=data["github_url"],
        )


class Migration(migrations.Migration):
    dependencies = [("content", "0011_correct_pwa_release_notes")]
    operations = [
        migrations.AlterField(
            model_name="teammember",
            name="student_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="內部識別用，不對外公開顯示",
                max_length=20,
            ),
        ),
        migrations.RunPython(scrub, migrations.RunPython.noop),
    ]
