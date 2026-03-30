from django import forms
from .models import Invoice, InvoiceItem, Quote, QuoteItem


class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['project', 'invoice_number', 'client_name', 'client_address', 'description', 'total_amount', 'status', 'due_date']
        widgets = {
            'project': forms.Select(attrs={'class': 'form-select'}),
            'invoice_number': forms.TextInput(attrs={'class': 'form-control'}),
            'client_name': forms.TextInput(attrs={'class': 'form-control'}),
            'client_address': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }


class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ['description', 'quantity', 'unit_price']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }


class QuoteForm(forms.ModelForm):
    class Meta:
        model = Quote
        fields = ['project', 'quote_number', 'client_name', 'project_name', 'status', 'total_amount', 'notes', 'valid_until']
        widgets = {
            'project': forms.Select(attrs={'class': 'form-select'}),
            'quote_number': forms.TextInput(attrs={'class': 'form-control'}),
            'client_name': forms.TextInput(attrs={'class': 'form-control'}),
            'project_name': forms.TextInput(attrs={'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'total_amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'valid_until': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }
