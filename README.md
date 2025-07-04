# Tinkoff Bonds Report

Скрипт для формирования подробного отчёта по купонным выплатам, дивидендам, комиссиям и другим операциям по вашему брокерскому счёту в Тинькофф Инвестиции.

## Возможности

- Автоматически собирает статистику по купонам, дивидендам, комиссиям, налогам, пополнениям и выводам средств.
- Формирует отчёты за день, неделю, месяц и весь период.
- Показывает топ-5 эмитентов по купонным выплатам и комиссиям за месяц.
- Сравнивает текущие показатели с предыдущим днём и месяцем.
- Поддерживает работу с несколькими счетами (выбирает брокерский).

## Требования

- Python 3.7+
- Токен доступа к OpenAPI Тинькофф Инвестиций
- Установленные зависимости:
  - `tinkoff-invest-api`
  - `python-dotenv`

## Установка зависимостей

```bash
pip install tinkoff-invest-api python-dotenv
```

## Настройка

1. Получите токен OpenAPI Тинькофф Инвестиций:  
   [Инструкция](https://tinkoff.github.io/investAPI/token/)
2. Создайте файл `.env` в корне проекта и добавьте в него строку:

   ```
   TINKOFF_TOKEN=ваш_токен_сюда
   ```

## Запуск

### Через Python

```bash
python report.py
```

### Через Windows (bat-файл)

Двойной клик по файлу `tinkoff_report_run.bat`  
(убедитесь, что путь к Python в bat-файле соответствует вашей системе).

## Пример вывода

```
Купонная зарплата, ежемесячный отчет - июнь

1.1 За день:
◻️ Купоны: 1 000,00 ₽
◻️ Дивиденды: 0,00 ₽
...
3. Топ-5 компаний/облигаций по купонным выплатам за месяц:
Компания/Эмитент         | Тикер   | За месяц
----------------------------------------------
...
```

## Логи

В процессе работы создаётся файл `report.log` с подробностями выполнения и возможными ошибками.

## Примечания

- Скрипт работает только с брокерским счётом (не ИИС).
- Дата начала анализа задана в коде (январь 2023), при необходимости измените её в функции `generate_report`.
- Для корректной работы требуется стабильное интернет-соединение. 