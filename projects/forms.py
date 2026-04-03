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
        self.fields['quotation'].empty_label = '— None —'
        self.fields['invoice'].empty_label   = '— None —'

        # Only show quotations not already linked to a different project
        from quotations.models import Quotation
        # Exclude quotations that have a project, unless it's this project's own quotation
        already_linked = Quotation.objects.filter(project__isnull=False)
        if self.instance and self.instance.pk and self.instance.quotation_id:
            already_linked = already_linked.exclude(pk=self.instance.quotation_id)
        self.fields['quotation'].queryset = (
            Quotation.objects.exclude(pk__in=already_linked.values_list('pk', flat=True))
        )
