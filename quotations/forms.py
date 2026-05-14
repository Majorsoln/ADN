from django import forms
from .models import Quotation, QuotationItem, QuotationMaterial


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = [
            'client_name', 'client_phone', 'client_email', 'client_address',
            'project_name', 'installation_days', 'quote_date', 'valid_until',
            'status', 'notes',
            'discount_name', 'discount_duration', 'discount_type', 'discount_value',
            'vat_enabled', 'vat_rate',
            'service_levy_enabled', 'service_levy_rate',
            'skills_levy_enabled', 'skills_levy_rate',
            'withholding_enabled', 'withholding_rate',
            'custom1_name', 'custom1_rate', 'custom1_enabled',
            'custom2_name', 'custom2_rate', 'custom2_enabled',
        ]
        widgets = {
            'client_address': forms.Textarea(attrs={'rows': 2}),
            'notes': forms.Textarea(attrs={'rows': 3}),
            'quote_date': forms.DateInput(attrs={'type': 'date'}),
            'valid_until': forms.DateInput(attrs={'type': 'date'}),
        }


class QuotationItemForm(forms.ModelForm):
    class Meta:
        model = QuotationItem
        fields = ['item_type', 'description', 'width', 'height', 'quantity']
        widgets = {
            'description': forms.TextInput(),
        }


class QuotationMaterialForm(forms.ModelForm):
    class Meta:
        model = QuotationMaterial
        fields = ['material_name', 'price_per_sqm', 'notes']
