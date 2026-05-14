from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('quotations', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotation',
            name='accepted_material',
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='+',
                help_text='Material option accepted by the client',
                to='quotations.quotationmaterial',
            ),
        ),
    ]
