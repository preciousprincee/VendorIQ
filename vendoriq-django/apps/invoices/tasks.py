import logging

from celery import shared_task
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import Invoice

logger = logging.getLogger(__name__)


@shared_task
def send_invoice_email_task(invoice_id, recipient, store_name):
    """
    Runs on the Celery worker, not the web request - a slow or unreachable
    SMTP provider here costs worker time, not a gunicorn thread that a real
    user is waiting on.

    In local dev with no REDIS_URL set, CELERY_TASK_ALWAYS_EAGER makes this
    execute synchronously and inline anyway (see settings.py), so nothing
    extra needs to run to test this locally.
    """
    try:
        invoice = Invoice.objects.prefetch_related('invoice_items__product').get(id=invoice_id)
    except Invoice.DoesNotExist:
        # Invoice was deleted between being queued and the worker picking
        # this up - nothing to send.
        logger.warning('send_invoice_email_task: invoice %s no longer exists, skipping', invoice_id)
        return

    items = [{
        'product_name': item.product.name,
        'quantity': item.quantity,
        'unit_price': item.unit_price,
        'line_total': item.unit_price * item.quantity,
    } for item in invoice.invoice_items.all()]

    html_body = render_to_string('invoices/invoice_email.html', {
        'invoice': invoice,
        'items': items,
        'store_name': store_name,
        'currency_symbol': '₦',
    })

    email = EmailMultiAlternatives(
        subject=f'Invoice from {store_name}',
        body=f'Your invoice from {store_name} - total {invoice.total_amount}. View in HTML for full details.',
        to=[recipient],
    )
    email.attach_alternative(html_body, 'text/html')
    email.send(fail_silently=False)  # lets the exception propagate - logged below and visible in worker logs

    logger.info('Invoice %s emailed to %s', invoice_id, recipient)
