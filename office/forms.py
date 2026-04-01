from django import forms
from .models import OfficeServiceRecord, OfficeServicePayment, OfficeServiceRate, OfficeIncome


class OfficeServiceRateForm(forms.ModelForm):
    class Meta:
        model = OfficeServiceRate
        fields = ['rate_per_window', 'rate_per_door', 'effective_from', 'notes', 'is_active']
        widgets = {'effective_from': forms.DateInput(attrs={'type': 'date'})}


class OfficeServiceRecordForm(forms.ModelForm):
    class Meta:
        model = OfficeServiceRecord
        fields = [
            'client_name', 'client_phone', 'client_address',
            'work_description', 'num_windows', 'num_doors',
            'rate_per_window', 'rate_per_door',
            'date_recorded', 'due_date', 'status', 'notes',
        ]
        widgets = {
            'client_address':    forms.Textarea(attrs={'rows': 2}),
            'work_description':  forms.Textarea(attrs={'rows': 2}),
            'notes':             forms.Textarea(attrs={'rows': 2}),
            'date_recorded':     forms.DateInput(attrs={'type': 'date'}),
            'due_date':          forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-fill rates from active rate
        if not kwargs.get('instance'):
            rate = OfficeServiceRate.get_active()
            if rate:
                self.fields['rate_per_window'].initial = rate.rate_per_window
                self.fields['rate_per_door'].initial   = rate.rate_per_door


class OfficeServicePaymentForm(forms.ModelForm):
    class Meta:
        model = OfficeServicePayment
        fields = ['amount', 'payment_date', 'payment_method', 'reference', 'notes']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
            'notes':        forms.Textarea(attrs={'rows': 2}),
        }


class OfficeIncomeForm(forms.ModelForm):
    class Meta:
        model = OfficeIncome
        fields = ['source', 'amount', 'date', 'description']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}
