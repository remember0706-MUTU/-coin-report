#!/usr/bin/env python3
"""
코인 시황 리포트 자동 생성기
- CoinGecko + Alternative.me + 업비트 API로 실시간 데이터 수집
- Claude API로 네이버 블로그용 시황 리포트 생성
- output/YYYYMMDD_coin_report.txt 로 저장
"""

import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import requests
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
import anthropic

# ── 설정 ──────────────────────────────────────────────────────────────
# 환경변수 또는 config.py에서 API 키 읽기
ANTHROPIC_API_KEY = (
    os.environ.get('ANTHROPIC_API_KEY') or
    os.environ.get('CLAUDE_API_KEY') or
    ''
)
KAKAO_REST_API_KEY = ''
KAKAO_ACCESS_TOKEN = ''
KAKAO_REFRESH_TOKEN = ''
TELEGRAM_BOT_TOKEN = ''
TELEGRAM_CHANNEL_ID = ''

try:
    from config import CLAUDE_API_KEY as _cfg_key
    if not ANTHROPIC_API_KEY:
        ANTHROPIC_API_KEY = _cfg_key
except ImportError:
    pass

try:
    import config as _cfg
    KAKAO_REST_API_KEY  = getattr(_cfg, 'KAKAO_REST_API_KEY', '')
    KAKAO_ACCESS_TOKEN  = getattr(_cfg, 'KAKAO_ACCESS_TOKEN', '')
    KAKAO_REFRESH_TOKEN = getattr(_cfg, 'KAKAO_REFRESH_TOKEN', '')
    TELEGRAM_BOT_TOKEN  = getattr(_cfg, 'TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHANNEL_ID = getattr(_cfg, 'TELEGRAM_CHANNEL_ID', '')
except ImportError:
    pass

KST = timezone(timedelta(hours=9))
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / 'output'
PROMPT_FILE = BASE_DIR / 'coin_prompt.txt'

COIN_IDS = "bitcoin,ethereum,solana,ripple,binancecoin,dogecoin"


# ── 데이터 수집 ──────────────────────────────────────────────────────

def fetch(url, params=None, timeout=15, label="") -> dict | list | None:
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
    """CoinGecko: 코인 가격 + 변동률 + KRW"""
    print("📡 코인 시장 데이터 수집 중...")

    coins_raw = fetch(
        "https://api.coingecko.com/api/v3/coins/markets",
        params={
            "vs_currency": "usd",
            "ids": COIN_IDS,
            "order": "market_cap_desc",
            "price_change_percentage": "24h,7d",
        },
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
    """Alternative.me: 공포탐욕지수"""
    print("😨 공포탐욕지수 수집 중...")
    data = fetch("https://api.alternative.me/fng/", label="공포탐욕지수")
    if data and "data" in data:
        item = data["data"][0]
        return {"value": int(item["value"]), "label": item["value_classification"]}
    return {"value": 50, "label": "Neutral"}


def get_global_data() -> dict:
    """CoinGecko: 전체 시총 + 도미넌스"""
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
    """업비트 vs CoinGecko KRW 기준 김치프리미엄"""
    print("🌏 김치프리미엄 계산 중...")
    data = fetch(
        "https://api.upbit.com/v1/ticker",
        params={"markets": "KRW-BTC"},
        label="업비트"
    )
    if data and btc_krw_cg:
        upbit_krw = data[0]["trade_price"]
        premium = (upbit_krw - btc_krw_cg) / btc_krw_cg * 100
        print(f"  업비트: ₩{upbit_krw:,.0f} | CoinGecko: ₩{btc_krw_cg:,.0f} | 김프: {premium:+.2f}%")
        return round(premium, 2)
    return 0.0


# ── 리포트 생성 ──────────────────────────────────────────────────────

def build_data_summary(market_data: dict, fear_greed: dict, global_data: dict, kimchi: float) -> str:
    now_kst = datetime.now(KST)
    date_str = now_kst.strftime('%Y년 %m월 %d일 %H:%M')

    coins = market_data.get("coins", {})
    krw   = market_data.get("krw", {})

    def c(coin_id): return coins.get(coin_id, {})
    def pct(coin_id, key): return c(coin_id).get(key, 0) or 0

    fear_label_kr = {
        "Extreme Fear": "극도의 공포",
        "Fear": "공포",
        "Neutral": "중립",
        "Greed": "탐욕",
        "Extreme Greed": "극도의 탐욕",
    }.get(fear_greed["label"], fear_greed["label"])

    total_cap_t = global_data.get("total_market_cap_usd", 0) / 1e12

    return f"""
=== 코인 시장 실시간 데이터 ({date_str} KST) ===

[비트코인 BTC]
현재가: ${c('bitcoin').get('current_price', 0):,.0f} USD / ₩{krw.get('bitcoin', {}).get('krw', 0)//10000:,.0f}만원
24h 변동: {pct('bitcoin','price_change_percentage_24h'):+.2f}%
7d 변동: {pct('bitcoin','price_change_percentage_7d_in_currency'):+.2f}%
시가총액: ${c('bitcoin').get('market_cap', 0)/1e9:.0f}B

[이더리움 ETH]
현재가: ${c('ethereum').get('current_price', 0):,.0f} USD / ₩{krw.get('ethereum', {}).get('krw', 0)//10000:,.0f}만원
24h 변동: {pct('ethereum','price_change_percentage_24h'):+.2f}%
7d 변동: {pct('ethereum','price_change_percentage_7d_in_currency'):+.2f}%

[알트코인]
SOL:  ${c('solana').get('current_price', 0):.2f} | 24h: {pct('solana','price_change_percentage_24h'):+.2f}%
XRP:  ${c('ripple').get('current_price', 0):.4f} | 24h: {pct('ripple','price_change_percentage_24h'):+.2f}%
BNB:  ${c('binancecoin').get('current_price', 0):.2f} | 24h: {pct('binancecoin','price_change_percentage_24h'):+.2f}%
DOGE: ${c('dogecoin').get('current_price', 0):.6f} | 24h: {pct('dogecoin','price_change_percentage_24h'):+.2f}%

[시장 전체]
전체 시총: ${total_cap_t:.2f}조 달러
시총 24h 변동: {global_data.get('market_cap_change_24h', 0):+.2f}%
BTC 도미넌스: {global_data.get('btc_dominance', 0):.1f}%
ETH 도미넌스: {global_data.get('eth_dominance', 0):.1f}%

[감정 지표]
공포탐욕지수: {fear_greed['value']}/100 ({fear_label_kr})
김치프리미엄: {kimchi:+.2f}%
"""


def generate_report(data_summary: str) -> str:
    print("✍️  Claude API로 리포트 생성 중...")

    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY 환경변수를 설정해주세요.")

    system_prompt = PROMPT_FILE.read_text(encoding='utf-8') if PROMPT_FILE.exists() else ""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=3000,
        system=system_prompt,
        messages=[{"role": "user", "content": data_summary}]
    )
    return message.content[0].text


# ── 저장 ─────────────────────────────────────────────────────────────

def save_report(content: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    filename = datetime.now(KST).strftime('%Y%m%d_%H%M') + '_coin_report.txt'
    filepath = OUTPUT_DIR / filename
    filepath.write_text(content, encoding='utf-8')
    return filepath


# ── 카카오톡 발송 ────────────────────────────────────────────────────

def refresh_kakao_token() -> str:
    """리프레시 토큰으로 새 액세스 토큰 발급 후 config.py 갱신"""
    import re
    r = requests.post(
        "https://kauth.kakao.com/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": KAKAO_REST_API_KEY,
            "refresh_token": KAKAO_REFRESH_TOKEN,
        },
        timeout=15
    )
    tokens = r.json()
    new_access = tokens.get("access_token", "")
    if not new_access:
        return ""

    config_path = BASE_DIR / "config.py"
    content = config_path.read_text(encoding='utf-8')
    content = re.sub(
        r'^KAKAO_ACCESS_TOKEN\s*=.*$',
        f'KAKAO_ACCESS_TOKEN = "{new_access}"',
        content, flags=re.MULTILINE
    )
    if "new_refresh_token" in tokens:
        content = re.sub(
            r'^KAKAO_REFRESH_TOKEN\s*=.*$',
            f'KAKAO_REFRESH_TOKEN = "{tokens["new_refresh_token"]}"',
            content, flags=re.MULTILINE
        )
    config_path.write_text(content, encoding='utf-8')
    return new_access


def send_kakao(market_data: dict, fear_greed: dict, kimchi: float, filepath: Path):
    if not KAKAO_ACCESS_TOKEN:
        print("  ⚠️  카카오 토큰 없음 - kakao_setup.py를 먼저 실행하세요")
        return

    print("📱 카카오톡 발송 중...")

    coins = market_data.get("coins", {})
    btc = coins.get("bitcoin", {})
    eth = coins.get("ethereum", {})
    now = datetime.now(KST)

    btc_change = btc.get('price_change_percentage_24h', 0) or 0
    eth_change = eth.get('price_change_percentage_24h', 0) or 0
    fear_emoji = {"Extreme Fear": "😱", "Fear": "😨", "Neutral": "😐",
                  "Greed": "🤑", "Extreme Greed": "🤩"}.get(fear_greed["label"], "😐")

    msg = (
        f"📊 [{now.strftime('%m/%d')} 코인시황]\n"
        f"BTC ${btc.get('current_price',0):,.0f} ({btc_change:+.2f}%)\n"
        f"ETH ${eth.get('current_price',0):,.0f} ({eth_change:+.2f}%)\n"
        f"공포탐욕 {fear_greed['value']}/100 {fear_emoji}\n"
        f"김프 {kimchi:+.2f}%\n"
        f"→ 리포트: {filepath.name}"
    )

    import json
    token = KAKAO_ACCESS_TOKEN

    def _send(access_token):
        template = {
            "object_type": "text",
            "text": msg,
            "link": {
                "web_url": "https://blog.naver.com/remember0706",
                "mobile_web_url": "https://blog.naver.com/remember0706"
            }
        }
        return requests.post(
            "https://kapi.kakao.com/v2/api/talk/memo/default/send",
            headers={"Authorization": f"Bearer {access_token}"},
            data={"template_object": json.dumps(template, ensure_ascii=False)},
            timeout=15
        ).json()

    result = _send(token)

    # 토큰 만료 시 자동 갱신
    if result.get("code") == -401:
        print("  토큰 만료 → 자동 갱신 중...")
        new_token = refresh_kakao_token()
        if new_token:
            result = _send(new_token)

    if result.get("result_code") == 0:
        print("  ✅ 카카오톡 전송 완료!")
    else:
        print(f"  ⚠️  카카오톡 전송 실패: {result}")


# ── 텔레그램 발송 ────────────────────────────────────────────────────

def send_telegram(report: str, market_data: dict, fear_greed: dict, kimchi: float):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        print("  ⚠️  텔레그램 설정 없음 - config.py에 TELEGRAM_BOT_TOKEN/CHANNEL_ID를 입력하세요")
        return

    print("✈️  텔레그램 채널 발송 중...")

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

    def _post(text, parse_mode="Markdown"):
        payload = {
            "chat_id": TELEGRAM_CHANNEL_ID,
            "text": text,
            "parse_mode": parse_mode,
        }
        try:
            r = requests.post(api_url, json=payload, timeout=15)
            return r.json()
        except Exception as e:
            return {"ok": False, "error": str(e)}

    # 전체 리포트를 4096자 단위로 분할 전송 (텔레그램 한 메시지 최대 4096자)
    MAX_LEN = 4096
    chunks = [report[i:i+MAX_LEN] for i in range(0, len(report), MAX_LEN)]

    success = True
    for i, chunk in enumerate(chunks):
        result = _post(chunk)
        if not result.get("ok"):
            # Markdown 파싱 오류 시 plain text로 재시도
            result = _post(chunk, parse_mode=None)
        if result.get("ok"):
            print(f"  ✅ 텔레그램 전송 완료! ({i+1}/{len(chunks)})")
        else:
            print(f"  ⚠️  텔레그램 전송 실패: {result}")
            success = False

    return success


# ── 메인 ─────────────────────────────────────────────────────────────

def main():
    print("\n" + "="*55)
    print("  📊 코인 시황 리포트 자동 생성기")
    print("="*55 + "\n")

    market_data = get_market_data()
    fear_greed  = get_fear_greed()
    global_data = get_global_data()

    btc_krw_cg = market_data.get("krw", {}).get("bitcoin", {}).get("krw", 0)
    kimchi = get_kimchi_premium(btc_krw_cg) if btc_krw_cg else 0.0

    data_summary = build_data_summary(market_data, fear_greed, global_data, kimchi)

    report   = generate_report(data_summary)
    filepath = save_report(report)

    print("\n" + "="*55)
    print(f"  ✅ 리포트 저장 완료!")
    print(f"  📁 {filepath}")
    print("="*55)

    send_kakao(market_data, fear_greed, kimchi, filepath)
    send_telegram(report, market_data, fear_greed, kimchi)

    print(f"\n👉 전체 리포트: {filepath}")


if __name__ == '__main__':
    main()
