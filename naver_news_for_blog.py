import os
import re
import requests


def fetch_coin_news(count: int = 3) -> list[dict]:
    """Naver News API → [{"title": str, "link": str, "description": str}, ...]
    실패 시 [] 반환 (예외 발생 금지)."""
    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        print("⚠️ NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 없음 — 뉴스 수집 건너뜀")
        return []

    try:
        r = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            params={"query": "비트코인", "display": count, "sort": "date"},
            headers={
                "X-Naver-Client-Id": client_id,
                "X-Naver-Client-Secret": client_secret,
            },
            timeout=10,
        )
        r.raise_for_status()
        items = r.json().get("items", [])
        result = []
        for item in items[:count]:
            result.append({
                "title": _strip_html(item.get("title", "")),
                "link": item.get("link", ""),
                "description": _strip_html(item.get("description", "")),
            })
        print(f"📰 네이버 뉴스 {len(result)}건 수집 완료")
        return result
    except Exception as e:
        print(f"⚠️ 뉴스 수집 실패: {e}")
        return []


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text).strip()
