#!/usr/bin/env python3
"""
네이버 쿠키 수동 갱신 스크립트 — 로컬에서만 실행 (GitHub Actions 아님)

사용법:
    python refresh_naver_cookies.py

실행하면 실제 Chrome 창이 열립니다. 네이버에 직접 로그인(2FA 포함)한 뒤
터미널에서 Enter를 누르면 쿠키가 저장되고 base64 값이 출력됩니다.
출력된 값을 GitHub Secrets → NAVER_COOKIES_JSON 에 붙여넣으세요.
"""

import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

COOKIES_FILE = Path(__file__).parent / "naver_cookies.json"


def main():
    print("=" * 55)
    print(" 🔐 네이버 쿠키 갱신")
    print("=" * 55)
    print("브라우저가 열립니다. 네이버에 로그인(2FA 포함) 후")
    print("이 터미널로 돌아와 Enter를 눌러주세요.\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto("https://nid.naver.com/nidlogin.login")

        input("로그인 완료 후 Enter ▶ ")

        cookies = context.cookies()
        browser.close()

    COOKIES_FILE.write_text(json.dumps(cookies, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✅ 쿠키 저장 완료: {COOKIES_FILE}")
    print(f"   쿠키 수: {len(cookies)}개\n")

    encoded = base64.b64encode(COOKIES_FILE.read_bytes()).decode("utf-8")
    print("=" * 55)
    print(" 아래 값을 GitHub Secrets → NAVER_COOKIES_JSON 에 등록하세요")
    print("=" * 55)
    print(encoded)
    print("=" * 55)


if __name__ == "__main__":
    main()
