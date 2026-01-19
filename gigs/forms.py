from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
from .models import GigShift, GigCompanyEntry, MileageRate
from decimal import Decimal

class GigShiftForm(forms.ModelForm):
    class Meta:
        model = GigShift
        fields = [
            "date", "start_time", "end_time",
            "miles", "mpg", "gas_price",
            "company_mix_note",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "start_time": forms.TimeInput(attrs={"type": "time"}),
            "end_time": forms.TimeInput(attrs={"type": "time"}),
            "miles": forms.NumberInput(
                attrs={
                    "class": "w-full border rounded px-2 py-1 text-sm text-right",
                    "min": "0",
                    "step": "0.1",
                }
            ),
            "mpg": forms.NumberInput(
                attrs={
                    "class": "w-full border rounded px-2 py-1 text-sm text-right",
                    "min": "0",
                    "step": "0.1",
                }
            ),
            "gas_price": forms.NumberInput(
                attrs={
                    "class": "w-full border rounded px-2 py-1 text-sm text-right",
                    "min": "0",
                    "step": "0.001",
                }
            ),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_time")
        end = cleaned.get("end_time")

        if start and end and end <= start:
            raise ValidationError("End time must be later than start time.")

        return cleaned
    
    def clean_miles(self):
        miles = self.cleaned_data.get("miles")
        if miles is None:
            return miles
        if miles < 0:
            raise ValidationError("Miles cannot be negative.")
        return miles

    def clean_mpg(self):
        mpg = self.cleaned_data.get("mpg")
        if mpg is None:
            return mpg
        if mpg < 0:
            raise ValidationError("MPG cannot be negative.")
        return mpg

    def clean_gas_price(self):
        gas_price = self.cleaned_data.get("gas_price")
        if gas_price is None:
            return gas_price
        if gas_price < 0:
            raise ValidationError("Gas price cannot be negative.")
        return gas_price

class GigCompanyEntryForm(forms.ModelForm):
    class Meta:
        model = GigCompanyEntry
        fields = [
            "company",
            "deliveries",
            "gross_earnings",
            "tips_count",
            "tips_amount",
        ]
        widgets = {
            "deliveries": forms.NumberInput(
                attrs={
                    "class": "w-full text-right border rounded px-1 py-0.5 text-xs",
                    "min": "0",
                    "step": "1",
                }
            ),
            "gross_earnings": forms.NumberInput(
                attrs={
                    "class": "gross-earnings w-full text-right border rounded px-1 py-0.5 text-xs",
                    "min": "0",
                    "step": "0.01",
                }
            ),
            "tips_count": forms.NumberInput(
                attrs={
                    "class": "tips-count w-full text-right border rounded px-1 py-0.5 text-xs",
                    "min": "0",
                    "step": "1",
                }
            ),
            "tips_amount": forms.NumberInput(
                attrs={
                    "class": "tips-amount w-full text-right border rounded px-1 py-0.5 text-xs",
                    "min": "0",
                    "step": "0.01",
                }
            ),
        }

    def clean_deliveries(self):
        deliveries = self.cleaned_data.get("deliveries")

        if deliveries is None:
            return deliveries

        if deliveries < 0:
            raise ValidationError("Deliveries cannot be negative.")

        return deliveries

    def clean_tips_count(self):
        tips_count = self.cleaned_data.get("tips_count")
        deliveries = self.cleaned_data.get("deliveries")

        if tips_count is None:
            return tips_count

        if tips_count < 0:
            raise ValidationError("Tips # cannot be negative.")

        # If deliveries has already been cleaned and is not None
        if deliveries is not None and tips_count > deliveries:
            raise ValidationError("Tips # cannot exceed total deliveries.")

        return tips_count

    def clean(self):
        cleaned_data = super().clean()

        gross = cleaned_data.get("gross_earnings")
        tips_amount = cleaned_data.get("tips_amount")

        # normalize to Decimal for comparisons
        gross = gross if gross is not None else Decimal("0")
        tips_amount = tips_amount if tips_amount is not None else Decimal("0")

        if gross < 0:
            self.add_error("gross_earnings", "Gross earnings cannot be negative.")

        if tips_amount < 0:
            self.add_error("tips_amount", "Tip amount cannot be negative.")

        if tips_amount > gross:
            self.add_error(
                "tips_amount",
                "Tip amount cannot be greater than gross earnings.",
            )

        return cleaned_data
        
# ⬇️ This is at module level, not indented under a class
GigCompanyFormSet = inlineformset_factory(
    GigShift,
    GigCompanyEntry,
    form=GigCompanyEntryForm,
    extra=4,
    can_delete=True,
)

class MileageRateForm(forms.ModelForm):
    class Meta:
        model = MileageRate
        fields = ["effective_date", "rate", "note"]
        widgets = {
            "effective_date": forms.DateInput(attrs={"type": "date", "class": "border rounded px-2 py-1"}),
            "rate": forms.NumberInput(attrs={"step": "0.001", "class": "border rounded px-2 py-1"}),
            "note": forms.TextInput(attrs={"class": "border rounded px-2 py-1"}),
        }