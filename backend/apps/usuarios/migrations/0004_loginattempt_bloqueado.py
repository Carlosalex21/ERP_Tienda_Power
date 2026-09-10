# Generated manually para el sistema ERP SaaS Multi-Tenant.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('usuarios', '0003_alter_logactividad_options_alter_rol_options_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='usermetadata',
            name='bloqueado_hasta',
            field=models.DateTimeField(
                blank=True,
                help_text='Fecha/hora hasta la que la cuenta queda bloqueada por intentos fallidos.',
                null=True,
                verbose_name='Bloqueado hasta',
            ),
        ),
        migrations.CreateModel(
            name='LoginAttempt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ip', models.GenericIPAddressField(blank=True, null=True, verbose_name='Dirección IP')),
                ('success', models.BooleanField(default=False, verbose_name='¿Éxito?')),
                ('timestamp', models.DateTimeField(auto_now_add=True, verbose_name='Fecha y Hora')),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='login_attempts',
                    to='auth.user',
                    verbose_name='Usuario',
                )),
            ],
            options={
                'verbose_name': 'Intento de Inicio de Sesión',
                'verbose_name_plural': 'Intentos de Inicio de Sesión',
                'db_table': 'LoginAttempt',
                'ordering': ['-timestamp'],
                'indexes': [
                    models.Index(fields=['user', 'timestamp'], name='idx_login_user_ts'),
                ],
            },
        ),
    ]
