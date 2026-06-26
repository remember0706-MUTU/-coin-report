import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import anthropic

KST = timezone(timedelta(hours=9))
GUIDELINE = Path(__file__).parent / "combined_telegram_guideline.txt"


def generate_blog_post(
    market_summary: str,
    ohlcv_4h: list[dict],
    telegram_report: str,
    news_items: list[dict],
    now_kst: str,
) -> dict:
    """Claude Sonnet → {"title": str, "html": str}."""
    date_str = now_kst[:10].replace("-", ".") if "-" in now_kst else now_kst[:10]
    title = f"[{date_str}] BTC 시황 + ICT 구조 분석"

    guideline = GUIDELINE.read_text(encoding="utf-8") if GUIDELINE.exists() else ""

    ohlcv_summary = _summarize_ohlcv(ohlcv_4h)
    news_section_hint = _format_news_hint(news_items)

    system_prompt = f"""당신은 암호화폐 ICT/SMC 분석 교육 블로그 작성자입니다.
네이버 블로그에 게재할 HTML 형식의 포스트를 작성합니다.

=== 교육 콘텐츠 포지셔닝 규칙 (반드시 준수) ===
{guideline}

=== 블로그 작성 추가 규칙 ===
- 출력은 순수 HTML만 (마크다운 금지, doctype/html/body 태그 제외)
- <h2>, <h3>, <p>, <table>, <ul>, <li>, <strong> 태그만 사용
- 스타일 속성 사용 최소화 (네이버 블로그 기본 스타일 존중)
- 한국어로 작성, 1,500~2,500자 분량
- 초보자도 이해할 수 있는 친근한 말투 유지
- 투자 권유, 확신형 표현 절대 금지
- 이미지 <img> 태그 삽입 금지 (이미지는 별도 처리)"""

    user_message = f"""현재 날짜/시간: {now_kst} KST

{market_summary}

{ohlcv_summary}

=== 오늘의 텔레그램 리포트 (참고용) ===
{telegram_report[:2000]}

{news_section_hint}

위 데이터를 바탕으로 네이버 블로그 포스트 HTML을 작성해주세요.

필수 섹션 순서 (생략 금지):
1. <h2>오늘 시장 한 줄 요약</h2> + <p>
2. <h2>📊 시장 현황 스냅샷</h2> + <table> (BTC/ETH 가격, 공포탐욕지수, 김치프리미엄)
3. <h2>🎯 ICT 구조 요약</h2> + <p> (4H/1H 핵심 레벨)
4. <h3>🟢 시나리오 A — 불리시</h3> + <h3>🔴 시나리오 B — 베어리시</h3>
5. <h2>💬 오늘의 코멘트</h2> + <p> (블로그 전용, 대화체, 교육적 인사이트)
{f'6. <h2>📰 관련 뉴스</h2> + <ul> (아래 뉴스 항목 포함)' if news_items else ''}
{len(news_items) + 6 if news_items else 6}. <p><em>⚠️ 이 글은 투자 권유가 아닙니다. ICT 방법론 교육 목적 자료이며, 암호화폐는 고위험 자산입니다.</em></p>

HTML만 출력하세요 (설명 문구 없이).
"""

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    html = msg.content[0].text.strip()

    # 뉴스 섹션이 HTML에 없으면 직접 삽입
    if news_items and "<h2>" in html and "관련 뉴스" not in html:
        html += _build_news_html(news_items)

    # 면책 고지가 없으면 추가
    if "투자 권유가 아닙니다" not in html:
        html += '<p><em>⚠️ 이 글은 투자 권유가 아닙니다. ICT 방법론 교육 목적 자료이며, 암호화폐는 고위험 자산입니다. 모든 투자 결정은 본인의 판단과 책임 하에 이루어져야 합니다.</em></p>'

    return {"title": title, "html": html}


def _summarize_ohlcv(ohlcv_4h: list[dict]) -> str:
    if not ohlcv_4h:
        return ""
    recent = ohlcv_4h[-10:]
    rows = ["=== BTC 4H 최근 10캔들 (close 기준) ==="]
    for c in recent:
        rows.append(f"{c['time']}  ${c['close']:,.0f}")
    return "\n".join(rows)


def _format_news_hint(news_items: list[dict]) -> str:
    if not news_items:
        return ""
    lines = ["=== 관련 뉴스 (블로그에 포함할 것) ==="]
    for i, item in enumerate(news_items, 1):
        lines.append(f"{i}. {item['title']}")
        lines.append(f"   {item['description']}")
        lines.append(f"   링크: {item['link']}")
    return "\n".join(lines)


def _build_news_html(news_items: list[dict]) -> str:
    items_html = "".join(
        f'<li><a href="{item["link"]}" target="_blank">{item["title"]}</a>'
        f'<br><small>{item["description"]}</small></li>'
        for item in news_items
    )
    return f"<h2>📰 관련 뉴스</h2><ul>{items_html}</ul>"
