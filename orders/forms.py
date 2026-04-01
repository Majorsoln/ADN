from django import forms
from .models import MaterialOrder, MaterialOrderItem


class MaterialOrderForm(forms.ModelForm):
    class Meta:
        model = MaterialOrder
        fields = ['supplier_name', 'order_date', 'expected_delivery', 'actual_delivery', 'status', 'notes']
        widgets = {
            'order_date':         forms.DateInput(attrs={'type': 'date'}),
            'expected_delivery':  forms.DateInput(attrs={'type': 'date'}),
            'actual_delivery':    forms.DateInput(attrs={'type': 'date'}),
            'notes':              forms.Textarea(attrs={'rows': 2}),
        }
