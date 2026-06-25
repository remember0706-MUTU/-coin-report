#!/usr/bin/env python3
import requests
import time
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))


def fetch_btc_news(max_items: int = 5) -> list:
    """CryptoCompare에서 BTC 관련 최신 뉴스 수집.

    Returns:
        [{"title": str, "body": str, "url": str, "published_at": str}, ...]
        실패 시 빈 리스트 반환
    """
    url = "https://min-api.cryptocompare.com/data/v2/news/"
    params = {"categories": "BTC", "lang": "EN", "sortOrder": "latest"}

    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            items = r.json().get("Data", [])[:max_items]
            return [
                {
                    "title": item.get("title", ""),
                    "body": item.get("body", "")[:400],
                    "url": item.get("url", ""),
                    "published_at": datetime.fromtimestamp(
                        item.get("published_on", 0), tz=KST
                    ).strftime('%Y-%m-%d %H:%M'),
                }
                for item in items
            ]
        except Exception as e:
            print(f"  [뉴스] 재시도 {attempt + 1}/3: {e}")
            if attempt < 2:
                time.sleep(3)
    return []
