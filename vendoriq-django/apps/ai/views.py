from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.conf import settings
from django.utils import timezone
from django.db.models import Sum, F, DecimalField
import logging
import requests
from apps.stores.base_views import StoreScopedAPIView
from apps.stores.permissions import get_store_or_404, require_store_access
from apps.products.models import Product
from apps.sales.models import Sale, SaleItem
from apps.billing.entitlements import require_ai_assistant
from .models import ChatMessage

logger = logging.getLogger(__name__)

# The AI assistant answers with revenue, profit, and stock-value figures,
# so it is restricted the same way the dashboard and insights are - cashiers excluded.
AI_ROLES = ['OWNER', 'MANAGER']

HISTORY_LIMIT = 50  # keep prompts small and the UI snappy

# The actual model id lives in settings.GROQ_MODEL (env-var driven - see
# vendoriq/settings.py) rather than a constant here, specifically so a
# future Groq deprecation is a config change, not a code change. If the AI
# assistant starts returning "service unavailable", check
# https://console.groq.com/docs/deprecations first - a decommissioned
# model quietly returning "model_decommissioned" for a while (masked by the
# blanket except/503 below) is exactly how this has broken before.


def build_store_context(store):
    now = timezone.now()
    # See the identical fix + explanation in apps/insights/views.py -
    # TIME_ZONE is Africa/Lagos (UTC+1), so .replace() must run on the
    # localtime()-converted value or "today"/"this month" boundaries land on
    # UTC midnight instead of Lagos midnight, occasionally telling the AI
    # assistant "today's revenue" figures that are actually yesterday's.
    local_now = timezone.localtime(now)
    month_start = local_now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    today_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)

    products = Product.objects.filter(store=store)
    today_sales = Sale.objects.filter(store=store, created_at__gte=today_start).aggregate(
        revenue=Sum('total_amount'), profit=Sum('total_profit')
    )
    month_sales = Sale.objects.filter(store=store, created_at__gte=month_start).aggregate(
        revenue=Sum('total_amount'), profit=Sum('total_profit')
    )
    best_sellers = SaleItem.objects.filter(
        sale__store=store, sale__created_at__gte=month_start
    ).values('product__name').annotate(total=Sum('quantity')).order_by('-total')[:3]

    low_stock = products.filter(quantity__lte=F('low_stock_threshold'))
    total_stock_value = products.aggregate(
        value=Sum(F('cost_price') * F('quantity'), output_field=DecimalField())
    )['value'] or 0

    # Every other figure here (today/month revenue+profit, total stock
    # value, best sellers, low stock) comes from a SQL aggregate - correct
    # and cheap regardless of catalog size. This per-product text listing
    # is different: it was iterating and writing out EVERY product with no
    # cap at all. Pro plan advertises unlimited products, so a real,
    # successful Pro store with a few thousand SKUs would build a prompt
    # of tens of thousands of tokens just for this section - risking
    # hitting the LLM's context limit outright (a hard failure), and at
    # minimum making every single AI request slow and expensive, for
    # exactly the largest paying customers the Pro tier exists to serve
    # well. Capped to a reasonable number; the note below tells the model
    # (and, if it repeats this back, the user) that the list is partial
    # rather than silently pretending a 3,000-product store only has 150.
    PRODUCT_LIST_CAP = 150
    total_product_count = products.count()
    listed_products = products[:PRODUCT_LIST_CAP]

    products_text = '\n'.join([
        f"- {p.name}: cost={p.cost_price}, price={p.selling_price}, stock={p.quantity}"
        for p in listed_products
    ])
    if total_product_count > PRODUCT_LIST_CAP:
        products_text += f'\n... and {total_product_count - PRODUCT_LIST_CAP} more products not shown here (ask about a specific product by name if needed).'
    best_text = '\n'.join([f"{i+1}. {b['product__name']} ({b['total']} sold)" for i, b in enumerate(best_sellers)]) or 'No sales yet'
    low_text = '\n'.join([f"- {p.name}: {p.quantity} left" for p in low_stock[:PRODUCT_LIST_CAP]]) or 'All products sufficiently stocked'

    return f"""
You are a smart business assistant for {store.name} on VendorIQ.
Answer questions based ONLY on the data below. Be concise and speak like a knowledgeable business advisor.

--- STORE DATA ---
Products ({total_product_count} total):
{products_text}

Today: Revenue={today_sales['revenue'] or 0}, Profit={today_sales['profit'] or 0}
This Month: Revenue={month_sales['revenue'] or 0}, Profit={month_sales['profit'] or 0}
Total Stock Value (at cost): {total_stock_value}

Top Selling This Month:
{best_text}

Low Stock:
{low_text}
--- END DATA ---
"""


class ChatView(APIView):
    """
    Note: this one stays on the explicit get_store_or_404/require_store_access
    pattern rather than StoreScopedAPIView - its URL (/api/ai/chat/) has no
    <uuid:store_id> segment, since the store is chosen client-side and sent
    as `storeId` in the POST body instead. StoreScopedAPIView resolves the
    store from URL kwargs, so it has nothing to hook into here.
    """

    def post(self, request):
        message = request.data.get('message', '').strip()
        store_id = request.data.get('storeId')

        if not message or not store_id:
            return Response({'error': 'Message and storeId are required.'}, status=status.HTTP_400_BAD_REQUEST)

        store = get_store_or_404(store_id, request.user)
        require_store_access(store, request.user, AI_ROLES)
        require_ai_assistant(store.owner)

        context = build_store_context(store)

        if not settings.GROQ_API_KEY:
            return Response({'error': 'AI service not configured.'}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # Save the user's message right away so it's part of history even if
        # the upstream AI call fails.
        ChatMessage.objects.create(store=store, user=request.user, role=ChatMessage.Role.USER, content=message)

        # Recent conversation turns give the model short-term memory of this
        # chat, without re-sending the whole history every time.
        recent = ChatMessage.objects.filter(store=store, user=request.user).order_by('-created_at')[:20]
        history_messages = [
            {'role': m.role, 'content': m.content} for m in reversed(recent)
        ]

        try:
            response = requests.post(
                'https://api.groq.com/openai/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {settings.GROQ_API_KEY}',
                    'Content-Type': 'application/json',
                },
                json={
                    'model': settings.GROQ_MODEL,
                    'messages': [
                        {'role': 'system', 'content': context},
                        *history_messages,
                    ],
                    'max_tokens': 500,
                    'temperature': 0.3,
                },
                timeout=30
            )
        except requests.exceptions.RequestException:
            logger.error('Groq request failed (network/timeout)', exc_info=True)
            return Response({'error': 'AI service unavailable. Please try again shortly.'}, status=status.HTTP_502_BAD_GATEWAY)

        if response.status_code != 200:
            # Log the real reason (bad/expired key, decommissioned model,
            # rate limit, etc) instead of just telling the user "unavailable"
            # with no trace anywhere - that's exactly how the last outage
            # (a silently deprecated model) went unnoticed for weeks.
            logger.error('Groq API returned %s: %s', response.status_code, response.text[:500])
            return Response({'error': 'AI service unavailable. Please try again shortly.'}, status=status.HTTP_502_BAD_GATEWAY)

        try:
            data = response.json()
            reply = data['choices'][0]['message']['content']
        except (ValueError, KeyError, IndexError):
            logger.error('Unexpected Groq response shape: %s', response.text[:500])
            return Response({'error': 'AI service returned an unexpected response.'}, status=status.HTTP_502_BAD_GATEWAY)

        ChatMessage.objects.create(store=store, user=request.user, role=ChatMessage.Role.ASSISTANT, content=reply)
        return Response({'reply': reply})


class ChatHistoryView(StoreScopedAPIView):
    allowed_roles = AI_ROLES

    def get(self, request, store_id):
        messages = ChatMessage.objects.filter(store=self.store, user=request.user).order_by('created_at')[:HISTORY_LIMIT]
        return Response({
            'messages': [{'role': m.role, 'content': m.content, 'createdAt': m.created_at} for m in messages]
        })

    def delete(self, request, store_id):
        ChatMessage.objects.filter(store=self.store, user=request.user).delete()
        return Response({'message': 'Chat cleared.'})
