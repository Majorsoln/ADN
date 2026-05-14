from django.apps import AppConfig


class FinanceConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'finance'
    verbose_name = 'Finance & Reporting'

    def ready(self):
        # Seed default expense categories after migrations run
        from django.db.models.signals import post_migrate
        from django.dispatch import receiver

        @receiver(post_migrate, sender=self)
        def seed_categories(sender, **kwargs):
            from finance.models import ExpenseCategory
            ExpenseCategory.create_defaults()
