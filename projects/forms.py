from django import forms
from .models import Project


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            'name', 'client_name', 'client_phone', 'description',
            'quotation', 'invoice',
            'status', 'start_date', 'target_date', 'completion_date',
            'notes',
        ]
        widgets = {
            'start_date':      forms.DateInput(attrs={'type': 'date'}),
            'target_date':     forms.DateInput(attrs={'type': 'date'}),
            'completion_date': forms.DateInput(attrs={'type': 'date'}),
            'description':     forms.Textarea(attrs={'rows': 2}),
            'notes':           forms.Textarea(attrs={'rows': 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['quotation'].required = False
        self.fields['invoice'].required   = False
        self.fields['quotation'].empty_label = '— Select Quotation —'
        self.fields['invoice'].empty_label   = '— Select Invoice —'
