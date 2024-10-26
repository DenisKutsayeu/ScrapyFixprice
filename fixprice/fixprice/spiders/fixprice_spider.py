import re
from datetime import datetime
from typing import List

import requests
from demjson3 import decode
from parsel import Selector
from scrapy import Spider, Request


HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "origin": "https://fix-price.com",
    "priority": "u=1, i",
    "referer": "https://fix-price.com/",
    "sec-ch-ua": '"Chromium";v="130", "Google Chrome";v="130", "Not?A_Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "x-city": "55",
    "x-key": "6d6821d06bc7881185e9c18e9d1287af",
    "x-language": "ru",
}
COOKIES = {
    "locality": "%7B%22city%22%3A%22%D0%95%D0%BA%D0%B0%D1%82%D0%B5%D1%80%D0%B8%D0%BD%D0%B1%D1%83%D1%80%D0%B3%22%2C%22cityId%22%3A55%2C%22longitude%22%3A60.597474%2C%22latitude%22%3A56.838011%2C%22prefix%22%3A%22%D0%B3%22%7D",
}
session = requests.Session()
session.headers.update(HEADERS)
session.cookies.update(COOKIES)


class SelectorListF(Selector):
    def extract(self) -> List[str]:
        return self.getall()

    def extract_first(self, default=None) -> str:
        return self.get(default=default)


def xpath(text: str, query: str) -> SelectorListF:
    return Selector(text=text).xpath(query=query)


class FixPriceSpider(Spider):
    name = "fixprice_spider"

    custom_settings = {
        "FEEDS": {
            "output.json": {
                "format": "json",
                "encoding": "utf8",
                "indent": 4,
            }
        }
    }

    start_urls = [
        "https://fix-price.com/catalog/kosmetika-i-gigiena/ukhod-za-polostyu-rta",
        "https://fix-price.com/catalog/kosmetika-i-gigiena/gigienicheskie-sredstva",
        "https://fix-price.com/catalog/krasota-i-zdorove/dlya-tela",
    ]

    def start_requests(self):
        for url in self.start_urls:
            yield Request(
                url=url,
                callback=self.parse_category,
                cookies=COOKIES,
                meta={"category_url": url, "page_count": 1},
            )

    def parse_category(self, response):
        category_url = response.meta["category_url"]
        page_count = response.meta["page_count"]

        self.logger.info(f"Parsing category: {category_url}, page {page_count}")

        product_links = xpath(
            response.text,
            "//div[@class='product__wrapper']//div[@class='description']//a//@href",
        ).extract()
        if not product_links:
            self.logger.info(
                f"No more products found in category: {category_url} on page {page_count}. Stopping pagination."
            )
            return

        for product_link in product_links:
            yield Request(
                url=response.urljoin(product_link),
                callback=self.parse_product,
                cookies=COOKIES,
                meta={"category_url": category_url},
            )

        next_page_url = f"{category_url}?page={page_count + 1}"
        self.logger.info(f"Fetching next page: {next_page_url}")
        yield Request(
            url=next_page_url,
            callback=self.parse_category,
            cookies=COOKIES,
            meta={"category_url": category_url, "page_count": page_count + 1},
        )

    def parse_product(self, response):
        attributes = self.get_item_info(response)

        yield {
            "timestamp": int(datetime.now().timestamp()),
            "RPC": attributes["RPC"],
            "url": response.url,
            "title": attributes["title"],
            "brand": attributes["brand"],
            "section": attributes["section"],
            "price_data": attributes["price_data"],
            "stock": attributes["stock"],
            "assets": attributes["assets"],
            "metadata": attributes["metadata"],
            "variants": attributes["variants"],
        }

    def get_item_info(self, response):
        metadata = dict()

        title = (
            xpath(response.text, "//h1[@class='title']//text()").extract_first().strip()
        )

        description = xpath(
            response.text, "//meta[@name='description']/@content"
        ).extract_first()
        metadata["__description"] = description

        section = xpath(
            response.text, "//div[@class='header']//div[@class='crumb']//text()"
        ).extract()

        properties = xpath(response.text, "//div[@class='properties']//p").extract()

        brand = "Не указан"

        for property in properties:
            title_text = xpath(
                property, "//span[@class='title']//text()"
            ).extract_first()
            value_text = xpath(
                property, "//span[@class='value']//text()"
            ).extract_first()
            metadata[title_text] = value_text
            if "код товара" in title_text.lower():
                rpc = value_text
            elif "бренд" in title_text.lower():
                brand = value_text

        additional_info = (
            re.search(r"(?<=\w{2}\.product=)\{.+?(?=;\w{2}\.similar)", response.text)[0]
            .replace("\r", "")
            .replace("\n", "")
        )
        additional_info = decode(
            re.sub(r"(?<=:)([A-Za-z$_]+)(?=,|\})", r'"\1"', additional_info)
        )

        price_data = self.get_price_data(response, additional_info)

        set_images = {
            picture.get("src") for picture in additional_info.get("images", [])
        }
        main_image = additional_info.get("images", [{}])[0].get("src")
        video = additional_info.get("videoLink")
        variants = int(len(additional_info.get("variants", {})))

        stock = self.get_stock_info(rpc)

        attributes = {
            "title": title,
            "brand": brand,
            "RPC": rpc,
            "metadata": metadata,
            "section": section,
            "stock": stock,
            "assets": {
                "set_images": set_images,
                "main_image": main_image,
                "video": video,
            },
            "variants": variants,
            "price_data": price_data,
        }

        return attributes

    @staticmethod
    def get_stock_info(rpc):
        in_stock = False
        params = {
            "canPickup": "all",
            "inStock": "true",
        }
        url = f"https://api.fix-price.com/buyer/v1/store/balance/{rpc}"

        response = session.get(url=url, params=params)
        if response.status_code != 200:
            return {"in_stock": in_stock}

        stores = response.json()
        total_count = sum(store["count"] for store in stores)
        in_stock = bool(total_count)

        return {"in_stock": in_stock, "count": total_count}

    @staticmethod
    def get_price_data(response, additional_info):
        sale = 0
        regular_price = xpath(
            response.text, '//meta[@itemprop="price"]/@content'
        ).extract_first()
        if not regular_price:
            return {
                "current": "Нет в наличии",
            }

        regular_price = round(float(regular_price), 2)

        try:
            special_price = round(
                float(additional_info.get("specialPrice").get("price")), 2
            )
            sale = round((1 - (special_price / regular_price)) * 100, 2)
        except BaseException:
            special_price = regular_price

        return {
            "current": special_price,
            "original": regular_price,
            "sale_tag": f"Скидка {sale} %",
        }
