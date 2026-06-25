#!/usr/bin/env python3
import os
from datetime import datetime, timezone, timedelta
import anthropic

KST = timezone(timedelta(hours=9))

DISCLAIMER = (
    '<div style="background:#FFF8E1;border-left:4px solid #FFA726;'
    'padding:12px 16px;margin-top:2rem;font-size:13px;color:#795548;'
    'border-radius:0 4px 4px 0;">'
    '⚠️ 본 콘텐츠는 ICT/SMC 차트 분석 방법론을 교육 목적으로 작성한 자료이며, '
    '투자 권유·매매 신호·금융 자문이 아닙니다. '
    '모든 투자 결정은 본인의 독립적 판단과 책임 하에 이루어져야 합니다.'
    '</div>'
)


def _get_api_key() -> str:
    key = os.environ.get('ANTHROPIC_API_KEY', '')
    if not key:
        try:
            import config as _cfg
            key = getattr(_cfg, 'CLAUDE_API_KEY', '')
        except ImportError:
            pass
    return key


def generate_evening_post(
    ohlcv_data: list,
    current_price: float,
    change_pct: float,
    news_list: list,
) -> dict:
    """21시용 하루 마감 종합 분석 블로그 포스트 생성.

    Args:
        ohlcv_data: 4H OHLCV 데이터 리스트 (fetch_ohlcv 반환값)
        current_price: 현재 BTC 가격 (USD)
        change_pct: 24h 변동률 (%)
        news_list: fetch_btc_news 반환값

    Returns:
        {"title": str, "content": str(HTML), "tags": list}
    """
    now = datetime.now(KST)
    date_str = now.strftime('%m/%d')

    recent = ohlcv_data[-18:] if len(ohlcv_data) >= 18 else ohlcv_data
    day_high = max(c['high'] for c in recent)
    day_low = min(c['low'] for c in recent)
    day_open = recent[0]['open'] if recent else current_price

    ohlcv_text = "\n".join(
        f"  {c['time']}  O:{c['open']:,.0f}  H:{c['high']:,.0f}  L:{c['low']:,.0f}  C:{c['close']:,.0f}"
        for c in recent[-10:]
    )

    news_text = "\n".join(
        f"  [{n['published_at']}] {n['title']}"
        for n in (news_list[:3] if news_list else [])
    ) or "  (뉴스 데이터 없음)"

    prompt = f"""현재 시각: {now.strftime('%Y.%m.%d %H:%M')} KST
BTCUSDT 현재가: ${current_price:,.0f} (24h {change_pct:+.2f}%)
당일 시가: ${day_open:,.0f} / 고가: ${day_high:,.0f} / 저가: ${day_low:,.0f}

최근 4H 캔들 (72시간):
{ohlcv_text}

오늘의 주요 뉴스:
{news_text}

위 데이터를 바탕으로 네이버 블로그용 하루 마감 종합 분석 글을 작성해주세요.

[규칙]
- 첫 줄: 제목만 출력 → [{date_str}] 비트코인 일일 마감 분석 | ICT·SMC 구조 + 내일 전망
- 두 번째 줄부터: HTML 본문 (인라인 스타일만, 외부 CSS·JS 없음)
- 코드블록(```html) 없이 바로 출력
- 1,500~2,000자 분량
- 초보자도 이해할 수 있는 친근한 한국어

[구성 — 반드시 이 순서로]
1. 당일 가격 흐름 요약 (시가·고가·저가·현재가, 주요 움직임)
2. ICT·SMC 핵심 구조 분석 (Order Block, Fair Value Gap, Liquidity 등 발견된 것 위주)
3. 오늘의 뉴스 이슈 (제공된 뉴스 2~3개 요약·해설)
4. 내일 주목 구간 및 시나리오 (강세/약세 분기점)

[스타일 참고]
- 섹션 구분은 h2 태그, 본문은 p 태그
- 주요 수치는 <strong> 강조
- 배경색은 흰색/밝은 배경 사용 (어두운 테마 피함)"""

    client = anthropic.Anthropic(api_key=_get_api_key())
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=5000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = msg.content[0].text.strip()
    lines = raw.split('\n', 1)
    title = lines[0].strip() if lines else f"[{date_str}] 비트코인 일일 마감 분석 | ICT·SMC 구조 + 내일 전망"
    content_body = lines[1].strip() if len(lines) > 1 else raw
    content = content_body + '\n' + DISCLAIMER

    return {
        "title": title,
        "content": content,
        "tags": ["비트코인", "BTC", "ICT분석", "SMC", "비트코인분석", "코인일일분석"],
    }
