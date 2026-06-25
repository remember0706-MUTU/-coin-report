#!/usr/bin/env python3
"""
최초 1회 로컬 실행 전용 — 네이버 쿠키 추출 스크립트
GitHub Actions에서 실행하지 마세요.

사용법:
  python extract_naver_cookies.py

출력된 JSON을 GitHub Secrets > NAVER_COOKIES 에 등록하세요.
"""
import json
import asyncio
from playwright.async_api import async_playwright

WAIT_SECONDS = 90


async def extract_cookies():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        print("네이버 로그인 페이지를 엽니다...")
        await page.goto("https://nid.naver.com/nidlogin.login", wait_until="networkidle")

        print(f"\n{WAIT_SECONDS}초 안에 로그인을 완료해 주세요 (아이디/비밀번호 입력 후 로그인 버튼 클릭)...")
        print("로그인 완료 후 자동으로 쿠키를 추출합니다.\n")

        for remaining in range(WAIT_SECONDS, 0, -5):
            await asyncio.sleep(5)
            current_url = page.url
            if "nid.naver.com" not in current_url:
                print("로그인 감지! 쿠키 추출 중...")
                break
            print(f"  대기 중... {remaining}초 남음")

        cookies = await context.cookies()
        await browser.close()

        print("\n" + "=" * 60)
        print("아래 JSON을 GitHub Secrets > NAVER_COOKIES 값으로 등록하세요:")
        print("=" * 60)
        print(json.dumps(cookies, indent=2, ensure_ascii=False))
        print("=" * 60)
        print(f"\n총 {len(cookies)}개 쿠키 추출 완료.")


if __name__ == "__main__":
    asyncio.run(extract_cookies())
