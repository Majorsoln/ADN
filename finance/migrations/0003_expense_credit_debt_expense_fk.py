from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('finance', '0002_debt_debtpayment'),
    ]

    operations = [
        # Add expense FK to Debt so credit expenses can be linked to a debt record
        migrations.AddField(
            model_name='debt',
            name='expense',
            field=models.ForeignKey(
                blank=True,
                help_text='Expense recorded on credit that created this debt',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='debts',
                to='finance.expense',
            ),
        ),
    ]
