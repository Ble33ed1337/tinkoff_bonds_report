import os
from datetime import datetime, timedelta
from collections import defaultdict, deque
from dotenv import load_dotenv
from tinkoff.invest import Client, OperationState
from tinkoff.invest.utils import quotation_to_decimal
import logging

# Настройка логирования
logging.basicConfig(
    filename='report.log',
    filemode='w',
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s'
)

load_dotenv()
TOKEN = os.getenv("TINKOFF_TOKEN")

CONFIG = {
    'target_coupons': 30000.00,
    'currency': '₽'
}

def format_money(amount):
    """Форматирование суммы с разделителями тысяч"""
    return f"{amount:,.2f} {CONFIG['currency']}".replace(",", " ").replace(".", ",")

def get_operations(client, account_id, from_date, to_date):
    operations = client.operations.get_operations(
        account_id=account_id,
        from_=from_date,
        to=to_date,
        state=OperationState.OPERATION_STATE_EXECUTED
    ).operations
    return operations

def filter_stats(operations):
    stats = {
        'deposits': 0,
        'withdrawals': 0,
        'dividends': 0,
        'amortisation': 0,
        'taxes': 0,
        'commissions': 0,
        'coupons': 0,
    }
    for op in operations:
        op_type = str(op.type).lower()
        op_desc = str(getattr(op, 'description', '')).lower()
        amount = float(quotation_to_decimal(op.payment))
        # Пополнение
        if 'пополн' in op_type or 'зачисление' in op_type or 'депозит' in op_type or 'cash_in' in op_type:
            stats['deposits'] += abs(amount)
        # Вывод
        elif 'вывод' in op_type or 'списание' in op_type or 'cash_out' in op_type:
            stats['withdrawals'] += abs(amount)
        # Купоны (по типу или описанию)
        elif 'купон' in op_type or 'coupon' in op_type or 'купон' in op_desc or 'coupon' in op_desc:
            stats['coupons'] += abs(amount)
        # Дивиденды (по типу или описанию)
        elif 'дивиденд' in op_type or 'dividend' in op_type or 'дивиденд' in op_desc or 'dividend' in op_desc:
            stats['dividends'] += abs(amount)
        # Амортизация
        elif 'амортизац' in op_type or 'amortis' in op_type:
            stats['amortisation'] += abs(amount)
        # Комиссии
        elif 'комисс' in op_type or 'fee' in op_type:
            stats['commissions'] += abs(amount)
        # Налоги
        elif 'налог' in op_type or 'tax' in op_type:
            stats['taxes'] += abs(amount)
    return stats

def calculate_real_sales_profit(operations):
    # FIFO по каждому инструменту
    buys = defaultdict(deque)
    profit = 0.0
    for op in sorted(operations, key=lambda x: x.date):
        op_type = str(op.type).lower()
        figi = getattr(op, 'figi', None)
        quantity = getattr(op, 'quantity', 0)
        price = float(quotation_to_decimal(op.price)) if hasattr(op, 'price') and op.price else 0
        amount = float(quotation_to_decimal(op.payment))
        fee = 0  # Комиссия может быть отдельной операцией
        # Покупка
        if ('покупк' in op_type or 'buy' in op_type) and amount < 0 and figi and quantity > 0:
            buys[figi].append({'price': abs(amount) / quantity, 'qty': quantity})
        # Продажа
        elif ('продаж' in op_type or 'sell' in op_type) and amount > 0 and figi and quantity > 0:
            qty_to_sell = quantity
            sale_sum = abs(amount) - fee
            cost_sum = 0.0
            while qty_to_sell > 0 and buys[figi]:
                lot = buys[figi][0]
                take_qty = min(lot['qty'], qty_to_sell)
                cost_sum += lot['price'] * take_qty
                lot['qty'] -= take_qty
                qty_to_sell -= take_qty
                if lot['qty'] == 0:
                    buys[figi].popleft()
            if qty_to_sell > 0:
                cost_sum += (abs(amount) / quantity) * qty_to_sell
            profit += sale_sum - cost_sum
    return profit

def get_portfolio_value(client, account_id):
    portfolio = client.operations.get_portfolio(account_id=account_id)
    return float(quotation_to_decimal(portfolio.total_amount_portfolio))

def generate_report(client):
    accounts = client.users.get_accounts().accounts
    broker_account = next((acc for acc in accounts if acc.type == 1), None)
    if not broker_account:
        print("❌ Брокерский счет не найден")
        return
    account_id = broker_account.id
    now = datetime.now()
    month_start = datetime(now.year, now.month, 1)
    all_time_start = datetime(2023, 1, 1)  # или дата открытия счёта
    # Операции
    operations_all = get_operations(client, account_id, all_time_start, now)
    operations_month = get_operations(client, account_id, month_start, now)
    week_start = now - timedelta(days=7)
    operations_week = get_operations(client, account_id, week_start, now)
    # Добавляем операции за день
    day_start = datetime(now.year, now.month, now.day)
    operations_day = get_operations(client, account_id, day_start, now)
    # Статистика
    stats_month = filter_stats(operations_month)
    stats_all = filter_stats(operations_all)
    stats_week = filter_stats(operations_week)
    stats_day = filter_stats(operations_day)
    real_sales_profit_month = calculate_real_sales_profit(operations_month)
    real_sales_profit_all = calculate_real_sales_profit(operations_all)
    real_sales_profit_day = calculate_real_sales_profit(operations_day)
    portfolio_value = get_portfolio_value(client, account_id)
    net_invested = stats_all['deposits'] - stats_all['withdrawals']
    price_diff = portfolio_value - net_invested
    yield_pct = (price_diff / net_invested) * 100 if net_invested != 0 else 0
    # --- Получение тикера и названия по FIGI через API ---
    instrument_cache = {}
    def get_instrument_info(figi, client):
        if not figi:
            return ('unknown', '')
        if figi in instrument_cache:
            return instrument_cache[figi]
        try:
            ins = client.instruments.find_instrument(query=figi).instruments
            if ins:
                name = ins[0].name or 'unknown'
                ticker = ins[0].ticker or ''
                instrument_cache[figi] = (name, ticker)
                return name, ticker
        except Exception as e:
            logging.error(f"Ошибка при поиске инструмента по FIGI {figi}: {e}")
        instrument_cache[figi] = ('unknown', '')
        return 'unknown', ''

    # Формируем блок 3 только за месяц с названием компании и тикером
    block3 = '\n3. Топ-5 компаний/облигаций по купонным выплатам за месяц:'
    block3 += '\nКомпания/Эмитент                              | Тикер       | За месяц'
    block3 += '\n----------------------------------------------|-------------|------------'
    coupon_map = defaultdict(lambda: {'sum': 0.0, 'name': '', 'ticker': ''})
    for op in operations_month:
        op_type = str(op.type).lower()
        op_desc = str(getattr(op, 'description', '')).lower()
        amount = float(quotation_to_decimal(op.payment))
        if 'купон' in op_type or 'coupon' in op_type or 'купон' in op_desc or 'coupon' in op_desc:
            name = getattr(op, 'name', None)
            ticker = getattr(op, 'ticker', None)
            figi = getattr(op, 'figi', None)
            if not name or not ticker:
                name_api, ticker_api = get_instrument_info(figi, client)
                name = name or name_api or op_desc or 'unknown'
                ticker = ticker or ticker_api or ''
            key = f"{name}|{ticker}"
            coupon_map[key]['sum'] += abs(amount)
            coupon_map[key]['name'] = name
            coupon_map[key]['ticker'] = ticker
    top5 = sorted(coupon_map.values(), key=lambda x: x['sum'], reverse=True)[:5]
    for item in top5:
        block3 += f"\n{item['name']:<40} | {item['ticker']:<12} | {format_money(item['sum']):>10}"

    # Новый блок статистики за день
    block_day = f"""
1.1 За день:
◻️ Купоны: {format_money(stats_day['coupons'])}
◻️ Дивиденды: {format_money(stats_day['dividends'])}
◻️ Пополнено: +{format_money(stats_day['deposits'])}
◻️ Выведено: -{format_money(stats_day['withdrawals'])}
◻️ Прибыль от продаж: +{format_money(real_sales_profit_day)}
◻️ Получено начислений: +{format_money(stats_day['dividends'] + stats_day['coupons'])}
◻️ Налоги: -{format_money(stats_day['taxes'])}
◻️ Уплачено комиссий: -{format_money(stats_day['commissions'])}
"""

    # --- Новый блоки детализации ---
    # 3. Топ-5 по комиссиям за месяц
    commission_map_month = defaultdict(lambda: {'sum': 0.0, 'name': '', 'ticker': ''})
    for op in operations_month:
        op_type = str(op.type).lower()
        op_desc = str(getattr(op, 'description', '')).lower()
        amount = float(quotation_to_decimal(op.payment))
        if 'комисс' in op_type or 'fee' in op_type:
            name = getattr(op, 'name', None)
            ticker = getattr(op, 'ticker', None)
            figi = getattr(op, 'figi', None)
            if not name or not ticker:
                name_api, ticker_api = get_instrument_info(figi, client)
                name = name or name_api or op_desc or 'unknown'
                ticker = ticker or ticker_api or ''
            key = f"{name}|{ticker}"
            commission_map_month[key]['sum'] += abs(amount)
            commission_map_month[key]['name'] = name
            commission_map_month[key]['ticker'] = ticker
    top5_comm_month = sorted(commission_map_month.values(), key=lambda x: x['sum'], reverse=True)[:5]
    block_comm_month = '\n6. Топ-5 по комиссиям за месяц:'
    block_comm_month += '\nКомпания/Эмитент                              | Тикер       | За месяц'
    block_comm_month += '\n----------------------------------------------|-------------|------------'
    for item in top5_comm_month:
        block_comm_month += f"\n{item['name']:<40} | {item['ticker']:<12} | {format_money(item['sum']):>10}"

    # 6. Сравнение с предыдущим днем и месяцем
    prev_day_start = day_start - timedelta(days=1)
    prev_day_end = day_start
    operations_prev_day = get_operations(client, account_id, prev_day_start, prev_day_end)
    stats_prev_day = filter_stats(operations_prev_day)
    prev_month_end = month_start
    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    operations_prev_month = get_operations(client, account_id, prev_month_start, prev_month_end)
    stats_prev_month = filter_stats(operations_prev_month)
    block_compare = '\n9. Сравнение с предыдущим днем и месяцем:'
    block_compare += f"\nКупоны за день: {format_money(stats_day['coupons'])} (вчера: {format_money(stats_prev_day['coupons'])})"
    block_compare += f"\nКупоны за месяц: {format_money(stats_month['coupons'])} (прошлый месяц: {format_money(stats_prev_month['coupons'])})"

    report = f"""
Купонная зарплата, ежемесячный отчет - {now.strftime('%B').lower()}

{block_day}
1. За месяц:
◻️ Купоны: {format_money(stats_month['coupons'])}
◻️ Получено за неделю: +{format_money(stats_week['dividends'] + stats_week['coupons'])}
◻️ Пополнено из вне за месяц: +{format_money(stats_month['deposits'])}
◻️ Цель: ежемесячно не меньше {format_money(CONFIG['target_coupons'])} {'✅' if stats_month['coupons'] >= CONFIG['target_coupons'] else '❌'}
◻️ Портфель: {format_money(portfolio_value)}
◻️ Прибыль от продаж: +{format_money(real_sales_profit_month)}
◻️ Получено начислений: +{format_money(stats_month['dividends'] + stats_month['coupons'])}
◻️ Налоги: -{format_money(stats_month['taxes'])}
◻️ Уплачено комиссий: -{format_money(stats_month['commissions'])}

2. За весь период:
◻️ Пополнено/выведено средств: +{format_money(stats_all['deposits'])} / -{format_money(stats_all['withdrawals'])}
◻️ Разница цены активов: {format_money(price_diff)} ({'+' if price_diff >= 0 else ''})
◻️ Прибыль от продаж: +{format_money(real_sales_profit_all)}
◻️ Получено начислений: +{format_money(stats_all['dividends'] + stats_all['coupons'])}
◻️ Налоги: -{format_money(stats_all['taxes'])}
◻️ Уплачено комиссий: -{format_money(stats_all['commissions'])}
◻️ Амортизация: {format_money(stats_all['amortisation'])}
◻️ Доходность портфеля: {yield_pct:.2f}%

{block3}
{block_comm_month}
{block_compare}
"""
    print(report)

def main():
    with Client(TOKEN) as client:
        generate_report(client)

if __name__ == "__main__":
    main()