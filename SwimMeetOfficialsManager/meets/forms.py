# forms.py

from django import forms
from .models import Meet, Session, Official


class MeetCreateForm(forms.ModelForm):
    class Meta:
        model = Meet
        fields = [
            "name",
            "location",
            "start_date",
            "end_date",
            "description",
            "num_sessions",
            "course_type",
            "num_pools",
            "has_relay_events",
        ]

        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "end_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "name": forms.TextInput(attrs={"class": "form-control form-control-lg"}),
            "location": forms.TextInput(attrs={"class": "form-control form-control-lg"}),
            "num_sessions": forms.NumberInput(attrs={"class": "form-control w-25", "min": 1}),
            "course_type": forms.Select(attrs={"class": "form-select"}),
            "num_pools": forms.NumberInput(attrs={"class": "form-control w-25", "min": 1, "max": 10}),
            "has_relay_events": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


    def clean(self):
        cleaned = super().clean()
        if cleaned["end_date"] < cleaned["start_date"]:
            raise forms.ValidationError("End date must be after start date")
        return cleaned

class SessionEditForm(forms.ModelForm):
    class Meta:
        model = Session
        fields = ['session_number', 'date', 'start_time', 'end_time', 'has_relay_starts', 'offline_mode']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'start_time': forms.TimeInput(attrs={'type': 'time'}),
            'end_time': forms.TimeInput(attrs={'type': 'time'}),
            'has_relay_starts': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'offline_mode': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

class CSVUploadForm(forms.Form):
    file = forms.FileField()
