from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("rrhh", "0006_conceptonomina_nominaempleado_horas_extra_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="nominaempleadoconcepto",
            name="concepto",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name="+", to="rrhh.conceptonomina",
            ),
        ),
    ]
