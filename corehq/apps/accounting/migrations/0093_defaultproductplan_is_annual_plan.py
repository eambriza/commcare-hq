# Generated by Django 4.2.11 on 2024-05-02 16:17

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0092_revert_application_error_report_priv"),
    ]

    operations = [
        migrations.AddField(
            model_name="defaultproductplan",
            name="is_annual_plan",
            field=models.BooleanField(default=False),
        ),
    ]
