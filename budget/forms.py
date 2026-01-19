from django import forms
from .models import Transaction, Transfer, Account, SubCategory

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

