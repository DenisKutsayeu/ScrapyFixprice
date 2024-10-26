# FixPrice Scrapy Parser

Проект предназначен для парсинга страниц товаров с сайта FixPrice с использованием библиотеки Scrapy.

## Установка зависимостей

Перед запуском проекта необходимо установить все необходимые зависимости, указанные в файле `requirements.txt`. Для этого выполните команду:

```
pip install -r requirements.txt
```

# Запуск проекта
Нужно перейти в директорию:
```
cd fixprice
```

Запустите парсинг с помощью команды Scrapy
```
scrapy crawl fixprice_spider
```

# О проекте
Данный парсер собирает информацию о товарах с сайта FixPrice и сохраняет их для дальнейшей работы. Проект использует фреймворк Scrapy для эффективного и быстрого сбора данных.