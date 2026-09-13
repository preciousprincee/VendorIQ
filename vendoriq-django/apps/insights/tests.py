import pytest
from datetime import date
from apps.products.models import Product
from apps.sales.models import Sale, SaleItem
from apps.expenses.models import Expense


@pytest.mark.django_db
class TestDashboardNetProfit:
    """
    The dashboard hero card used to show gross sales profit (revenue - cost
    of goods) with zero expense deduction, mislabeled as just "Profit".
    These lock in that it's now genuinely net of expenses.
    """

    def test_net_profit_deducts_expenses_from_sales_profit(self, owner_client, store, owner_user):
        product = Product.objects.create(store=store, name='Widget', cost_price='100.00', selling_price='150.00', quantity=10)
        sale = Sale.objects.create(store=store, recorded_by=owner_user, total_amount=300, total_profit=100)
        SaleItem.objects.create(sale=sale, product=product, quantity=2, unit_price=150, unit_cost=100, profit=100)
        Expense.objects.create(store=store, category='RENT', description='Rent', amount='40.00', incurred_on=date.today())

        response = owner_client.get(f'/api/stores/{store.id}/insights/dashboard/')
        assert response.status_code == 200
        today = response.data['today']
        assert today['salesProfit'] == 100.0
        assert today['expenses'] == 40.0
        assert today['netProfit'] == 60.0  # 100 sales profit - 40 expenses, not just 100

    def test_net_profit_with_no_expenses_equals_sales_profit(self, owner_client, store, owner_user):
        product = Product.objects.create(store=store, name='Widget', cost_price='100.00', selling_price='150.00', quantity=10)
        sale = Sale.objects.create(store=store, recorded_by=owner_user, total_amount=150, total_profit=50)
        SaleItem.objects.create(sale=sale, product=product, quantity=1, unit_price=150, unit_cost=100, profit=50)

        response = owner_client.get(f'/api/stores/{store.id}/insights/dashboard/')
        assert response.data['today']['netProfit'] == 50.0

    def test_dashboard_includes_comparison_baselines(self, owner_client, store):
        response = owner_client.get(f'/api/stores/{store.id}/insights/dashboard/')
        assert response.status_code == 200
        # These are the like-for-like comparison periods the frontend uses
        # for the hero card's up/down arrow - a partial period must never be
        # compared against a full previous month again.
        for key in ('today', 'yesterday', 'week', 'priorWeek', 'month', 'prevMonthToDate'):
            assert key in response.data
            assert 'netProfit' in response.data[key]
