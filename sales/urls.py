from django.urls import path

from . import views, views_admin

urlpatterns = [
    path("", views.daily_entry, name="daily_entry"),
    path("sale/<int:pk>/delete/", views.delete_sale, name="delete_sale"),
    path("sale/<int:pk>/edit/", views.edit_sale, name="edit_sale"),
    path("expense/<int:pk>/delete/", views.delete_expense, name="delete_expense"),
    path("expense/<int:pk>/edit/", views.edit_expense, name="edit_expense"),
    path("service/<int:pk>/delete/", views.delete_other_service, name="delete_other_service"),
    path("service/<int:pk>/edit/", views.edit_other_service, name="edit_other_service"),
    path("credit/", views.credit_ledger, name="credit_ledger"),
    path("credit/statement/", views.creditor_statement, name="creditor_statement"),
    path("credit/invoice/", views.invoice_customer, name="invoice_customer"),
    path("receipt/sale/<int:pk>/", views.receipt_sale, name="receipt_sale"),
    path("receipt/customer/", views.receipt_customer, name="receipt_customer"),
    path("receipt/selected/", views.receipt_selected, name="receipt_selected"),
    path("manage/items/", views_admin.admin_items, name="admin_items"),
    path("manage/suppliers/", views_admin.admin_suppliers, name="admin_suppliers"),
    path("manage/suppliers/<int:pk>/edit/", views_admin.admin_supplier_edit, name="admin_supplier_edit"),
    path("manage/suppliers/<int:pk>/pay/", views_admin.admin_supplier_pay, name="admin_supplier_pay"),
    path("manage/suppliers/<int:pk>/history/", views_admin.admin_supplier_history, name="admin_supplier_history"),
    path("manage/suppliers/<int:pk>/history/download/", views_admin.admin_supplier_history_download, name="admin_supplier_history_download"),
    path("manage/sales/", views_admin.admin_sales, name="admin_sales"),
    path("manage/expenses/", views_admin.admin_expenses, name="admin_expenses"),
    path("manage/users/", views_admin.admin_users, name="admin_users"),
    path("manage/stock/", views_admin.admin_stock, name="admin_stock"),
    path("manage/reports/", views_admin.admin_reports, name="admin_reports"),
    path("manage/reports/export/", views_admin.admin_reports_export, name="admin_reports_export"),
]
