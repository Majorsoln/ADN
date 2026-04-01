from django import forms
from django.utils import timezone
from .models import Expense, ExpenseCategory, ReportSnapshot


class ExpenseForm(forms.ModelForm):
    date = forms.DateField(
        widget=forms.DateInput(attrs={'type': 'date'}),
        initial=timezone.now,
    )

    class Meta:
        model = Expense
        fields = ['date', 'category', 'amount', 'description',
                  'paid_to', 'payment_method', 'reference', 'project', 'notes']
        widgets = {
            'description': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = ExpenseCategory.objects.filter(is_active=True)
        self.fields['project'].required = False
        self.fields['project'].empty_label = '— No project —'
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.Select)):
                field.widget.attrs.setdefault('class', 'form-control')
            elif isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault('class', 'form-select')


class ReportFilterForm(forms.Form):
    PERIOD_CHOICES = [
        ('today',     'Today'),
        ('this_week', 'This Week'),
        ('this_month', 'This Month'),
        ('last_month', 'Last Month'),
        ('custom',    'Custom Range'),
    ]

    period   = forms.ChoiceField(choices=PERIOD_CHOICES, initial='this_month',
                                 widget=forms.Select(attrs={'class': 'form-select'}))
    date_from = forms.DateField(required=False,
                                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))
    date_to   = forms.DateField(required=False,
                                widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}))

    def resolve_period(self):
        """Return (date_from, date_to) based on selected period."""
        from datetime import date, timedelta
        from calendar import monthrange

        period = self.cleaned_data.get('period', 'this_month')
        today = date.today()

        if period == 'today':
            return today, today
        elif period == 'this_week':
            start = today - timedelta(days=today.weekday())
            return start, today
        elif period == 'this_month':
            first = date(today.year, today.month, 1)
            return first, today
        elif period == 'last_month':
            first_this = date(today.year, today.month, 1)
            last_month_end = first_this - timedelta(days=1)
            last_month_start = date(last_month_end.year, last_month_end.month, 1)
            return last_month_start, last_month_end
        else:  # custom
            df = self.cleaned_data.get('date_from') or date(today.year, 1, 1)
            dt = self.cleaned_data.get('date_to') or today
            return df, dt


class SaveReportForm(forms.ModelForm):
    class Meta:
        model = ReportSnapshot
        fields = ['report_type', 'title', 'period_from', 'period_to', 'notes']
        widgets = {
            'period_from': forms.DateInput(attrs={'type': 'date'}),
            'period_to': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault('class', 'form-select')
            elif not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', 'form-control')
