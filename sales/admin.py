from decimal import Decimal

from django.contrib import admin
from django.db.models import Q, Sum
from django.urls import reverse
from django.utils.html import format_html

from .models import CreditPayment, Expense, Invoice, Item, OtherService, Sale, Supplier


admin.site.site_header = "Meat Magic Enterprises LTD"
admin.site.site_title = "Meat Magic Enterprises LTD"
admin.site.index_title = "Management"


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("name", "price_per_kg", "active")
    list_editable = ("price_per_kg", "active")
    list_filter = ("active",)
    search_fields = ("name",)
    list_per_page = 25


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("reference", "date", "item", "weight_kg_display", "gross_display", "payment_badge", "customer_name", "created_by", "edit_link")
    list_filter = ("date", "payment_method", "item")
    search_fields = ("customer_name", "remarks")
    date_hierarchy = "date"
    list_per_page = 50
    list_select_related = ("item", "created_by")
    save_on_top = True

    def reference(self, obj):
        return obj.reference
    reference.short_description = "No."
    reference.admin_order_field = "sequence"

    def weight_kg_display(self, obj):
        if obj.weight_kg is not None:
            return f"{obj.weight_kg:.3f} kg"
        return "-"
    weight_kg_display.short_description = "Weight"
    weight_kg_display.admin_order_field = "weight_kg"

    def gross_display(self, obj):
        if obj.gross is not None:
            return f"KES {obj.gross:,.2f}"
        return "-"
    gross_display.short_description = "Gross"
    gross_display.admin_order_field = "gross"

    def payment_badge(self, obj):
        colors = {"CASH": "#146c2e", "MPESA": "#96590a", "CREDIT": "#a12727"}
        bg = {"CASH": "#d9f2e3", "MPESA": "#fdecd2", "CREDIT": "#fbdede"}
        c = colors.get(obj.payment_method, "#333")
        b = bg.get(obj.payment_method, "#eee")
        return format_html(
            '<span style="background:{}; color:{}; padding:3px 10px; border-radius:12px; font-weight:600; font-size:0.85em;">{}</span>',
            b, c, obj.get_payment_method_display(),
        )
    payment_badge.short_description = "Payment"

    def edit_link(self, obj):
        url = reverse("admin:sales_sale_change", args=[obj.pk])
        return format_html('<a href="{}">Edit</a>', url)
    edit_link.short_description = ""

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        qs = self.get_queryset(request)
        totals = qs.aggregate(total=Sum("gross"), cash=Sum("gross", filter=Q(payment_method="CASH")), mpesa=Sum("gross", filter=Q(payment_method="MPESA")), credit=Sum("gross", filter=Q(payment_method="CREDIT")))
        extra_context["summary"] = {k: v or Decimal("0") for k, v in totals.items()}
        return super().changelist_view(request, extra_context)


@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ("date", "description", "amount_display", "payment_method", "created_by", "edit_link")
    list_filter = ("date", "payment_method")
    search_fields = ("description",)
    date_hierarchy = "date"
    list_per_page = 50
    list_select_related = ("created_by",)
    save_on_top = True

    def amount_display(self, obj):
        return f"KES {obj.amount:,.2f}"
    amount_display.short_description = "Amount"
    amount_display.admin_order_field = "amount"

    def edit_link(self, obj):
        url = reverse("admin:sales_expense_change", args=[obj.pk])
        return format_html('<a href="{}">Edit</a>', url)
    edit_link.short_description = ""

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        qs = self.get_queryset(request)
        total = qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")
        extra_context["total_expenses"] = total
        return super().changelist_view(request, extra_context)


@admin.register(OtherService)
class OtherServiceAdmin(admin.ModelAdmin):
    list_display = ("date", "description", "amount_display", "payment_method_display", "created_by", "edit_link")
    list_filter = ("date", "payment_method")
    search_fields = ("description",)
    date_hierarchy = "date"
    list_per_page = 50
    list_select_related = ("created_by",)
    save_on_top = True

    def amount_display(self, obj):
        return f"KES {obj.amount:,.2f}"
    amount_display.short_description = "Amount"
    amount_display.admin_order_field = "amount"

    def payment_method_display(self, obj):
        colors = {"CASH": "#146c2e", "MPESA": "#96590a"}
        bg = {"CASH": "#d9f2e3", "MPESA": "#fdecd2"}
        c = colors.get(obj.payment_method, "#333")
        b = bg.get(obj.payment_method, "#eee")
        return format_html(
            '<span style="background:{}; color:{}; padding:3px 10px; border-radius:12px; font-weight:600; font-size:0.85em;">{}</span>',
            b, c, obj.get_payment_method_display(),
        )
    payment_method_display.short_description = "Payment"

    def edit_link(self, obj):
        url = reverse("admin:sales_otherservice_change", args=[obj.pk])
        return format_html('<a href="{}">Edit</a>', url)
    edit_link.short_description = ""

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        qs = self.get_queryset(request)
        total = qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")
        extra_context["total_services"] = total
        return super().changelist_view(request, extra_context)




@admin.register(CreditPayment)
class CreditPaymentAdmin(admin.ModelAdmin):
    list_display = ("date", "customer_name", "amount_display", "payment_mode_display", "note", "created_by", "edit_link")
    list_filter = ("date", "payment_mode")
    search_fields = ("customer_name", "note")
    date_hierarchy = "date"
    list_per_page = 50
    list_select_related = ("created_by",)
    save_on_top = True

    def amount_display(self, obj):
        return f"KES {obj.amount:,.2f}"
    amount_display.short_description = "Amount"
    amount_display.admin_order_field = "amount"

    def payment_mode_display(self, obj):
        colors = {"CASH": "#146c2e", "MPESA": "#96590a"}
        bg = {"CASH": "#d9f2e3", "MPESA": "#fdecd2"}
        c = colors.get(obj.payment_mode, "#333")
        b = bg.get(obj.payment_mode, "#eee")
        return format_html(
            '<span style="background:{}; color:{}; padding:3px 10px; border-radius:12px; font-weight:600; font-size:0.85em;">{}</span>',
            b, c, obj.get_payment_mode_display(),
        )
    payment_mode_display.short_description = "Mode"

    def edit_link(self, obj):
        url = reverse("admin:sales_creditpayment_change", args=[obj.pk])
        return format_html('<a href="{}">Edit</a>', url)
    edit_link.short_description = ""

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        qs = self.get_queryset(request)
        total = qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")
        extra_context["total_payments"] = total
        return super().changelist_view(request, extra_context)


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ("date_supplied", "supplier_name", "unit_price", "total_kgs", "total", "date_paid", "amount_paid", "balance", "payment_mode", "remarks", "created_by")
    list_filter = ("date_supplied", "payment_mode")
    search_fields = ("supplier_name", "remarks")
    date_hierarchy = "date_supplied"
    list_per_page = 50
    list_select_related = ("created_by",)
    save_on_top = True


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ("number", "customer_name", "date", "created_by")
    list_filter = ("date",)
    search_fields = ("number", "customer_name")
    date_hierarchy = "date"
    list_per_page = 50
    list_select_related = ("created_by",)
    filter_horizontal = ("sales",)
