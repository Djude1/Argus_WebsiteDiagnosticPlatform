# 群眾外包路口停等資料 model
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('analytics', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='IntersectionWaitEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('grid_id', models.CharField(db_index=True, max_length=32, verbose_name='路口網格 ID')),
                ('lat', models.DecimalField(decimal_places=5, max_digits=8, verbose_name='緯度（5 位）')),
                ('lng', models.DecimalField(decimal_places=5, max_digits=9, verbose_name='經度（5 位）')),
                ('duration_sec', models.PositiveIntegerField(verbose_name='停等秒數')),
                ('device_hash', models.CharField(max_length=64, verbose_name='裝置雜湊')),
                ('started_at', models.DateTimeField(verbose_name='開始時間')),
                ('ended_at', models.DateTimeField(verbose_name='結束時間')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='紀錄時間')),
            ],
            options={
                'verbose_name': '路口停等事件',
                'verbose_name_plural': '路口停等事件',
                'ordering': ['-ended_at'],
                'indexes': [
                    models.Index(fields=['grid_id', '-ended_at'], name='analytics_i_grid_id_e3a8f4_idx'),
                ],
            },
        ),
        migrations.CreateModel(
            name='ActiveWaiter',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('grid_id', models.CharField(db_index=True, max_length=32, verbose_name='路口網格 ID')),
                ('device_hash', models.CharField(max_length=64, verbose_name='裝置雜湊')),
                ('last_seen_at', models.DateTimeField(verbose_name='最後回報時間')),
            ],
            options={
                'verbose_name': '即時等候裝置',
                'verbose_name_plural': '即時等候裝置',
                'unique_together': {('grid_id', 'device_hash')},
                'indexes': [
                    models.Index(fields=['grid_id', 'last_seen_at'], name='analytics_a_grid_id_b7c2d1_idx'),
                ],
            },
        ),
    ]
