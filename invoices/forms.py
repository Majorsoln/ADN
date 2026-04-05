from django import forms
from .models import Invoice, InvoicePayment


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            'client_name', 'client_phone', 'client_email', 'client_address',
            'quote_ref', 'quotation',
            'invoice_date', 'due_date', 'completion_date',
            'description',
            'contract_amount', 'advance_paid', 'advance_payment_method',
            'status', 'notes',
        ]
        widgets = {
            'client_address': forms.Textarea(attrs={'rows': 2}),
            'description': forms.Textarea(attrs={'rows': 3}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'invoice_date':    forms.DateInput(attrs={'type': 'date'}),
            'due_date':        forms.DateInput(attrs={'type': 'date'}),
            'completion_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['quotation'].required = False
        self.fields['quotation'].empty_label = '— None —'


class PaymentForm(forms.ModelForm):
    class Meta:
        model = InvoicePayment
        fields = ['amount', 'payment_date', 'payment_method', 'reference', 'notes']
        widgets = {
            'payment_date': forms.DateInput(attrs={'type': 'date'}),
            'notes': forms.Textarea(attrs={'rows': 2}),
        }
