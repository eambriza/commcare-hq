# Generated by Django 3.2.16 on 2023-04-05 06:55

from django.core.management import call_command
from django.db import migrations

from corehq.apps.accounting.models import SoftwarePlanEdition
from corehq.privileges import EXPORT_MULTISORT
from corehq.util.django_migrations import skip_on_fresh_install
from django_prbac.models import Grant, Role


@skip_on_fresh_install
def _grandfather_export_multisort_priv(apps, schema_editor):
    call_command('cchq_prbac_bootstrap')

    # EXPORT_MULTISORT are Standard Plan and higher
    skip_editions = ','.join((
        SoftwarePlanEdition.PAUSED,
        SoftwarePlanEdition.COMMUNITY,
    ))
    call_command(
        'cchq_prbac_grandfather_privs',
        EXPORT_MULTISORT,
        skip_edition=skip_editions,
        noinput=True,
    )


@skip_on_fresh_install
def _remove_export_multisort_role_and_grants(apps, schema_editor):
    role = Role.objects.get(slug=EXPORT_MULTISORT)
    grants = Grant.objects.filter(to_role_id=role.id)

    grants.delete()
    role.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0071_add_billingaccountwebuserhistory'),
    ]

    operations = [
        migrations.RunPython(
            _grandfather_export_multisort_priv,
            reverse_code=_remove_export_multisort_role_and_grants,
        ),
    ]
