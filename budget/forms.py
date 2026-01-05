from django import forms
from django.forms import inlineformset_factory
from django.core.exceptions import ValidationError
from .models import Transaction, Transfer, Account, SubCategory, GigShift, GigCompanyEntry, MileageRate
from decimal import Decimal

BASE_INPUT  = "block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3c4e61] focus:border-transparent"
BASE_SELECT = "block w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#3c4e61]"
BASE_CHECK  = "rounded border-gray-300 text-[#3c4e61] focus:ring-[#3c4e61]"

class DisabledPlaceholderSelect(forms.Select):
    """Makes the empty_label option disabled (and hidden in most browsers)."""
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value in (None, "",):  # the empty_label option
            option["attrs"]["disabled"] = True
            option["attrs"]["hidden"] = True  # many browsers hide it from the list
        return option


class TransactionForm(forms.ModelForm):
    # override the auto-generated fields so we can set empty_label
    # Use a placeholder, not None, so the select starts blank
    account = forms.ModelChoiceField(
        queryset=Account.objects.none(),            # fill in __init__
        empty_label="Select account",               # ← shows a blank placeholder (not dashes)
        required=True,
        widget=DisabledPlaceholderSelect(attrs={"class": BASE_SELECT}),
    )
    
    subcategory = forms.ModelChoiceField(
        queryset=SubCategory.objects.none(),        # fill in __init__
        empty_label="Select subcategory",           # ← blank placeholder
        required=True,
        widget=DisabledPlaceholderSelect(attrs={"class": BASE_SELECT}),
    )

    class Meta:
        model = Transaction
        fields = [
            'account',
            'date',
            'subcategory',
            'description',
            'debit',
            'credit',
            'cleared',
            'write_off',
        ]

        widgets = {
            # NOTE: don't try to pass queryset/choices via widget attrs — it does nothing.
            "date":        forms.DateInput(attrs={"type": "date", "class": BASE_SELECT}),
            "description": forms.TextInput(attrs={"class": BASE_INPUT, "placeholder": "Description"}),
            "debit":       forms.NumberInput(attrs={"class": BASE_INPUT, "step": "0.01"}),
            "credit":      forms.NumberInput(attrs={"class": BASE_INPUT, "step": "0.01"}),
            "cleared":     forms.CheckboxInput(attrs={"class": BASE_CHECK}),
            "write_off":   forms.CheckboxInput(attrs={"class": BASE_CHECK}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # set real querysets here so the form can be imported without hitting the DB at import time
        self.fields["account"].queryset = Account.objects.filter(active=True).order_by("name")
        self.fields["subcategory"].queryset = SubCategory.objects.order_by("name")
        # ensure no initial selection
        self.fields["account"].initial = None
        self.fields["subcategory"].initial = None

        # Fallback class for any field not covered above
        for field in self.fields.values():
            cls = field.widget.attrs.get("class")
            if not cls:
                field.widget.attrs["class"] = BASE_INPUT
        # Optional: Add filtering or logging by transaction_type if needed later

    # Optional: nicer validation messages
    def clean_account(self):
            v = self.cleaned_data.get("account")
            if not v:
                raise forms.ValidationError("Please choose an account.")
            return v

    def clean_subcategory(self):
        v = self.cleaned_data.get("subcategory")
        if not v:
            raise forms.ValidationError("Please choose a subcategory.")
        return v
        
    
    def clean(self):
        cleaned_data = super().clean()
        debit = cleaned_data.get("debit") or 0
        credit = cleaned_data.get("credit") or 0
        cleaned_data["amount"] = credit - debit
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.amount = (instance.credit or 0) - (instance.debit or 0)
        if commit:
            instance.save()
        return instance
    
class TransferForm(forms.ModelForm):
    class Meta:
        model = Transfer
        fields = ["from_account","to_account","date","amount","description","cleared","write_off"]
        widgets = {
            "from_account":  DisabledPlaceholderSelect(attrs={"class": BASE_SELECT}),
            "to_account":    DisabledPlaceholderSelect(attrs={"class": BASE_SELECT}),
            "date":          forms.DateInput(attrs={"type": "date", "class": BASE_SELECT}),
            "amount":        forms.NumberInput(attrs={"class": BASE_INPUT, "step": "0.01"}),
            "description":   forms.TextInput(attrs={"class": BASE_INPUT, "placeholder": "Optional memo/description"}),
            "cleared":       forms.CheckboxInput(attrs={"class": BASE_CHECK}),
            "write_off":     forms.CheckboxInput(attrs={"class": BASE_CHECK}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Account.objects.filter(active=True).order_by("name")
        self.fields["from_account"].queryset = qs
        self.fields["to_account"].queryset = qs
        self.fields["from_account"].empty_label = "Select account"
        self.fields["to_account"].empty_label = "Select account"

    def clean(self):
        cleaned = super().clean()
        fa, ta = cleaned.get("from_account"), cleaned.get("to_account")
        if fa and ta and fa == ta:
            self.add_error("to_account", "From and To accounts must be different.")
        return cleaned


class infer_transaction_type(Account):
    def infer_transaction_type(self):
        if self.account.account_type == 'LOAN':
            return 'LOAN_PAYMENT'
        elif self.account.account_type == 'CHARGE':
            return 'CC_PAYMENT'
        else:
            return 'UNKNOWN'

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