import csv
import datetime
import math
from decimal import Decimal

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.db.models import Count, Min, Q, Sum
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
    SupplierPayment,
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
            amount = form.cleaned_data["amount"]
            date_paid = form.cleaned_data["date_paid"]
            mode = form.cleaned_data["payment_mode"]
            remarks = (form.cleaned_data.get("remarks") or "").strip()

            supplier.amount_paid = (supplier.amount_paid or Decimal("0")) + amount
            supplier.date_paid = date_paid
            supplier.payment_mode = mode
            if remarks:
                supplier.remarks = remarks
            supplier.save()

            SupplierPayment.objects.create(
                supplier=supplier,
                date=date_paid,
                amount=amount,
                payment_mode=mode,
                remarks=remarks,
                created_by=request.user,
            )
            messages.success(request, "Supplier payment recorded.")
            return redirect("admin_suppliers")
    else:
        form = SupplierPaymentForm(initial={"date_paid": timezone.localdate()})
    return render(request, "sales/admin/supplier_pay.html", {
        "form": form,
        "supplier": supplier,
    })


@staff_member_required
def admin_supplier_history(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    payments = supplier.payments.select_related("created_by").order_by("-date", "-id")
    total_paid = payments.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    return render(request, "sales/admin/supplier_history.html", {
        "supplier": supplier,
        "payments": payments,
        "total_paid": total_paid,
    })


@staff_member_required
def admin_supplier_history_download(request, pk):
    supplier = get_object_or_404(Supplier, pk=pk)
    payments = supplier.payments.select_related("created_by").order_by("date", "id")

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = (
        f'attachment; filename="supplier_payments_{supplier.supplier_name}.csv"'
    )

    writer = csv.writer(response)
    writer.writerow([
        "Supplier", "Item", "Date Supplied", "Total (KES)",
        "Date Paid", "Amount (KES)", "Mode", "Remarks", "Recorded By",
    ])
    for p in payments:
        writer.writerow([
            supplier.supplier_name,
            supplier.item_name,
            supplier.date_supplied.isoformat(),
            str(supplier.total),
            p.date.isoformat(),
            str(p.amount),
            p.get_payment_mode_display(),
            p.remarks,
            p.created_by.username if p.created_by else "",
        ])

    return response


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
    selected = request.GET.get("description", "").strip()

    qs = Expense.objects.select_related("created_by")
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)
    if payment:
        qs = qs.filter(payment_method=payment)
    if selected:
        qs = qs.filter(description__iexact=selected)

    qs = qs.order_by("-date", "-id")

    total = qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")

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

    context = {
        "expenses": qs[:500],
        "date_from": date_from,
        "date_to": date_to,
        "payment": payment,
        "selected": selected,
        "payment_choices": Expense.PAYMENT_CHOICES,
        "descriptions": descriptions,
        "grouped": grouped_sorted,
        "total": total,
    }
    return render(request, "sales/admin/expenses.html", context)


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


def _svg_bar_chart(labels, series, width=760, height=280):
    """Render a dependency-free grouped-bar SVG chart.

    `labels` is a list of x-axis strings and `series` is a list of
    ``(name, color, values)`` tuples whose value lists parallel `labels`.
    Handles negative values (bars drawn below the zero line).
    """
    labels = list(labels)
    series = list(series)
    n = len(labels)
    k = len(series)

    pad_l, pad_r, pad_t, pad_b = 64, 12, 14, 34
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b

    max_val = 0.0
    min_val = 0.0
    for _, _, vals in series:
        for v in vals:
            fv = float(v or 0)
            max_val = max(max_val, fv)
            min_val = min(min_val, fv)

    if max_val <= 0:
        max_val = 1.0
    nice = 10 ** math.floor(math.log10(max_val)) if max_val > 0 else 1.0
    ymax = math.ceil(max_val / nice) * nice

    ymin = 0.0
    if min_val < 0:
        nice_n = 10 ** math.floor(math.log10(abs(min_val))) if min_val != 0 else 1.0
        ymin = -math.ceil(abs(min_val) / nice_n) * nice_n

    span = ymax - ymin

    def y(v):
        return pad_t + (ymax - float(v or 0)) / span * plot_h

    def gx(i):
        return pad_l + (i + 0.5) * (plot_w / n if n else 0)

    parts = []
    ticks = 5
    for t in range(ticks + 1):
        val = ymax - (ymax - ymin) * t / ticks
        yy = pad_t + plot_h * t / ticks
        parts.append(
            f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{pad_l + plot_w}" y2="{yy:.1f}" '
            f'stroke="#eee" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pad_l - 6}" y="{yy + 4:.1f}" text-anchor="end" '
            f'font-size="10" fill="#999">{val:,.0f}</text>'
        )

    if n:
        step = max(1, n // 8)
        for i, lab in enumerate(labels):
            if i % step == 0 or i == n - 1:
                parts.append(
                    f'<text x="{gx(i):.1f}" y="{pad_t + plot_h + 16}" '
                    f'text-anchor="middle" font-size="10" fill="#999">{lab}</text>'
                )

    group_w = plot_w / n if n else plot_w
    bar_w = group_w * 0.7 / k
    y_base = y(0.0)
    for i in range(n):
        for j, (name, color, vals) in enumerate(series):
            fv = float(vals[i] or 0)
            y_val = y(fv)
            x0 = pad_l + i * group_w + group_w * 0.15 + j * bar_w
            top = min(y_val, y_base)
            bar_h = abs(y_val - y_base)
            if bar_h < 0.5:
                bar_h = 0.5
            parts.append(
                f'<rect x="{x0:.1f}" y="{top:.1f}" width="{bar_w:.1f}" '
                f'height="{bar_h:.1f}" fill="{color}"/>'
            )

    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="auto" '
        f'role="img" aria-label="bar chart">' + "".join(parts) + "</svg>"
    )


def _build_date_presets(date_from, date_to):
    """Quick-select pills shown above the from/to date pickers."""
    today = timezone.localdate()
    start_of_week = today - datetime.timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)
    last_month_end = start_of_month - datetime.timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    ranges = [
        ("Today", today, today),
        ("This week", start_of_week, today),
        ("This month", start_of_month, today),
        ("Last month", last_month_start, last_month_end),
        ("All time", None, None),
    ]
    presets = []
    for label, df, dt in ranges:
        df_str = df.isoformat() if df else ""
        dt_str = dt.isoformat() if dt else ""
        presets.append({
            "label": label,
            "url": f"?date_from={df_str}&date_to={dt_str}",
            "active": (date_from == df_str) and (date_to == dt_str),
        })
    return presets


def _build_debtor_aging():
    """Current outstanding balance per customer, independent of the report's
    date range. 'Oldest unpaid sale' is approximated as the customer's earliest
    credit sale still contributing to a positive balance."""
    today = timezone.localdate()

    owed_rows = (
        Sale.objects.filter(payment_method=Sale.CREDIT)
        .exclude(customer_name="")
        .values("customer_name")
        .annotate(total_owed=Sum("gross"))
    )

    oldest_dates = dict(
        Sale.objects.filter(payment_method=Sale.CREDIT)
        .exclude(customer_name="")
        .values("customer_name")
        .annotate(oldest=Min("date"))
        .values_list("customer_name", "oldest")
    )

    paid = dict(
        CreditPayment.objects.values("customer_name")
        .annotate(total_paid=Sum("amount"))
        .values_list("customer_name", "total_paid")
    )

    debtors = []
    for row in owed_rows:
        name = row["customer_name"]
        total_owed = row["total_owed"] or Decimal("0")
        total_paid = paid.get(name, Decimal("0"))
        balance = total_owed - total_paid
        if balance <= 0:
            continue

        oldest_date = oldest_dates.get(name)
        days_outstanding = (today - oldest_date).days if oldest_date else 0

        if days_outstanding <= 7:
            bucket_class, bucket_label = "fresh", "0-7 days"
        elif days_outstanding <= 30:
            bucket_class, bucket_label = "watch", "8-30 days"
        else:
            bucket_class, bucket_label = "overdue", "31+ days"

        debtors.append({
            "customer_name": name,
            "balance": balance,
            "oldest_sale_date": oldest_date,
            "days_outstanding": days_outstanding,
            "bucket_class": bucket_class,
            "bucket_label": bucket_label,
        })

    debtors.sort(key=lambda d: d["days_outstanding"], reverse=True)
    return debtors


def _build_expense_breakdown(date_from, date_to):
    """Expenses in the selected range grouped by exact description text."""
    qs = Expense.objects.all()
    if date_from:
        qs = qs.filter(date__gte=date_from)
    if date_to:
        qs = qs.filter(date__lte=date_to)

    return (
        qs.values("description")
        .annotate(total=Sum("amount"), count=Count("id"))
        .order_by("-total")
    )


def _build_cashier_breakdown(date_from, date_to):
    """Sales and expenses in the selected range grouped by created_by."""
    sales_qs = Sale.objects.all()
    exp_qs = Expense.objects.all()
    if date_from:
        sales_qs = sales_qs.filter(date__gte=date_from)
        exp_qs = exp_qs.filter(date__gte=date_from)
    if date_to:
        sales_qs = sales_qs.filter(date__lte=date_to)
        exp_qs = exp_qs.filter(date__lte=date_to)

    sales_by_user = {
        row["created_by__username"]: row
        for row in sales_qs.values("created_by__username")
        .annotate(sale_count=Count("id"), sale_total=Sum("gross"))
    }
    expenses_by_user = {
        row["created_by__username"]: row
        for row in exp_qs.values("created_by__username")
        .annotate(expense_count=Count("id"), expense_total=Sum("amount"))
    }

    usernames = set(sales_by_user) | set(expenses_by_user)
    usernames.discard(None)

    breakdown = []
    for username in usernames:
        s = sales_by_user.get(username, {})
        e = expenses_by_user.get(username, {})
        breakdown.append({
            "username": username,
            "sale_count": s.get("sale_count", 0),
            "sale_total": s.get("sale_total") or Decimal("0"),
            "expense_count": e.get("expense_count", 0),
            "expense_total": e.get("expense_total") or Decimal("0"),
        })
    breakdown.sort(key=lambda b: b["sale_total"], reverse=True)
    return breakdown


@staff_member_required
def admin_reports(request):
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    sales_qs = Sale.objects.select_related("item").all()
    expenses_qs = Expense.objects.all()
    services_qs = OtherService.objects.all()
    stock_qs = Stock.objects.all()

    if date_from:
        sales_qs = sales_qs.filter(date__gte=date_from)
        expenses_qs = expenses_qs.filter(date__gte=date_from)
        services_qs = services_qs.filter(date__gte=date_from)
        stock_qs = stock_qs.filter(date__gte=date_from)
    if date_to:
        sales_qs = sales_qs.filter(date__lte=date_to)
        expenses_qs = expenses_qs.filter(date__lte=date_to)
        services_qs = services_qs.filter(date__lte=date_to)
        stock_qs = stock_qs.filter(date__lte=date_to)

    totals = sales_qs.aggregate(
        total=Sum("gross"),
        cash=Sum("gross", filter=Q(payment_method=Sale.CASH)),
        mpesa=Sum("gross", filter=Q(payment_method=Sale.MPESA)),
        credit=Sum("gross", filter=Q(payment_method=Sale.CREDIT)),
    )

    counts = sales_qs.aggregate(
        cash_count=Count("id", filter=Q(payment_method=Sale.CASH)),
        mpesa_count=Count("id", filter=Q(payment_method=Sale.MPESA)),
        credit_count=Count("id", filter=Q(payment_method=Sale.CREDIT)),
    )

    expenses_total = expenses_qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    services_total = services_qs.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    net = (totals["cash"] or Decimal("0")) + (services_total or Decimal("0")) - expenses_total

    by_item = (
        sales_qs.values("item__name")
        .annotate(total_kg=Sum("weight_kg"), total_gross=Sum("gross"))
        .order_by("-total_gross")
    )

    # --- Payment method analysis ---
    total_sales = totals["total"] or Decimal("0")

    def pct(value):
        if not total_sales:
            return "0.0%"
        return f"{(Decimal(value or 0) / total_sales * 100):.1f}%"

    payment_analysis = [
        {
            "key": "CASH",
            "label": "Cash",
            "total": totals["cash"] or Decimal("0"),
            "count": counts["cash_count"] or 0,
            "pct": pct(totals["cash"]),
            "color": "#18794e",
            "badge": "CASH",
        },
        {
            "key": "MPESA",
            "label": "Mpesa",
            "total": totals["mpesa"] or Decimal("0"),
            "count": counts["mpesa_count"] or 0,
            "pct": pct(totals["mpesa"]),
            "color": "#b54708",
            "badge": "MPESA",
        },
        {
            "key": "CREDIT",
            "label": "Credit",
            "total": totals["credit"] or Decimal("0"),
            "count": counts["credit_count"] or 0,
            "pct": pct(totals["credit"]),
            "color": "#eab308",
            "badge": "CREDIT",
        },
    ]

    # --- Payment trend line chart (daily cash / mpesa / credit) ---
    daily = (
        sales_qs.values("date")
        .annotate(
            cash=Sum("gross", filter=Q(payment_method=Sale.CASH)),
            mpesa=Sum("gross", filter=Q(payment_method=Sale.MPESA)),
            credit=Sum("gross", filter=Q(payment_method=Sale.CREDIT)),
        )
        .order_by("date")
    )
    payment_labels = [row["date"].strftime("%d/%m") for row in daily]
    payment_chart = _svg_bar_chart(
        payment_labels,
        [
            ("Cash", "#18794e", [float(row["cash"] or 0) for row in daily]),
            ("Mpesa", "#b54708", [float(row["mpesa"] or 0) for row in daily]),
            ("Credit", "#eab308", [float(row["credit"] or 0) for row in daily]),
        ],
    )

    # --- Stock analysis line chart (opening / sold / remaining kg) ---
    opening_by_date = {
        row["date"]: row["t"]
        for row in stock_qs.values("date").annotate(t=Sum("opening_kg")).order_by("date")
    }
    sold_by_date = {
        row["date"]: row["t"]
        for row in sales_qs.values("date").annotate(t=Sum("weight_kg")).order_by("date")
    }
    stock_dates = sorted(set(opening_by_date) | set(sold_by_date))
    opening_vals = [float(opening_by_date.get(d) or 0) for d in stock_dates]
    sold_vals = [float(sold_by_date.get(d) or 0) for d in stock_dates]
    remaining_vals = [o - s for o, s in zip(opening_vals, sold_vals)]
    stock_chart = _svg_bar_chart(
        [d.strftime("%d/%m") for d in stock_dates],
        [
            ("Opening", "#b42318", opening_vals),
            ("Sold", "#eab308", sold_vals),
            ("Remaining", "#b54708", remaining_vals),
        ],
    )

    context = {
        "date_from": date_from,
        "date_to": date_to,
        "summary": {k: v or Decimal("0") for k, v in totals.items()},
        "expenses_total": expenses_total,
        "services_total": services_total,
        "net": net,
        "by_item": by_item,
        "payment_analysis": payment_analysis,
        "payment_chart": payment_chart,
        "stock_chart": stock_chart,
        "has_stock_data": bool(stock_dates),
        "query_string": request.META.get("QUERY_STRING", ""),
        "date_presets": _build_date_presets(date_from, date_to),
        "debtors": _build_debtor_aging(),
        "expense_breakdown": _build_expense_breakdown(date_from, date_to),
        "cashier_breakdown": _build_cashier_breakdown(date_from, date_to),
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
