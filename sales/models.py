from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db import models, transaction
from django.db.models import Max
from django.utils import timezone


def normalize_expense_name(value):
    return " ".join((value or "").split()).title()


def normalize_customer_name(value):
    return " ".join((value or "").split()).title()


class Creditor(models.Model):
    """A customer who buys on credit, with optional extra contact notes."""

    name = models.CharField(max_length=100, unique=True)
    notes = models.TextField(blank=True, help_text="Extra info: phone, address, terms, etc.")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Item(models.Model):
    """One row of the price list (was columns P:Q in the spreadsheet)."""

    name = models.CharField(max_length=50, unique=True)
    price_per_kg = models.DecimalField(max_digits=10, decimal_places=2)
    active = models.BooleanField(
        default=True,
        help_text="Untick to hide from the sale entry dropdown without deleting history.",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} (KES {self.price_per_kg}/kg)"


class Stock(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="stock")
    date = models.DateField(db_index=True)
    opening_kg = models.DecimalField(max_digits=10, decimal_places=3, default=0)

    class Meta:
        unique_together = [("item", "date")]
        ordering = ["date", "item__name"]

    def __str__(self):
        return f"{self.item.name} — {self.date} opening {self.opening_kg} kg"

    @property
    def sold_kg(self):
        from django.db.models import Sum
        return (
            Sale.objects.filter(item=self.item, date=self.date).aggregate(
                t=Sum("weight_kg")
            )["t"]
            or Decimal("0")
        )

    @property
    def remaining_kg(self):
        return self.opening_kg - self.sold_kg


class Sale(models.Model):
    """One line of a day's sales log. Mirrors the WEIGHT / PAID(if unknown) / GROSS
    dance from the spreadsheet, except here it's just two optional fields and the
    model works out whichever one is missing - no circular formulas needed."""

    NONE = ""
    CASH, MPESA, CREDIT = "CASH", "MPESA", "CREDIT"
    PAYMENT_CHOICES = [(NONE, "— Select —"), (CASH, "Cash"), (MPESA, "Mpesa"), (CREDIT, "Credit")]

    date = models.DateField(default=timezone.localdate, db_index=True)
    sequence = models.PositiveIntegerField(
        default=0, editable=False,
        help_text="Per-day order number, e.g. 1, 2, 3 ...",
    )
    item = models.ForeignKey(Item, on_delete=models.PROTECT, related_name="sales")
    weight_kg = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    gross = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, blank=False, default=NONE)
    customer_name = models.CharField(
        max_length=100, blank=True,
        help_text="Required when payment method is Credit.",
    )
    customer_ctp = models.CharField(
        max_length=50, blank=True,
        help_text="Batch reference for this credit sale — same CTP for goods taken on the same day.",
    )
    creditor = models.ForeignKey(
        Creditor, on_delete=models.PROTECT, null=True, blank=True,
        related_name="sales",
    )
    remarks = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]

    def clean(self):
        errors = {}
        if self.payment_method == self.NONE:
            errors["payment_method"] = "Please select a mode of payment."
        if not self.weight_kg and not self.gross:
            errors[NON_FIELD_ERRORS] = "Enter either the weight (kg) or the amount paid (KES) to continue."
        if self.payment_method == self.CREDIT and not self.customer_name:
            errors["customer_name"] = "Customer name is required for credit sales."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.customer_name:
            self.customer_name = normalize_customer_name(self.customer_name)
            self.creditor = Creditor.objects.get_or_create(name=self.customer_name)[0]
        if self.customer_ctp:
            self.customer_ctp = self.customer_ctp.strip()
        if self._state.adding and not self.sequence:
            last = (
                Sale.objects.filter(date=self.date)
                .aggregate(m=Max("sequence"))["m"] or 0
            )
            self.sequence = last + 1
        price = self.item.price_per_kg
        cents = Decimal("0.01")
        if self.weight_kg and not self.gross:
            self.gross = (self.weight_kg * price).quantize(cents, rounding=ROUND_HALF_UP)
        elif self.gross and not self.weight_kg:
            self.weight_kg = (self.gross / price).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.reference} - {self.date} - {self.item.name} - KES {self.gross}"

    @property
    def reference(self):
        return f"{self.date.strftime('%d/%m')} #{self.sequence:02d}"

    @property
    def total_paid(self):
        from django.db.models import Sum
        return (
            self.credit_payments.aggregate(t=Sum("amount"))["t"]
            or Decimal("0")
        )

    @property
    def balance(self):
        return self.gross - self.total_paid

    @property
    def is_fully_paid(self):
        return self.balance <= Decimal("0")


class Expense(models.Model):
    """Same idea as the DAILY EXPENSES block on the sheet."""

    NONE = ""
    CASH, MPESA = "CASH", "MPESA"
    PAYMENT_CHOICES = [(NONE, "— Select —"), (CASH, "Cash"), (MPESA, "Mpesa")]

    date = models.DateField(default=timezone.localdate, db_index=True)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, blank=False, default=NONE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]

    def clean(self):
        errors = {}
        if self.payment_method == self.NONE:
            errors["payment_method"] = "Please select a mode of payment."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.description = normalize_expense_name(self.description)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} - {self.description} - KES {self.amount}"


class OtherService(models.Model):
    NONE = ""
    CASH, MPESA = "CASH", "MPESA"
    PAYMENT_CHOICES = [(NONE, "— Select —"), (CASH, "Cash"), (MPESA, "Mpesa")]

    date = models.DateField(default=timezone.localdate, db_index=True)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_CHOICES, blank=False, default=NONE)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]

    def clean(self):
        errors = {}
        if self.payment_method == self.NONE:
            errors["payment_method"] = "Please select a mode of payment."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.date} - {self.description} - KES {self.amount}"


class CreditPayment(models.Model):
    NONE = ""
    CASH, MPESA = "CASH", "MPESA"
    PAYMENT_MODE_CHOICES = [(NONE, "— Select —"), (CASH, "Cash"), (MPESA, "M-Pesa")]

    date = models.DateField(default=timezone.localdate, db_index=True)
    customer_name = models.CharField(max_length=100, db_index=True)
    customer_ctp = models.CharField(
        max_length=50, blank=True,
        help_text="Batch reference copied from the linked credit sale.",
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODE_CHOICES, blank=False, default=NONE)
    note = models.CharField(max_length=255, blank=True)
    sale = models.ForeignKey(
        Sale, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="credit_payments",
        help_text="Link this payment to a specific credit sale.",
    )
    creditor = models.ForeignKey(
        Creditor, on_delete=models.PROTECT, null=True, blank=True,
        related_name="payments",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["date", "id"]

    def clean(self):
        errors = {}
        if self.payment_mode == self.NONE:
            errors["payment_mode"] = "Please select a mode of payment (Cash or Mpesa)."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.sale and not self.customer_name:
            self.customer_name = self.sale.customer_name
        if self.sale and not self.customer_ctp:
            self.customer_ctp = self.sale.customer_ctp
        if self.customer_name:
            self.customer_name = normalize_customer_name(self.customer_name)
            self.creditor = Creditor.objects.get_or_create(name=self.customer_name)[0]
        if self.customer_ctp:
            self.customer_ctp = self.customer_ctp.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        if self.sale:
            return f"{self.date} - {self.customer_name} paid KES {self.amount} (sale {self.sale.reference})"
        return f"{self.date} - {self.customer_name} paid KES {self.amount}"


class Supplier(models.Model):
    """One goods delivery / purchase from a supplier, with its payment status."""

    NONE = ""
    CASH, MPESA = "CASH", "MPESA"
    PAYMENT_CHOICES = [(NONE, "— Select —"), (CASH, "Cash"), (MPESA, "Mpesa")]

    date_supplied = models.DateField(default=timezone.localdate, db_index=True)
    supplier_name = models.CharField(max_length=100)
    item_name = models.CharField(max_length=100, help_text="Name of the goods being supplied.")
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_kgs = models.DecimalField(max_digits=10, decimal_places=3)
    date_paid = models.DateField(null=True, blank=True)
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_CHOICES, blank=True, default=NONE)
    remarks = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date_supplied", "-id"]

    def clean(self):
        errors = {}
        if (self.amount_paid or Decimal("0")) > 0 and self.payment_mode == self.NONE:
            errors["payment_mode"] = "Please select a mode of payment (Cash or Mpesa)."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.supplier_name:
            self.supplier_name = normalize_customer_name(self.supplier_name)
        if self.item_name:
            self.item_name = normalize_customer_name(self.item_name)
        if self.amount_paid is None:
            self.amount_paid = Decimal("0")
        super().save(*args, **kwargs)

    @property
    def total(self):
        return (self.unit_price * self.total_kgs).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

    @property
    def balance(self):
        return self.total - self.amount_paid

    def __str__(self):
        return f"{self.date_supplied} - {self.supplier_name} - KES {self.total}"


class SupplierPayment(models.Model):
    """A single payment made against a supplier delivery."""

    NONE = ""
    CASH, MPESA = "CASH", "MPESA"
    PAYMENT_MODE_CHOICES = [(NONE, "— Select —"), (CASH, "Cash"), (MPESA, "M-Pesa")]

    supplier = models.ForeignKey(
        Supplier, on_delete=models.CASCADE, related_name="payments"
    )
    date = models.DateField(default=timezone.localdate, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_mode = models.CharField(max_length=10, choices=PAYMENT_MODE_CHOICES, blank=False, default=NONE)
    remarks = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def clean(self):
        errors = {}
        if self.payment_mode == self.NONE:
            errors["payment_mode"] = "Please select a mode of payment (Cash or Mpesa)."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"{self.date} - {self.supplier.supplier_name} paid KES {self.amount}"


class InvoiceCounter(models.Model):
    """Single-row counter used to hand out sequential invoice numbers."""

    key = models.CharField(max_length=32, primary_key=True)
    value = models.PositiveIntegerField(default=0)


def next_invoice_number():
    with transaction.atomic():
        try:
            counter = InvoiceCounter.objects.select_for_update().get(key="invoice")
        except InvoiceCounter.DoesNotExist:
            counter = InvoiceCounter(key="invoice", value=0)
        counter.value += 1
        counter.save()
        return counter.value


class Invoice(models.Model):
    """A customer invoice for one or more credit sales, kept so the number is stable."""

    number = models.CharField(max_length=32, unique=True)
    customer_name = models.CharField(max_length=100, db_index=True)
    date = models.DateField(default=timezone.localdate, db_index=True)
    sales = models.ManyToManyField(Sale, related_name="invoices")
    signature = models.CharField(
        max_length=500, blank=True,
        help_text="Internal dedupe key (sorted sale ids) so the same sales reuse one number.",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.number} - {self.customer_name}"
