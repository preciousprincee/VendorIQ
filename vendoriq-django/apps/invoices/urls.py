from django.urls import path
from .views import InvoiceListCreateView, InvoiceDetailView, InvoiceStatusView, InvoiceSendView, CreateInvoiceFromSaleView

urlpatterns = [
    path('<uuid:store_id>/invoices/', InvoiceListCreateView.as_view()),
    path('<uuid:store_id>/invoices/<uuid:invoice_id>/', InvoiceDetailView.as_view()),
    path('<uuid:store_id>/invoices/<uuid:invoice_id>/status/', InvoiceStatusView.as_view()),
    path('<uuid:store_id>/invoices/<uuid:invoice_id>/send/', InvoiceSendView.as_view()),
    path('<uuid:store_id>/sales/<uuid:sale_id>/create-invoice/', CreateInvoiceFromSaleView.as_view()),
]
