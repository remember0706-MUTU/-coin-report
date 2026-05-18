#!/usr/bin/env python3
"""
BTC 시황 + ICT 구조 분석 통합 텔레그램 리포트 생성기
- CoinGecko / Alternative.me / 업비트: 실시간 시황 데이터
- Binance: BTC 4H / 1H OHLCV 데이터
- Claude Sonnet: 통합 분석 + 텔레그램용 리포트 작성
- output_ict/ 저장 + 텔레그램 채널 발송
"""

import os
import sys
import io
import requests
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import anthropic

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# ── 설정 ──────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY   = os.environ.get('ANTHROPIC_API_KEY', '')
TELEGRAM_BOT_TOKEN  = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHANNEL_ID = os.environ.get('TELEGRAM_CHANNEL_ID', '')

try:
    import config as _cfg
    if not ANTHROPIC_API_KEY:
        ANTHROPIC_API_KEY = getattr(_cfg, 'CLAUDE_API_KEY', '')
    if not TELEGRAM_BOT_TOKEN:
        TELEGRAM_BOT_TOKEN = getattr(_cfg, 'TELEGRAM_BOT_TOKEN', '')
    if not TELEGRAM_CHANNEL_ID:
        TELEGRAM_CHANNEL_ID = getattr(_cfg, 'TELEGRAM_CHANNEL_ID', '')
except ImportError:
    pass

KST        = timezone(timedelta(hours=9))
BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / 'output_ict'
GUIDELINE  = BASE_DIR / 'combined_telegram_guideline.txt'
SYMBOL     = "BTCUSDT"
COIN_IDS   = "bitcoin,ethereum,solana,ripple,binancecoin,dogecoin"


# ── 시황 데이터 수집 (CoinGecko / Alternative.me / 업비트) ────────────

def fetch(url, params=None, timeout=15, label=""):
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"  [{label}] 재시도 {attempt+1}/3: {e}")
            if attempt < 2:
                time.sleep(5)
    return None


def get_market_data() -> dict:
    print("📡 코인 시장 데이터 수집 중...")
    coins_raw = fetch(
        "https://api.coingecko.com/api/v3/coins/markets",
        params={"vs_currency": "usd", "ids": COIN_IDS, "order": "market_cap_desc",
                "price_change_percentage": "24h,7d"},
        label="코인가격"
    )
    coins = {c["id"]: c for c in (coins_raw or [])}

    krw_raw = fetch(
        "https://api.coingecko.com/api/v3/simple/price",
        params={"ids": "bitcoin,ethereum", "vs_currencies": "krw"},
        label="KRW가격"
    )
    return {"coins": coins, "krw": krw_raw or {}}


def get_fear_greed() -> dict:
    print("😨 공포탐욕지수 수집 중...")
    data = fetch("https://api.alternative.me/fng/", label="공포탐욕지수")
    if data and "data" in data:
        item = data["data"][0]
        return {"value": int(item["value"]), "label": item["value_classification"]}
    return {"value": 50, "label": "Neutral"}


def get_global_data() -> dict:
    print("🌐 글로벌 시장 데이터 수집 중...")
    data = fetch("https://api.coingecko.com/api/v3/global", label="글로벌")
    if data and "data" in data:
        d = data["data"]
        return {
            "total_market_cap_usd": d["total_market_cap"].get("usd", 0),
            "market_cap_change_24h": d.get("market_cap_change_percentage_24h_usd", 0),
            "btc_dominance": d["market_cap_percentage"].get("btc", 0),
            "eth_dominance": d["market_cap_percentage"].get("eth", 0),
        }
    return {}


def get_kimchi_premium(btc_krw_cg: int) -> float:
    print("🌏 김치프리미엄 계산 중...")
    data = fetch("https://api.upbit.com/v1/ticker", params={"markets": "KRW-BTC"}, label="업비트")
    if data and btc_krw_cg:
        upbit_krw = data[0]["trade_price"]
        premium = (upbit_krw - btc_krw_cg) / btc_krw_cg * 100
        print(f"  업비트: ₩{upbit_krw:,.0f} | CoinGecko: ₩{btc_krw_cg:,.0f} | 김프: {premium:+.2f}%")
        return round(premium, 2)
    return 0.0


def build_market_summary(market_data, fear_greed, global_data, kimchi) -> str:
    coins = market_data.get("coins", {})
    krw   = market_data.get("krw", {})

    def c(cid): return coins.get(cid, {})
    def pct(cid, key): return c(cid).get(key, 0) or 0

    fear_kr = {"Extreme Fear": "극도의 공포", "Fear": "공포",
               "Neutral": "중립", "Greed": "탐욕",
               "Extreme Greed": "극도의 탐욕"}.get(fear_greed["label"], fear_greed["label"])

    total_cap_t = global_data.get("total_market_cap_usd", 0) / 1e12

    return f"""=== 실시간 시장 데이터 ===
BTC: ${c('bitcoin').get('current_price',0):,.0f} / ₩{krw.get('bitcoin',{}).get('krw',0)//10000:,.0f}만원
BTC 24h: {pct('bitcoin','price_change_percentage_24h'):+.2f}% | 7d: {pct('bitcoin','price_change_percentage_7d_in_currency'):+.2f}%
ETH: ${c('ethereum').get('current_price',0):,.0f} / ₩{krw.get('ethereum',{}).get('krw',0)//10000:,.0f}만원
ETH 24h: {pct('ethereum','price_change_percentage_24h'):+.2f}% | 7d: {pct('ethereum','price_change_percentage_7d_in_currency'):+.2f}%
SOL: ${c('solana').get('current_price',0):.2f} | 24h: {pct('solana','price_change_percentage_24h'):+.2f}%
XRP: ${c('ripple').get('current_price',0):.4f} | 24h: {pct('ripple','price_change_percentage_24h'):+.2f}%
BNB: ${c('binancecoin').get('current_price',0):.2f} | 24h: {pct('binancecoin','price_change_percentage_24h'):+.2f}%
DOGE: ${c('dogecoin').get('current_price',0):.6f} | 24h: {pct('dogecoin','price_change_percentage_24h'):+.2f}%
전체 시총: ${total_cap_t:.2f}조 달러 ({global_data.get('market_cap_change_24h',0):+.2f}%)
BTC 도미넌스: {global_data.get('btc_dominance',0):.1f}%
ETH 도미넌스: {global_data.get('eth_dominance',0):.1f}%
공포탐욕지수: {fear_greed['value']}/100 ({fear_kr})
김치프리미엄: {kimchi:+.2f}%"""


# ── OHLCV 데이터 수집 (Binance) ──────────────────────────────────────

def fetch_ohlcv(symbol: str, interval: str, limit: int = 100) -> list:
    aggregate = {"4h": 4, "1h": 1}.get(interval, 1)
    url = "https://min-api.cryptocompare.com/data/v2/histohour"
    params = {"fsym": "BTC", "tsym": "USD", "limit": limit, "aggregate": aggregate}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=15)
            r.raise_for_status()
            candles = r.json().get("Data", {}).get("Data", [])
            return [{
                "time":   datetime.fromtimestamp(c["time"], tz=KST).strftime('%Y-%m-%d %H:%M'),
                "open":   float(c["open"]), "high": float(c["high"]),
                "low":    float(c["low"]),  "close": float(c["close"]),
                "volume": float(c["volumefrom"]),
            } for c in candles]
        except Exception as e:
            print(f"  [{interval}] 재시도 {attempt+1}/3: {e}")
            if attempt < 2:
                time.sleep(5)
    return []


def format_ohlcv(candles: list, label: str, n: int = 60) -> str:
    rows = [f"=== {label} — 최근 {min(n, len(candles))}개 캔들 ===",
            "시간(KST)         시가      고가      저가      종가      거래량"]
    for c in candles[-n:]:
        rows.append(f"{c['time']}  {c['open']:>9.0f}  {c['high']:>9.0f}  "
                    f"{c['low']:>9.0f}  {c['close']:>9.0f}  {c['volume']:>10.2f}")
    return "\n".join(rows)


# ── 통합 리포트 생성 ──────────────────────────────────────────────────

def generate_report(market_summary: str, ohlcv_4h: list, ohlcv_1h: list) -> str:
    print("✍️  Claude Sonnet으로 통합 리포트 생성 중...")

    guideline = GUIDELINE.read_text(encoding='utf-8') if GUIDELINE.exists() else ""
    now_str   = datetime.now(KST).strftime('%Y.%m.%d %H:%M')

    system_prompt = f"""당신은 암호화폐 시장 분석가이자 ICT/SMC 차트 분석 교육 콘텐츠 작성자입니다.

=== 리포트 작성 지침 ===
{guideline}

추가 지시사항:
- 현재 날짜/시간: {now_str} KST
- 시황 데이터(BTC/ETH 가격, 공포탐욕, 김치프리미엄)와 OHLCV 차트 데이터를 모두 활용하세요
- 초보자도 이해할 수 있는 친근한 말투 + ICT/SMC 전문 분석을 자연스럽게 융합하세요
- 공포탐욕지수와 김치프리미엄을 ICT 유동성 관점으로 해석하세요
- 출력은 순수 텍스트만 (HTML 태그, 마크다운 절대 금지)"""

    user_message = f"""{market_summary}

{format_ohlcv(ohlcv_4h, '4시간봉 (4H)', n=60)}

{format_ohlcv(ohlcv_1h, '1시간봉 (1H)', n=60)}

위 데이터를 바탕으로 지침의 구조에 따라 통합 텔레그램 리포트를 작성해주세요.
"""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=5000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}]
    )
    return msg.content[0].text


# ── 저장 + 텔레그램 발송 ─────────────────────────────────────────────

def save_report(content: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    filename  = datetime.now(KST).strftime('%Y%m%d_%H%M') + '_combined_report.txt'
    filepath  = OUTPUT_DIR / filename
    filepath.write_text(content, encoding='utf-8')
    return filepath


FOOTER = "🔴 𝗽𝗿𝗶𝗰𝗲 𝗶𝘀 𝗮 𝘀𝘁𝗼𝗿𝘆 𝗮𝗻𝗱 𝗹𝗶𝗾𝘂𝗶𝗱𝗶𝘁𝘆 𝗶𝘀 𝘁𝗵𝗲 𝗺𝗮𝗽 🔴\n📝 https://blog.naver.com/remember0706"

def send_telegram(content: str):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        print("  ⚠️  텔레그램 설정 없음")
        return
    print("✈️  텔레그램 채널 발송 중...")
    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunks  = [content[i:i+4000] for i in range(0, len(content), 4000)]
    for i, chunk in enumerate(chunks):
        result = requests.post(api_url, json={"chat_id": TELEGRAM_CHANNEL_ID, "text": chunk}, timeout=15).json()
        if result.get("ok"):
            print(f"  ✅ 텔레그램 전송 완료! ({i+1}/{len(chunks)})")
        else:
            print(f"  ⚠️  전송 실패: {result}")
    # 푸터 별도 메시지로 항상 마지막에 전송
    requests.post(api_url, json={"chat_id": TELEGRAM_CHANNEL_ID, "text": FOOTER}, timeout=15)


# ── 메인 ─────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*55)
    print("  📊 BTC 시황 + ICT 구조 분석 통합 리포트")
    print("="*55 + "\n")

    # 시황 데이터
    market_data = get_market_data()
    fear_greed  = get_fear_greed()
    global_data = get_global_data()
    btc_krw     = market_data.get("krw", {}).get("bitcoin", {}).get("krw", 0)
    kimchi      = get_kimchi_premium(btc_krw) if btc_krw else 0.0
    market_summary = build_market_summary(market_data, fear_greed, global_data, kimchi)

    # OHLCV 데이터
    print("📡 Binance OHLCV 데이터 수집 중...")
    ohlcv_4h = fetch_ohlcv(SYMBOL, "4h", limit=100)
    ohlcv_1h = fetch_ohlcv(SYMBOL, "1h", limit=100)

    if not ohlcv_4h or not ohlcv_1h:
        print("❌ OHLCV 데이터 수집 실패")
        return

    btc_price = ohlcv_1h[-1]['close']
    print(f"  ✅ 4H {len(ohlcv_4h)}개 / 1H {len(ohlcv_1h)}개 | BTC ${btc_price:,.0f}")

    # 리포트 생성
    report   = generate_report(market_summary, ohlcv_4h, ohlcv_1h)
    filepath = save_report(report)

    print(f"\n{'='*55}")
    print(f"  ✅ 리포트 저장 완료!")
    print(f"  📁 {filepath}")
    print(f"  📏 글자 수: {len(report)}자")
    print(f"{'='*55}\n")

    send_telegram(report)
    print(f"\n👉 파일 확인: {filepath}")


if __name__ == '__main__':
    main()
