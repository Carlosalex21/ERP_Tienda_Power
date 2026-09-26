from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("tenants", "0017_plan_modulos"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscriptionpayment",
            name="credito_aplicado",
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=10,
                help_text="Crédito acreditado por el tiempo no consumido del plan anterior (upgrade a mitad de período). 0 en renovaciones del mismo plan.",
            ),
        ),
    ]
