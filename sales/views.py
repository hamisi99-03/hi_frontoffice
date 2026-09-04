import datetime
import uuid
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import NON_FIELD_ERRORS, ValidationError
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import CreditPaymentForm, ExpenseForm, OtherServiceForm, SaleForm
from .models import (
    CreditPayment,
    Creditor,
    Expense,
    Invoice,
    Item,
    OtherService,
    Sale,
    Stock,
    next_invoice_number,
    normalize_customer_name,
    normalize_expense_name,
)
from .pdf import build_invoice_pdf


SALE_KIND_LABELS = {
    Sale.CASH: "CASH SALE",
    Sale.MPESA: "MPESA SALE",
    Sale.CREDIT: "CREDIT SALE",
}


def _sale_kind_label(payment_method):
    return SALE_KIND_LABELS.get(payment_method, "SALE")


def _receipt_context(sales, doc_type, customer="", receipt_no="", hide_costs=False):
    total = sum((s.gross or Decimal("0") for s in sales), Decimal("0"))
    methods = {s.payment_method for s in sales}
    if len(methods) == 1:
        doc_type = _sale_kind_label(next(iter(methods)))
    return {
        "sales": sales,
        "doc_type": doc_type,
        "customer": customer,
        "receipt_no": receipt_no,
        "date": sales[0].date if sales else timezone.localdate(),
        "total": total,
        "methods": methods,
        "total_paid": None,
        "balance": None,
        "show_balance": False,
        "hide_costs": hide_costs,
    }


def _want_hide_costs(request):
    return request.GET.get("hide_costs", "").strip().lower() in ("1", "true", "yes", "on")


@login_required
def receipt_sale(request, pk):
    sale = get_object_or_404(Sale.objects.select_related("item"), pk=pk)
    ctx = _receipt_context(
        [sale],
        _sale_kind_label(sale.payment_method),
        customer=sale.customer_name,
        receipt_no=sale.reference,
        hide_costs=_want_hide_costs(request),
    )
    return render(request, "sales/receipt.html", ctx)


@login_required
def receipt_customer(request):
    name = request.GET.get("name", "").strip()
    if not name:
        messages.error(request, "Select a customer first.")
        return redirect("credit_ledger")
    name = normalize_customer_name(name)
    date_from = _parse_date(request.GET.get("date_from", ""))
    date_to = _parse_date(request.GET.get("date_to", ""))
    sales = (
        Sale.objects.filter(customer_name__iexact=name)
        .select_related("item")
        .order_by("date", "id")
    )
    if date_from:
        sales = sales.filter(date__gte=date_from)
    if date_to:
        sales = sales.filter(date__lte=date_to)
    if not sales.exists():
        messages.error(request, f"No sales found for {name}.")
        return redirect("credit_ledger")
    sales_list = list(sales)
    ctx = _receipt_context(sales_list, "SALES RECEIPT", customer=name, hide_costs=_want_hide_costs(request))
    total_paid = sum((s.total_paid for s in sales_list), Decimal("0"))
    ctx["total_paid"] = total_paid
    ctx["balance"] = ctx["total"] - total_paid
    ctx["show_balance"] = True
    ctx["date_from"] = date_from
    ctx["date_to"] = date_to
    return render(request, "sales/receipt.html", ctx)


@login_required
def receipt_selected(request):
    ids = request.GET.get("ids", "").strip()
    pks = [p for p in ids.split(",") if p.strip().isdigit()]
    sales = (
        Sale.objects.filter(pk__in=pks)
        .select_related("item")
        .order_by("date", "id")
    )
    if not pks or not sales.exists():
        messages.error(request, "Select at least one sale to print.")
        return redirect("daily_entry")

    sales_list = list(sales)
    names = {
        normalize_customer_name(s.customer_name)
        for s in sales_list
        if s.customer_name
    }
    customer = next(iter(names)) if len(names) == 1 else ""
    ctx = _receipt_context(sales_list, "SALES RECEIPT", customer=customer, hide_costs=_want_hide_costs(request))
    return render(request, "sales/receipt.html", ctx)


@login_required
def invoice_customer(request):
    name = request.GET.get("name", "").strip()
    if not name:
        messages.error(request, "Select a customer to invoice.")
        return redirect("credit_ledger")

    name = normalize_customer_name(name)
    date_from = _parse_date(request.GET.get("date_from", ""))
    date_to = _parse_date(request.GET.get("date_to", ""))
    sales = (
        Sale.objects.filter(payment_method=Sale.CREDIT, customer_name__iexact=name)
        .select_related("item")
        .order_by("date", "id")
    )
    if date_from:
        sales = sales.filter(date__gte=date_from)
    if date_to:
        sales = sales.filter(date__lte=date_to)
    if not sales.exists():
        messages.error(request, f"No credit sales found for {name}.")
        return redirect("credit_ledger")

    sales_list = list(sales)
    signature = ",".join(str(s.pk) for s in sales_list)

    invoice = Invoice.objects.filter(customer_name=name, signature=signature).first()
    if invoice is None:
        seq = next_invoice_number()
        invoice_date = timezone.localdate()
        invoice = Invoice.objects.create(
            number=f"MM-{invoice_date.year}-{seq:04d}",
            customer_name=name,
            date=invoice_date,
            signature=signature,
            created_by=request.user,
        )
        invoice.sales.set(sales_list)

    total = sum((s.gross or Decimal("0") for s in sales_list), Decimal("0"))
    total_paid = sum((s.total_paid for s in sales_list), Decimal("0"))
    balance = total - total_paid

    if request.GET.get("download") == "pdf":
        return build_invoice_pdf(invoice, sales_list, total, total_paid, balance)

    context = {
        "invoice": invoice,
        "sales": sales_list,
        "total": total,
        "total_paid": total_paid,
        "balance": balance,
        "date_from": date_from,
        "date_to": date_to,
    }
    return render(request, "sales/invoice.html", context)


def _parse_date(value):
    if value:
        try:
            return datetime.date.fromisoformat(value)
        except ValueError:
            pass
    return None


def _selected_date(request):
    raw = request.GET.get("date") or request.POST.get("date")
    if raw:
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError:
            pass
    return timezone.localdate()


def _carry_forward_stock(date):
    """
    Ensure every active item has a Stock record for `date`.
    Opening stock = previous day's remaining, or 0 if no prior record.
    """
    items = Item.objects.filter(active=True)
    existing = set(
        Stock.objects.filter(date=date).values_list("item_id", flat=True)
    )
    previous = Stock.objects.filter(date__lt=date).order_by("item", "-date")
    prev_map = {}
    for s in previous:
        if s.item_id not in prev_map:
            prev_map[s.item_id] = s.remaining_kg
    created = 0
    for item in items:
        if item.pk not in existing:
            Stock.objects.create(
                item=item,
                date=date,
                opening_kg=prev_map.get(item.pk, Decimal("0")),
            )
            created += 1
    return created


@login_required
def daily_entry(request):
    date = _selected_date(request)
    _carry_forward_stock(date)

    filter_payment = request.GET.get("filter_payment", "").strip()
    redirect_params = f"date={date.isoformat()}"
    if filter_payment:
        redirect_params += f"&filter_payment={filter_payment}"

    submit_token = request.session.get("submit_token")
    if not submit_token:
        submit_token = uuid.uuid4().hex
        request.session["submit_token"] = submit_token

    if request.method == "POST" and request.POST.get("submit_token", ""):
        if request.POST.get("submit_token") != submit_token:
            return redirect(f"/?{redirect_params}")

    if request.method == "POST" and "add_sale" in request.POST:
        form = SaleForm(request.POST)
        if form.is_valid():
            sale = form.save(commit=False)
            sale.date = date
            sale.created_by = request.user
            sale.full_clean()
            sale.save()
            messages.success(request, "Sale recorded.")
            request.session["submit_token"] = uuid.uuid4().hex
            return redirect(f"/?{redirect_params}")
    else:
        form = SaleForm()

    bulk_errors = []
    if request.method == "POST" and "add_bulk" in request.POST:
        items = Item.objects.filter(active=True)
        items_by_id = {str(it.pk): it for it in items}
        i = 0
        saved = 0
        while f"item_{i}" in request.POST:
            item_id = request.POST.get(f"item_{i}") or ""
            weight_raw = request.POST.get(f"weight_kg_{i}", "").strip()
            gross_raw = request.POST.get(f"gross_{i}", "").strip()
            payment_method = request.POST.get(f"payment_method_{i}", "") or Sale.NONE
            customer_name = request.POST.get(f"customer_name_{i}", "").strip()
            customer_ctp = request.POST.get(f"customer_ctp_{i}", "").strip()
            remarks = request.POST.get(f"remarks_{i}", "").strip()

            if not item_id or (not weight_raw and not gross_raw):
                i += 1
                continue

            sale = Sale(date=date, payment_method=payment_method,
                        customer_name=customer_name, customer_ctp=customer_ctp,
                        remarks=remarks, created_by=request.user)
            if weight_raw:
                try:
                    sale.weight_kg = Decimal(weight_raw)
                except Exception:
                    bulk_errors.append(f"Row {i+1}: invalid weight '{weight_raw}'")
                    i += 1
                    continue
            if gross_raw:
                try:
                    sale.gross = Decimal(gross_raw)
                except Exception:
                    bulk_errors.append(f"Row {i+1}: invalid amount '{gross_raw}'")
                    i += 1
                    continue

            if item_id not in items_by_id:
                bulk_errors.append(f"Row {i+1}: unknown item")
                i += 1
                continue
            sale.item = items_by_id[item_id]

            try:
                sale.full_clean()
                sale.save()
                saved += 1
            except ValidationError as exc:
                if hasattr(exc, 'message_dict'):
                    parts = []
                    for field, errs in exc.message_dict.items():
                        label = field if field != NON_FIELD_ERRORS else "general"
                        parts.append(f"{label}: {', '.join(errs)}")
                    msg = "; ".join(parts)
                elif hasattr(exc, 'message'):
                    msg = str(exc.message)
                else:
                    msg = str(exc)
                bulk_errors.append(f"Row {i+1}: {msg}")
            i += 1

        if not bulk_errors and saved > 0:
            messages.success(request, f"{saved} sale(s) recorded.")
            request.session["submit_token"] = uuid.uuid4().hex
            return redirect(f"/?{redirect_params}")
        if not bulk_errors and saved == 0:
            bulk_errors.append("No sales entered. Please fill in at least one row.")

    if request.method == "POST" and "add_expense" in request.POST:
        exp_form = ExpenseForm(request.POST)
        if exp_form.is_valid():
            expense = exp_form.save(commit=False)
            expense.date = date
            expense.created_by = request.user
            expense.save()
            messages.success(request, "Expense recorded.")
            request.session["submit_token"] = uuid.uuid4().hex
            return redirect(f"/?{redirect_params}")
    else:
        exp_form = ExpenseForm()

    if request.method == "POST" and "add_service" in request.POST:
        svc_form = OtherServiceForm(request.POST)
        if svc_form.is_valid():
            svc = svc_form.save(commit=False)
            svc.date = date
            svc.created_by = request.user
            svc.save()
            messages.success(request, "Other service recorded.")
            request.session["submit_token"] = uuid.uuid4().hex
            return redirect(f"/?{redirect_params}")
    else:
        svc_form = OtherServiceForm()

    sales = Sale.objects.filter(date=date).select_related("item")
    if filter_payment:
        display_sales = sales.filter(payment_method=filter_payment)
    else:
        display_sales = sales
    expenses = Expense.objects.filter(date=date)
    other_services = OtherService.objects.filter(date=date)

    totals_by_method = {code: Decimal("0") for code, _ in Sale.PAYMENT_CHOICES if code}
    for row in sales.values("payment_method").annotate(total=Sum("gross")):
        totals_by_method[row["payment_method"]] = row["total"] or Decimal("0")

    day_total = sum(totals_by_method.values(), Decimal("0"))
    services_total = other_services.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    services_cash = other_services.filter(payment_method=OtherService.CASH).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    services_mpesa = other_services.filter(payment_method=OtherService.MPESA).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    day_total += services_total
    expense_total = expenses.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    expense_cash = expenses.filter(payment_method=Expense.CASH).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    expense_mpesa = expenses.filter(payment_method=Expense.MPESA).aggregate(t=Sum("amount"))["t"] or Decimal("0")

    credit_payments = CreditPayment.objects.filter(date=date).select_related("sale", "created_by")
    credit_paid_cash = credit_payments.filter(payment_mode=CreditPayment.CASH).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    credit_paid_mpesa = credit_payments.filter(payment_mode=CreditPayment.MPESA).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    credit_paid_total = credit_paid_cash + credit_paid_mpesa

    net_cash = totals_by_method[Sale.CASH] + services_cash + credit_paid_cash - expense_cash

    sold_by_item = (
        sales.values("item__name")
        .annotate(total_kg=Sum("weight_kg"), total_gross=Sum("gross"))
        .order_by("item__name")
    )

    stock_rows = (
        Stock.objects.filter(date=date)
        .select_related("item")
        .order_by("item__name")
    )

    context = {
        "date": date,
        "today": timezone.localdate(),
        "form": form,
        "exp_form": exp_form,
        "svc_form": svc_form,
        "sales": display_sales,
        "expenses": expenses,
        "other_services": other_services,
        "totals_by_method": totals_by_method,
        "day_total": day_total,
        "services_total": services_total,
        "services_cash": services_cash,
        "services_mpesa": services_mpesa,
        "expense_total": expense_total,
        "expense_cash": expense_cash,
        "expense_mpesa": expense_mpesa,
        "net_cash": net_cash,
        "credit_payments": credit_payments,
        "credit_paid_cash": credit_paid_cash,
        "credit_paid_mpesa": credit_paid_mpesa,
        "credit_paid_total": credit_paid_total,
        "sold_by_item": sold_by_item,
        "stock_rows": stock_rows,
        "filter_payment": filter_payment,
        "payment_choices": [(c, l) for c, l in Sale.PAYMENT_CHOICES if c],
        "bulk_errors": bulk_errors,
        "active_items": Item.objects.filter(active=True),
        "creditor_names": sorted({
            normalize_customer_name(n)
            for n in Sale.objects.filter(
                payment_method=Sale.CREDIT
            ).exclude(customer_name="").values_list("customer_name", flat=True)
        }),
        "creditor_ctps": sorted({
            ctp.strip()
            for ctp in Sale.objects.exclude(customer_ctp="").values_list("customer_ctp", flat=True)
            if ctp and ctp.strip()
        }),
        "expense_descriptions": sorted({
            normalize_expense_name(d)
            for d in Expense.objects.values_list("description", flat=True)
        }),
        "submit_token": submit_token,
    }
    return render(request, "sales/daily_entry.html", context)


@login_required
def delete_sale(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    date = sale.date
    fp = request.GET.get("filter_payment", "")
    if request.method == "POST":
        sale.delete()
        messages.success(request, "Sale deleted.")
    return redirect(f"/?date={date.isoformat()}&filter_payment={fp}")


@login_required
def delete_expense(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    date = expense.date
    fp = request.GET.get("filter_payment", "")
    if request.method == "POST":
        expense.delete()
        messages.success(request, "Expense deleted.")
    return redirect(f"/?date={date.isoformat()}&filter_payment={fp}")


@login_required
def delete_other_service(request, pk):
    svc = get_object_or_404(OtherService, pk=pk)
    date = svc.date
    fp = request.GET.get("filter_payment", "")
    if request.method == "POST":
        svc.delete()
        messages.success(request, "Service deleted.")
    return redirect(f"/?date={date.isoformat()}&filter_payment={fp}")


@login_required
def edit_sale(request, pk):
    sale = get_object_or_404(Sale, pk=pk)
    original_weight = sale.weight_kg
    original_gross = sale.gross
    if request.method == "POST":
        form = SaleForm(request.POST, instance=sale)
        if form.is_valid():
            sale = form.save(commit=False)
            if sale.weight_kg != original_weight:
                sale.gross = None
            elif sale.gross != original_gross:
                sale.weight_kg = None
            sale.save()
            messages.success(request, "Sale updated.")
            return redirect(f"/?date={sale.date.isoformat()}")
    else:
        form = SaleForm(instance=sale)
    form.fields["item"].queryset = Item.objects.all()
    return render(request, "sales/edit_entry.html", {
        "form": form,
        "title": f"Edit Sale {sale.reference}",
        "cancel_url": f"/?date={sale.date.isoformat()}",
    })


@login_required
def edit_expense(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == "POST":
        form = ExpenseForm(request.POST, instance=expense)
        if form.is_valid():
            form.save()
            messages.success(request, "Expense updated.")
            return redirect(f"/?date={expense.date.isoformat()}")
    else:
        form = ExpenseForm(instance=expense)
    return render(request, "sales/edit_entry.html", {
        "form": form,
        "title": "Edit Expense",
        "cancel_url": f"/?date={expense.date.isoformat()}",
    })


@login_required
def edit_other_service(request, pk):
    svc = get_object_or_404(OtherService, pk=pk)
    if request.method == "POST":
        form = OtherServiceForm(request.POST, instance=svc)
        if form.is_valid():
            form.save()
            messages.success(request, "Service updated.")
            return redirect(f"/?date={svc.date.isoformat()}")
    else:
        form = OtherServiceForm(instance=svc)
    return render(request, "sales/edit_entry.html", {
        "form": form,
        "title": "Edit Other Service",
        "cancel_url": f"/?date={svc.date.isoformat()}",
    })


@login_required
def creditor_statement(request):
    name = request.GET.get("name", "").strip()
    if not name:
        return redirect("credit_ledger")

    date_from = _parse_date(request.GET.get("date_from", ""))
    date_to = _parse_date(request.GET.get("date_to", ""))

    sales = (
        Sale.objects.filter(payment_method=Sale.CREDIT, customer_name__iexact=name)
        .select_related("item")
        .order_by("date", "id")
    )
    payments = (
        CreditPayment.objects.filter(customer_name__iexact=name)
        .select_related("sale")
        .order_by("date", "id")
    )
    if date_from:
        sales = sales.filter(date__gte=date_from)
        payments = payments.filter(date__gte=date_from)
    if date_to:
        sales = sales.filter(date__lte=date_to)
        payments = payments.filter(date__lte=date_to)

    transactions = []
    for s in sales:
        transactions.append({
            "date": s.date,
            "ctp": s.customer_ctp,
            "kind": "sale",
            "description": s.item.name,
            "debit": s.gross,
            "credit": Decimal("0"),
        })
    for p in payments:
        description = p.note or ("Payment" + (f" — sale {p.sale.reference}" if p.sale else ""))
        transactions.append({
            "date": p.date,
            "ctp": p.customer_ctp,
            "kind": "payment",
            "description": description,
            "debit": Decimal("0"),
            "credit": p.amount,
        })

    transactions.sort(key=lambda t: (t["date"], t["kind"] != "sale"))

    running = Decimal("0")
    for t in transactions:
        running += t["debit"] - t["credit"]
        t["balance"] = running

    total_owed = sum((s.gross for s in sales), Decimal("0"))
    total_paid = sum((p.amount for p in payments), Decimal("0"))

    context = {
        "name": name,
        "transactions": transactions,
        "total_owed": total_owed,
        "total_paid": total_paid,
        "balance": total_owed - total_paid,
        "today": timezone.localdate(),
        "date_from": date_from,
        "date_to": date_to,
    }
    return render(request, "sales/creditor_statement.html", context)


@login_required
def credit_ledger(request):
    q = request.GET.get("q", "").strip()
    date_from = request.GET.get("date_from", "")
    date_to = request.GET.get("date_to", "")

    query_string = request.META.get("QUERY_STRING", "")
    redirect_target = f"/credit/?{query_string}" if query_string else "credit_ledger"

    if request.method == "POST" and "delete_payment" in request.POST:
        payment = get_object_or_404(CreditPayment, pk=request.POST.get("payment_id"))
        payment.delete()
        messages.success(request, "Payment deleted.")
        return redirect(redirect_target)

    if request.method == "POST" and "save_notes" in request.POST:
        name = normalize_customer_name(request.POST.get("customer_name", ""))
        notes = request.POST.get("notes", "").strip()
        if not name:
            messages.error(request, "No customer selected.")
        else:
            creditor = Creditor.objects.filter(name=name).first()
            if creditor is None:
                creditor = Creditor.objects.create(name=name)
            creditor.notes = notes
            creditor.save()
            messages.success(request, f"Notes saved for {name}.")
        return redirect(redirect_target)

    if request.method == "POST" and "settle" in request.POST:
        settle_name = normalize_customer_name(request.POST.get("customer_name", ""))
        raw_amount = request.POST.get("settle_amount", "").strip()
        payment_mode = request.POST.get("payment_mode", CreditPayment.CASH)
        note = request.POST.get("note", "").strip()
        try:
            amount = Decimal(raw_amount)
        except Exception:
            amount = Decimal("0")

        if settle_name and amount > 0:
            unpaid = []
            for s in (
                Sale.objects.filter(
                    payment_method=Sale.CREDIT, customer_name__iexact=settle_name
                )
                .select_related("item")
                .order_by("date", "id")
            ):
                bal = s.balance
                if bal > 0:
                    unpaid.append((s, bal))

            remaining = amount
            for s, bal in unpaid:
                if remaining <= 0:
                    break
                portion = min(remaining, bal)
                CreditPayment.objects.create(
                    customer_name=settle_name,
                    customer_ctp=s.customer_ctp,
                    amount=portion,
                    payment_mode=payment_mode,
                    note=note,
                    sale=s,
                    created_by=request.user,
                )
                remaining = (remaining - portion).quantize(Decimal("0.01"))

            if remaining > 0:
                ctp = unpaid[0][0].customer_ctp if unpaid else ""
                if not ctp:
                    first = (
                        Sale.objects.filter(
                            payment_method=Sale.CREDIT, customer_name__iexact=settle_name
                        )
                        .exclude(customer_ctp="")
                        .order_by("date", "id")
                        .first()
                    )
                    ctp = first.customer_ctp if first else ""
                CreditPayment.objects.create(
                    customer_name=settle_name,
                    customer_ctp=ctp,
                    amount=remaining,
                    payment_mode=payment_mode,
                    note=(note + " — overpayment" if note else "overpayment"),
                    sale=None,
                    created_by=request.user,
                )
            messages.success(
                request,
                f"Applied KES {amount:,.2f} to {settle_name}'s debts."
                + (" Any extra was recorded as an overpayment." if remaining > 0 else ""),
            )
        return redirect(redirect_target)

    if request.method == "POST":
        payment_form = CreditPaymentForm(request.POST)
        if payment_form.is_valid():
            payment = payment_form.save(commit=False)
            payment.created_by = request.user
            payment.save()
            messages.success(request, "Payment recorded.")
            return redirect(redirect_target)
    else:
        payment_form = CreditPaymentForm()

    credit_sales = (
        Sale.objects.filter(payment_method=Sale.CREDIT)
        .exclude(customer_name="")
        .prefetch_related("credit_payments")
        .select_related("item")
        .order_by("customer_name", "-date")
    )

    payments = CreditPayment.objects.select_related("sale", "created_by")

    if date_from:
        credit_sales = credit_sales.filter(date__gte=date_from)
        payments = payments.filter(date__gte=date_from)
    if date_to:
        credit_sales = credit_sales.filter(date__lte=date_to)
        payments = payments.filter(date__lte=date_to)

    if q:
        q_name = normalize_customer_name(q)
        credit_sales = credit_sales.filter(
            Q(customer_name__icontains=q_name) | Q(customer_ctp__icontains=q)
        )
        payments = payments.filter(
            Q(customer_name__icontains=q_name) | Q(customer_ctp__icontains=q)
        )

    customers = {}
    creditor_map = {c.name: c for c in Creditor.objects.all()}
    for sale in credit_sales:
        name = normalize_customer_name(sale.customer_name)
        if name not in customers:
            customers[name] = {"sales": [], "total_owed": Decimal("0"), "total_paid": Decimal("0"), "ctp": "", "creditor": creditor_map.get(name)}
        customers[name]["sales"].append(sale)
        customers[name]["total_owed"] += sale.gross
        if not customers[name]["ctp"] and sale.customer_ctp:
            customers[name]["ctp"] = sale.customer_ctp

    paid_by_sale = {
        row["sale_id"]: row["total"]
        for row in CreditPayment.objects.filter(sale__isnull=False).values("sale_id").annotate(total=Sum("amount"))
    }

    for data in customers.values():
        for s in data["sales"]:
            s_paid = paid_by_sale.get(s.pk, Decimal("0"))
            data["total_paid"] += s_paid
            s.sale_paid = s_paid
            s.sale_balance = s.gross - s_paid

    unlinked_payments = CreditPayment.objects.filter(sale__isnull=True)
    if date_from:
        unlinked_payments = unlinked_payments.filter(date__gte=date_from)
    if date_to:
        unlinked_payments = unlinked_payments.filter(date__lte=date_to)
    if q:
        q_name = normalize_customer_name(q)
        unlinked_payments = unlinked_payments.filter(
            Q(customer_name__icontains=q_name) | Q(customer_ctp__icontains=q)
        )
    for p in unlinked_payments:
        name = normalize_customer_name(p.customer_name)
        if not name:
            continue
        if name not in customers:
            customers[name] = {"sales": [], "total_owed": Decimal("0"), "total_paid": Decimal("0"), "ctp": "", "creditor": creditor_map.get(name)}
        customers[name]["total_paid"] += p.amount
        if not customers[name]["ctp"] and p.customer_ctp:
            customers[name]["ctp"] = p.customer_ctp

    for c in customers.values():
        c["balance"] = c["total_owed"] - c["total_paid"]
        c["paid_count"] = sum(1 for s in c["sales"] if s.sale_balance <= 0)
        if c["balance"] < 0:
            c["overpaid"] = -c["balance"]
    sorted_customers = sorted(customers.items(), key=lambda x: x[1]["balance"], reverse=True)
    if not q:
        sorted_customers = [(n, d) for n, d in sorted_customers if d["balance"] != 0]

    payments = payments.order_by("-date", "-id")[:50]

    creditor_names = sorted({
        normalize_customer_name(n)
        for n in Sale.objects.filter(
            payment_method=Sale.CREDIT
        ).exclude(customer_name="").values_list("customer_name", flat=True)
    })
    creditor_ctps = sorted({
        ctp.strip()
        for ctp in Sale.objects.exclude(customer_ctp="").values_list("customer_ctp", flat=True)
        if ctp and ctp.strip()
    })

    context = {
        "customers": sorted_customers,
        "outstanding_total": sum(
            (c["balance"] for _, c in sorted_customers if c["balance"] > 0),
            Decimal("0"),
        ),
        "payment_form": payment_form,
        "payments": payments,
        "q": q,
        "date_from": date_from,
        "date_to": date_to,
        "creditor_names": creditor_names,
        "creditor_ctps": creditor_ctps,
        "payment_mode_choices": CreditPayment.PAYMENT_MODE_CHOICES,
    }
    return render(request, "sales/credit_ledger.html", context)
