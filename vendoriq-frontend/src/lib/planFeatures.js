// Upsell copy for each Pro feature. Keys must match apps/billing/plans.py's
// FEATURES dict on the backend - that's the contract between the two sides
// (the backend decides what's locked, this decides how to explain why it's
// worth paying for). Keep the wording benefit-focused, matching the spec's
// example ("See which products are driving your profit...") rather than
// just repeating the feature's name.
export const FEATURE_COPY = {
  multiple_stores: {
    title: 'Unlock Multiple Stores',
    description: 'Run more than one shop or branch from a single VendorIQ account.',
  },
  multiple_staff: {
    title: 'Unlock Staff Accounts',
    description: 'Add managers and cashiers with their own logins and permissions.',
  },
  advanced_sales_analytics: {
    title: 'Unlock Advanced Analytics',
    description: 'See which products are driving your profit, identify sales trends, and understand where your money is going.',
  },
  advanced_profit_analytics: {
    title: 'Unlock Advanced Profit Analytics',
    description: 'See true store profitability after overhead, broken down by today, this month, and all time.',
  },
  advanced_expense_analytics: {
    title: 'Unlock Advanced Expense Analytics',
    description: 'Break overhead and misc spending down by category to see exactly where costs are creeping up.',
  },
  detailed_reports: {
    title: 'Unlock Detailed Reports',
    description: 'Get a full breakdown of sales, profit, and stock movement over any period.',
  },
  data_export: {
    title: 'Unlock CSV Exports',
    description: 'Download your full bookkeeping records as a CSV - handy for loan applications and accountants.',
  },
  invoicing: {
    title: 'Unlock Invoicing',
    description: 'Create and send professional invoices to your customers, and track which ones are paid.',
  },
  customer_management: {
    title: 'Unlock Customer Management',
    description: 'Keep a record of your customers, sell to them on credit, and see who owes you and how much.',
  },
  cloud_backup: {
    title: 'Unlock Cloud Backup',
    description: 'Download a complete backup of your store - products, sales, customers, expenses and invoices - any time, and keep a copy safe if your device is lost or damaged.',
  },
  advanced_low_stock_insights: {
    title: 'Unlock Advanced Low-Stock Insights',
    description: 'Get restock suggestions based on how fast each product actually sells, not just a fixed threshold.',
  },
  automated_summaries: {
    title: 'Unlock Automated Business Summaries',
    description: 'Get a daily or weekly summary of how your business is doing, without opening the app.',
  },
  ai_assistant: {
    title: 'Unlock the AI Business Assistant',
    description: 'Ask questions about your sales, profit, and stock in plain language and get instant answers.',
  },
  advanced_dashboard: {
    title: 'Unlock Advanced Dashboard Insights',
    description: 'See a deeper breakdown of what\u2019s driving your numbers, right on your dashboard.',
  },
  long_term_history: {
    title: 'Unlock Longer History',
    description: 'Look back further than 14 days to spot real trends in your sales and profit.',
  },
}
