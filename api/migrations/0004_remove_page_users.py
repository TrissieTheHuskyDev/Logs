# Generated by Django 2.2.4 on 2019-08-23 12:40

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0003_log_data'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='page',
            name='users',
        ),
    ]