import csv
import datetime
from decimal import Decimal

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import ItemForm, SupplierForm, SupplierPaymentForm
from .models import (
    CreditPayment,
    Expense,
    Item,
    OtherService,
    Sale,
    Stock,
    Supplier,
    normalize_customer_name,
    normalize_expense_name,
)


@staff_member_required
def admin_items(request):
    if request.method == "POST":
        item_id = request.POST.get("item_id")
        if item_id:
            item = get_object_or_404(Item, pk=item_id)
            if "delete" in request.POST:
                item.delete()
                messages.success(request, "Item deleted.")
            else:
                form = ItemForm(request.POST, instance=item)
                if form.is_valid():
                    form.save()
                    messages.success(request, "Item updated.")
            return redirect("admin_items")
        else:
            form = ItemForm(request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, "Item added.")
            return redirect("admin_items")

    items = Item.objects.order_by("active", "name")
    form = ItemForm()
    context = {"items": items, "form": form}
    return render(request, "sales/admin/items.html", context)


@staff_member_required
def admin_suppliers(request):
    if request.method == "POST":
        if "delete_supplier" in request.POST:
            supplier = get_object_or_404(Supplier, pk=request.POST.get("supplier_id"))
            supplier.delete()
            messages.success(request, "Supplier deleted.")
            return redirect("admin_suppliers")
        form = SupplierForm(request.POST)
        if form.is_valid():
            supplier = form.save(commit=False)
            supplier.created_by = request.user
            supplier.save()
            messages.success(request, "Supplier added.")
            return redirect("admin_suppliers")

    suppliers = Supplier.objects.all().order_by("-date_supplied", "-id")
    total_value = sum((s.total for s in suppliers), Decimal("0"))
    total_paid = suppliers.aggregate(t=Sum("amount_paid"))["t"] or Decimal("0")

    context = {
        "suppliers": suppliers,
        "form": SupplierForm(),
        "total_value": total_value,
        "total_paid": total_paid,
        "total_balance": total_value - total_paid,
    }
    return render(request, "sales/admin/suppliers.html", context)


@staff_member_required
def admin_supplier_edit(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == "POST":
        form = SupplierForm(request.POST, instance=supplier)
        if form.is_valid():
            form.save()
            messages.success(request, "Supplier updated.")
            return redirect("admin_suppliers")
    else:
        form = SupplierForm(instance=supplier)
    return render(request, "sales/edit_entry.html", {
        "form": form,
        "title": f"Edit Supplier — {supplier.supplier_name}",
        "cancel_url": "/manage/suppliers/",
    })


@staff_member_required
def admin_supplier_pay(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    if request.method == "POST":
        form = SupplierPaymentForm(request.POST)
        if form.is_valid():
            supplier.amount_paid = (supplier.amount_paid or Decimal("0")) + form.cleaned_data["amount"]
            supplier.date_paid = form.cleaned_data["date_paid"]
            supplier.payment_mode = form.cleaned_data["payment_mode"]
            remarks = (form.cleaned_data.get("remarks") or "").strip()
            if remarks:
                supplier.remarks = remarks
            supplier.save()
            messages.success(request, "Supplier payment recorded.")
            return redirect("admin_suppliers")
    else:
        form = SupplierPaymentForm(initial={"date_paid": timezone.localdate()})
    return render(request, "sales/admin/supplier_pay.html", {
        "form": form,
        "supplier": supplier,
    })


@staff_member_required
def admin_sales(request):
    if request.method == "POST" and "delete_sale" in request.POST:
        sale = get_object_or_404(Sale, pk=request.POST.get("sale_id"))
        sale.delete()
        messages.success(request, "Sale deleted.")
        return redirect("admin_sales")

    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    payment = request.GET.get("payment", "")

    qs = Sale.objects.select_related("item", "created_by")

    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if payment:
        qs = qs.filter(payment_method=payment)

    qs = qs.order_by("-date", "-id")

    totals = qs.aggregate(
        total=Sum("gross"),
        cash=Sum("gross", filter=Q(payment_method="CASH")),
        mpesa=Sum("gross", filter=Q(payment_method="MPESA")),
        credit=Sum("gross", filter=Q(payment_method="CREDIT")),
    )

    context = {
        "sales": qs[:200],
        "date_from": date_from,
        "date_to": date_to,
        "payment": payment,
        "payment_choices": [(c, l) for c, l in Sale.PAYMENT_CHOICES if c],
        "summary": {k: v or Decimal("0") for k, v in totals.items()},
    }
    return render(request, "sales/admin/sales.html", context)


@staff_member_required
def admin_expenses(request):
    if request.method == "POST" and "delete_expense" in request.POST:
        expense = get_object_or_404(Expense, pk=request.POST.get("expense_id"))
        expense.delete()
        messages.success(request, "Expense deleted.")
        return redirect("admin_expenses")

    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    payment = request.GET.get("payment", "")

    qs = Expense.objects.select_related("created_by")
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if payment:
        qs = qs.filter(payment_method=payment)

    qs = qs.order_by("-date", "-id")
    total = qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")

    context = {
        "expenses": qs[:200],
        "date_from": date_from,
        "date_to": date_to,
        "payment": payment,
        "payment_choices": Expense.PAYMENT_CHOICES,
        "total": total,
    }
    return render(request, "sales/admin/expenses.html", context)


@staff_member_required
def admin_payments(request):
    if request.method == "POST" and "delete_payment" in request.POST:
        payment = get_object_or_404(CreditPayment, pk=request.POST.get("payment_id"))
        payment.delete()
        messages.success(request, "Payment deleted.")
        return redirect("admin_payments")

    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    q = request.GET.get("q", "").strip()

    qs = CreditPayment.objects.select_related("sale", "created_by")
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if q:
        qs = qs.filter(customer_name__icontains=q)

    qs = qs.order_by("-date", "-id")
    total = qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")

    grouped = {}
    for p in qs:
        name = normalize_customer_name(p.customer_name)
        grouped.setdefault(name, {"payments": [], "total": Decimal("0")})
        grouped[name]["payments"].append(p)
        grouped[name]["total"] += p.amount
    grouped_sorted = sorted(grouped.items(), key=lambda kv: kv[1]["total"], reverse=True)

    customer_names = sorted({
        normalize_customer_name(n)
        for n in CreditPayment.objects.values_list("customer_name", flat=True)
    })

    context = {
        "grouped": grouped_sorted,
        "date_from": date_from,
        "date_to": date_to,
        "q": q,
        "total": total,
        "customer_names": customer_names,
    }
    return render(request, "sales/admin/payments.html", context)


@staff_member_required
def admin_users(request):
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")
        if "delete_user" in request.POST:
            uid = request.POST.get("user_id")
            user = get_object_or_404(User, pk=uid)
            if not user.is_superuser:
                user.delete()
                messages.success(request, "User deleted.")
            return redirect("admin_users")
        elif username and password:
            if not User.objects.filter(username=username).exists():
                User.objects.create_user(username=username, password=password, is_staff=False, is_superuser=False)
                messages.success(request, f"User '{username}' created.")
            return redirect("admin_users")

    cashiers = User.objects.filter(is_superuser=False, is_staff=False).order_by("username")
    owners = User.objects.filter(is_superuser=True).order_by("username")
    context = {"cashiers": cashiers, "owners": owners}
    return render(request, "sales/admin/users.html", context)


@staff_member_required
def admin_stock(request):
    if request.method == "POST":
        date_str = request.POST.get("date", "")
        if date_str:
            try:
                date = datetime.date.fromisoformat(date_str)
            except ValueError:
                date = timezone.localdate()
            if "clear_stock" in request.POST:
                Stock.objects.filter(date=date).update(opening_kg=Decimal("0"))
                messages.success(request, "Opening stock cleared.")
            else:
                for key, value in request.POST.items():
                    if key.startswith("opening_"):
                        stock_id = key.replace("opening_", "")
                        stock = get_object_or_404(Stock, pk=stock_id)
                        if value:
                            stock.opening_kg = Decimal(value)
                            stock.save()
                messages.success(request, "Stock updated.")
            return redirect(f"/manage/stock/?date={date.isoformat()}")
        return redirect("admin_stock")

    date_str = request.GET.get("date", "")
    if date_str:
        try:
            date = datetime.date.fromisoformat(date_str)
        except ValueError:
            date = timezone.localdate()
    else:
        date = timezone.localdate()

    items = Item.objects.filter(active=True)
    existing = {s.item_id: s for s in Stock.objects.filter(date=date)}

    for item in items:
        if item.pk not in existing:
            prev = (
                Stock.objects.filter(item=item, date__lt=date)
                .order_by("-date")
                .first()
            )
            opening = prev.remaining_kg if prev else Decimal("0")
            existing[item.pk] = Stock.objects.create(
                item=item, date=date, opening_kg=opening
            )

    stock_rows = sorted(existing.values(), key=lambda s: s.item.name)

    has_negatives = any(s.remaining_kg < 0 for s in stock_rows)

    context = {
        "date": date,
        "today": timezone.localdate(),
        "stock_rows": stock_rows,
        "has_negatives": has_negatives,
    }
    return render(request, "sales/admin/stock.html", context)


@staff_member_required
def admin_expense_summary(request):
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")
    selected = request.GET.get("description", "").strip()

    qs = Expense.objects.select_related("created_by")
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    qs = qs.order_by("-date", "-id")

    descriptions = sorted({
        normalize_expense_name(d)
        for d in Expense.objects.values_list("description", flat=True)
    })

    grouped = {}
    for e in qs:
        key = normalize_expense_name(e.description) or "(blank)"
        grouped.setdefault(key, {"total": Decimal("0"), "count": 0})
        grouped[key]["total"] += e.amount
        grouped[key]["count"] += 1
    grouped_sorted = sorted(grouped.items(), key=lambda kv: kv[1]["total"], reverse=True)

    selected_rows = []
    selected_total = Decimal("0")
    if selected:
        selected_rows = [
            e for e in qs
            if normalize_expense_name(e.description).lower() == selected.lower()
        ]
        selected_total = sum((e.amount for e in selected_rows), Decimal("0"))

    total = qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")

    context = {
        "date_from": date_from,
        "date_to": date_to,
        "selected": selected,
        "descriptions": descriptions,
        "grouped": grouped_sorted,
        "selected_rows": selected_rows,
        "selected_total": selected_total,
        "total": total,
    }
    return render(request, "sales/admin/expense_summary.html", context)


@staff_member_required
def admin_reports(request):
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    sales_qs = Sale.objects.select_related("item").all()
    expenses_qs = Expense.objects.all()
    services_qs = OtherService.objects.all()

    if date_from:
        sales_qs = sales_qs.filter(date__gte=date_from)
        expenses_qs = expenses_qs.filter(date__gte=date_from)
        services_qs = services_qs.filter(date__gte=date_from)
    if date_to:
        sales_qs = sales_qs.filter(date__lte=date_to)
        expenses_qs = expenses_qs.filter(date__lte=date_to)
        services_qs = services_qs.filter(date__lte=date_to)

    totals = sales_qs.aggregate(
        total=Sum("gross"),
        cash=Sum("gross", filter=Q(payment_method=Sale.CASH)),
        mpesa=Sum("gross", filter=Q(payment_method=Sale.MPESA)),
        credit=Sum("gross", filter=Q(payment_method=Sale.CREDIT)),
    )

    expenses_total = expenses_qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    services_total = services_qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    net = (totals["cash"] or Decimal("0")) + (services_total or Decimal("0")) - expenses_total

    by_item = (
        sales_qs.values("item__name")
        .annotate(total_kg=Sum("weight_kg"), total_gross=Sum("gross"))
        .order_by("-total_gross")
    )

    context = {
        "date_from": date_from,
        "date_to": date_to,
        "summary": {k: v or Decimal("0") for k, v in totals.items()},
        "expenses_total": expenses_total,
        "services_total": services_total,
        "net": net,
        "by_item": by_item,
        "query_string": request.META.get("QUERY_STRING", ""),
    }
    return render(request, "sales/admin/reports.html", context)


@staff_member_required
def admin_reports_export(request):
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    sales_qs = Sale.objects.select_related("item", "created_by")
    if date_from:
        sales_qs = sales_qs.filter(date__gte=date_from)
    if date_to:
        sales_qs = sales_qs.filter(date__lte=date_to)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="meatmagic_report.csv"'

    writer = csv.writer(response)
    writer.writerow(["Date", "Item", "Weight (kg)", "Gross (KES)", "Payment", "Customer", "Cashier"])
    for sale in sales_qs.order_by("date", "id"):
        writer.writerow([
            sale.date.isoformat(),
            sale.item.name,
            str(sale.weight_kg),
            str(sale.gross),
            sale.get_payment_method_display(),
            sale.customer_name,
            sale.created_by.username if sale.created_by else "",
        ])

    return response
