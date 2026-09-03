from decimal import Decimal

from django import forms

from .models import CreditPayment, Expense, Item, OtherService, Sale, Sale, Supplier


class SaleForm(forms.ModelForm):
    class Meta:
        model = Sale
        fields = [
            "item", "weight_kg", "gross", "payment_method",
            "customer_name", "customer_ctp", "remarks",
        ]
        widgets = {
            "weight_kg": forms.NumberInput(attrs={
                "step": "0.001", "placeholder": "e.g. 2.5",
            }),
            "gross": forms.NumberInput(attrs={
                "step": "0.01", "placeholder": "fill this OR weight, not both",
            }),
            "customer_name": forms.TextInput(attrs={
                "placeholder": "Customer name (optional)",
            }),
            "customer_ctp": forms.TextInput(attrs={
                "placeholder": "CTP batch (optional)",
            }),
            "remarks": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["item"].queryset = Item.objects.filter(active=True)
        self.fields["item"].empty_label = "— Select item —"
        self.fields["weight_kg"].required = False
        self.fields["gross"].required = False
        self.fields["customer_name"].label = "Customer Name"
        self.fields["customer_name"].required = False
        self.fields["customer_ctp"].label = "Sale CTP"
        self.fields["customer_ctp"].required = False
        self.fields["customer_name"].widget.attrs["list"] = "creditor-datalist"
        self.fields["customer_ctp"].widget.attrs["list"] = "ctp-datalist"


class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = ["description", "amount", "payment_method"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["description"].widget.attrs["list"] = "expense-list"
        self.fields["description"].widget.attrs["placeholder"] = "e.g. Transport"


class CreditPaymentForm(forms.ModelForm):
    class Meta:
        model = CreditPayment
        fields = ["sale", "customer_name", "customer_ctp", "amount", "payment_mode", "note"]
        widgets = {
            "payment_mode": forms.Select(choices=CreditPayment.PAYMENT_MODE_CHOICES),
            "customer_ctp": forms.TextInput(attrs={"placeholder": "CTP batch (optional)"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        credit_sales = Sale.objects.filter(
            payment_method=Sale.CREDIT
        ).select_related("item").order_by("-date", "customer_name")
        unpaid = [s for s in credit_sales if s.balance > 0]
        choices = [("", "— Select a sale —")]
        for s in unpaid:
            label = f"{s.reference} | {s.customer_name} | {s.item.name} | Gross {s.gross} | Paid {s.total_paid} | Bal {s.balance}"
            choices.append((s.pk, label))
        self.fields["sale"].choices = choices
        self.fields["sale"].required = True
        self.fields["customer_name"].required = False
        self.fields["customer_name"].widget.attrs["list"] = "creditor-list-bottom"
        self.fields["customer_name"].widget.attrs["placeholder"] = "Customer name"
        self.fields["customer_ctp"].required = False
        self.fields["customer_ctp"].widget.attrs["list"] = "ctp-list-bottom"


class OtherServiceForm(forms.ModelForm):
    class Meta:
        model = OtherService
        fields = ["description", "amount", "payment_method"]


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ["name", "price_per_kg", "active"]
        widgets = {
            "price_per_kg": forms.NumberInput(attrs={"step": "0.01"}),
        }


class SupplierForm(forms.ModelForm):
    class Meta:
        model = Supplier
        fields = [
            "date_supplied", "supplier_name", "item_name", "unit_price", "total_kgs",
        ]
        widgets = {
            "date_supplied": forms.DateInput(attrs={"type": "date"}),
            "unit_price": forms.NumberInput(attrs={"step": "0.01"}),
            "total_kgs": forms.NumberInput(attrs={"step": "0.001"}),
        }


class SupplierPaymentForm(forms.Form):
    date_paid = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    amount = forms.DecimalField(
        max_digits=10, decimal_places=2,
        widget=forms.NumberInput(attrs={"step": "0.01", "placeholder": "KES"}),
        min_value=Decimal("0.01"),
    )
    payment_mode = forms.ChoiceField(
        choices=[("", "— Select —"), (Supplier.CASH, "Cash"), (Supplier.MPESA, "Mpesa")]
    )
    remarks = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Optional"}),
    )
