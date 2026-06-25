#!/usr/bin/env python3
"""
blog_main.py — 네이버 블로그 자동 포스팅 오케스트레이터

사용법 (GitHub Actions):
    TIME_SLOT=17 xvfb-run -a python blog_main.py
    TIME_SLOT=21 xvfb-run -a python blog_main.py

사용법 (로컬 테스트, 발행 없이 내용만 확인):
    python blog_main.py --dry-run 17
"""
import asyncio
import json
import os
import sys
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

KST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent
CHART_DIR = BASE_DIR / 'output_ict' / 'charts'


# ── API 키 / 환경 설정 ────────────────────────────────────────────────

def _get_telegram_config():
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    channel = os.environ.get('TELEGRAM_CHANNEL_ID', '')
    if not token or not channel:
        try:
            import config as _cfg
            token = token or getattr(_cfg, 'TELEGRAM_BOT_TOKEN', '')
            channel = channel or getattr(_cfg, 'TELEGRAM_CHANNEL_ID', '')
        except ImportError:
            pass
    return token, channel


def _send_error_telegram(message: str):
    import requests
    token, channel = _get_telegram_config()
    if not token or not channel:
        print(f"[경고] 텔레그램 설정 없음 — 에러 알림 생략: {message}")
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": channel, "text": f"⚠️ 블로그 발행 오류\n{message}"},
            timeout=10,
        )
    except Exception as e:
        print(f"[경고] 텔레그램 전송 실패: {e}")


# ── 시장 데이터 수집 (ict_writer.py 패턴 재사용) ─────────────────────

def _fetch_ohlcv(hours: int) -> list:
    """Binance data-api에서 4H OHLCV 수집. hours에 맞는 캔들 수 반환."""
    import requests, time
    n_candles = max(hours // 4, 25)
    url = "https://data-api.binance.vision/api/v3/klines"
    params = {"symbol": "BTCUSDT", "interval": "4h", "limit": n_candles}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            return [
                {
                    "time": datetime.fromtimestamp(c[0] / 1000, tz=KST).strftime('%Y-%m-%d %H:%M'),
                    "open": float(c[1]), "high": float(c[2]),
                    "low": float(c[3]),  "close": float(c[4]),
                    "volume": float(c[5]),
                }
                for c in r.json()
            ]
        except Exception as e:
            print(f"  [OHLCV] 재시도 {attempt+1}/3: {e}")
            if attempt < 2:
                time.sleep(5)
    return []


def _get_current_price_and_change(ohlcv_data: list) -> tuple:
    if not ohlcv_data:
        return 0.0, 0.0
    current = ohlcv_data[-1]['close']
    day_ago_idx = max(0, len(ohlcv_data) - 6)  # ~24h ago (6 × 4H = 24H)
    day_ago_price = ohlcv_data[day_ago_idx]['close']
    change_pct = ((current - day_ago_price) / day_ago_price * 100) if day_ago_price else 0.0
    return current, round(change_pct, 2)


# ── 쿠키 로드 ─────────────────────────────────────────────────────────

def _load_naver_cookies() -> list:
    raw = os.environ.get('NAVER_COOKIES', '').strip()
    if not raw:
        raise RuntimeError(
            "NAVER_COOKIES 환경변수가 없습니다. "
            "extract_naver_cookies.py 로 쿠키를 추출하고 GitHub Secrets에 등록해 주세요."
        )
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"NAVER_COOKIES JSON 파싱 실패: {e}") from e


# ── 메인 실행 ─────────────────────────────────────────────────────────

async def run(time_slot: str, dry_run: bool = False):
    now = datetime.now(KST)
    print(f"\n{'='*55}")
    print(f"  📝 네이버 블로그 자동 포스팅 — time_slot={time_slot}")
    print(f"  {now.strftime('%Y.%m.%d %H:%M')} KST")
    print(f"{'='*55}\n")

    # 1. 쿠키 확인 (dry-run이 아닐 때만 필수)
    cookies = []
    if not dry_run:
        try:
            cookies = _load_naver_cookies()
            print(f"✅ 쿠키 로드 완료 ({len(cookies)}개)")
        except RuntimeError as e:
            _send_error_telegram(str(e))
            print(f"❌ {e}")
            return

    # 2. OHLCV 데이터 수집
    hours = 48 if time_slot == "17" else 72
    print(f"📡 OHLCV 데이터 수집 중 ({hours}시간)...")
    ohlcv = _fetch_ohlcv(hours)
    if not ohlcv:
        msg = f"OHLCV 데이터 수집 실패 (time_slot={time_slot})"
        _send_error_telegram(msg)
        print(f"❌ {msg}")
        return

    current_price, change_pct = _get_current_price_and_change(ohlcv)
    print(f"  ✅ {len(ohlcv)}개 캔들 | BTC ${current_price:,.0f} ({change_pct:+.2f}%)")

    # 3. 차트 생성
    print("📊 차트 이미지 생성 중...")
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    chart_path = str(CHART_DIR / f"{now.strftime('%Y%m%d_%H%M')}_chart.png")
    try:
        from chart_generator import generate_chart
        generate_chart(ohlcv, hours, chart_path)
        print(f"  ✅ 차트 저장: {chart_path}")
    except Exception as e:
        msg = f"차트 생성 실패: {e}"
        _send_error_telegram(msg)
        print(f"❌ {msg}")
        return

    # 4. 블로그 콘텐츠 생성
    print("✍️  블로그 콘텐츠 생성 중...")
    try:
        if time_slot == "17":
            from blog_writer_afternoon import generate_afternoon_post
            post = generate_afternoon_post(ohlcv, current_price, change_pct)
        else:  # "21"
            from news_fetcher import fetch_btc_news
            from blog_writer_evening import generate_evening_post
            news = fetch_btc_news(max_items=5)
            post = generate_evening_post(ohlcv, current_price, change_pct, news)
    except Exception as e:
        msg = f"콘텐츠 생성 실패: {e}"
        _send_error_telegram(msg)
        print(f"❌ {msg}")
        return

    print(f"  ✅ 제목: {post['title']}")
    print(f"  ✅ 본문: {len(post['content'])}자")

    if dry_run:
        print("\n[DRY-RUN] 발행 없이 종료합니다.")
        print(f"제목: {post['title']}")
        print(f"본문 앞부분:\n{post['content'][:300]}...")
        return

    # 5. 네이버 블로그 발행
    print("🚀 네이버 블로그 발행 중...")
    try:
        from naver_poster import post_to_naver_blog
        url = await post_to_naver_blog(
            title=post['title'],
            content_html=post['content'],
            image_path=chart_path,
            tags=post['tags'],
            cookies=cookies,
        )
        print(f"\n{'='*55}")
        print(f"  ✅ 발행 완료!")
        print(f"  🔗 {url}")
        print(f"{'='*55}\n")
    except Exception as e:
        msg = f"네이버 블로그 발행 실패 (time_slot={time_slot}): {e}"
        _send_error_telegram(msg)
        print(f"❌ {msg}")


def main():
    # time_slot: 환경변수 > CLI 인자 순서로 읽기
    time_slot = os.environ.get('TIME_SLOT', '').strip()
    dry_run = False

    args = sys.argv[1:]
    if '--dry-run' in args:
        dry_run = True
        args = [a for a in args if a != '--dry-run']
    if args and not time_slot:
        time_slot = args[0]

    if time_slot not in ('17', '21'):
        print(f"사용법: TIME_SLOT=17 python blog_main.py  또는  python blog_main.py --dry-run 17")
        print(f"  time_slot은 '17' 또는 '21' 이어야 합니다. (받은 값: '{time_slot}')")
        sys.exit(1)

    asyncio.run(run(time_slot, dry_run=dry_run))


if __name__ == '__main__':
    main()
