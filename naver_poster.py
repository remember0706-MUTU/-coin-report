#!/usr/bin/env python3
"""
naver_poster.py — Playwright 기반 네이버 블로그 자동 발행 모듈

Interface:
    post_to_naver_blog(title, content_html, image_path, tags, cookies) -> str (published URL)

환경:
    - GitHub Actions (Ubuntu) : xvfb-run -a python ... 으로 감싸서 실행
    - 로컬 Windows : headless=False 로 직접 실행 가능
"""

import asyncio
import os
import json
import pyperclip
from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

BLOG_ID = "remember0706"
WRITE_URL = f"https://blog.naver.com/PostWriteForm.naver?blogId={BLOG_ID}"
EXPECTED_URL_FRAGMENT = f"blog.naver.com/{BLOG_ID}"

# 타임아웃 설정 (ms)
NAVIGATION_TIMEOUT = 60_000
SELECTOR_TIMEOUT   = 30_000
PUBLISH_TIMEOUT    = 60_000


async def post_to_naver_blog(
    title: str,
    content_html: str,
    image_path: str,
    tags: list,
    cookies: list,
) -> str:
    """네이버 블로그에 포스트를 발행하고 게시된 URL을 반환합니다.

    Args:
        title:        포스트 제목
        content_html: HTML 본문 (인라인 스타일)
        image_path:   업로드할 차트 이미지 절대 경로 (빈 문자열이면 생략)
        tags:         태그 문자열 리스트  e.g. ["비트코인", "BTC"]
        cookies:      Playwright 쿠키 포맷 dict 리스트
                      [{name, value, domain, path, ...}, ...]

    Returns:
        발행된 포스트 URL  e.g. "https://blog.naver.com/remember0706/123456789"

    Raises:
        ValueError:   쿠키가 비어있거나 만료된 경우
        RuntimeError: 셀렉터를 찾지 못하거나 발행 URL 확인 실패 시
    """
    if not cookies:
        raise ValueError("cookies가 비어 있습니다. NAVER_COOKIES Secret을 확인하세요.")

    # GitHub Actions(Linux)에서는 반드시 xvfb-run -a 로 감싸서 실행해야 합니다.
    # DISPLAY 환경변수가 없는데 headless=False 이면 Playwright가 크래시합니다.
    is_linux = os.name != 'nt'
    has_display = bool(os.environ.get('DISPLAY'))
    if is_linux and not has_display:
        raise RuntimeError(
            "DISPLAY 환경변수가 없습니다. "
            "GitHub Actions 워크플로우에서 'xvfb-run -a python blog_main.py' 로 실행하세요."
        )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,   # Xvfb 환경에서는 headless=False 로도 정상 동작
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
        )
        context.set_default_timeout(SELECTOR_TIMEOUT)

        # ── 1. 쿠키 주입 ─────────────────────────────────────────────────
        await context.add_cookies(cookies)

        page = await context.new_page()

        # ── 2. 쓰기 페이지 이동 ──────────────────────────────────────────
        try:
            await page.goto(WRITE_URL, wait_until="domcontentloaded",
                            timeout=NAVIGATION_TIMEOUT)
        except Exception as exc:
            raise RuntimeError(f"쓰기 페이지 이동 실패: {exc}") from exc

        # 로그인 여부 확인: 로그인 페이지로 리디렉션되면 쿠키 만료
        if "nid.naver.com" in page.url or "login" in page.url.lower():
            raise ValueError(
                f"쿠키가 만료되었거나 로그인이 필요합니다. 현재 URL: {page.url}"
            )

        # PostWrite 프레임 대기 — Smart Editor 3.0 은 iframe 안에 있음
        # NOTE: Naver는 iframe 구조를 자주 바꿉니다.
        #       아래 frame locator 패턴이 맞지 않으면 page.frames 로 직접 탐색하세요.
        try:
            await page.wait_for_selector(
                "iframe#mainFrame, iframe[name='mainFrame'], #mainFrame",
                timeout=SELECTOR_TIMEOUT,
            )
        except PWTimeoutError:
            # mainFrame 이 없을 경우 현재 페이지 자체가 에디터일 수 있음
            pass

        # ── 3. iframe 획득 (mainFrame or 현재 페이지) ─────────────────────
        main_frame = page
        try:
            frame_el = await page.query_selector("iframe#mainFrame, iframe[name='mainFrame']")
            if frame_el:
                main_frame = await frame_el.content_frame()
        except Exception:
            pass  # frame 없으면 page 직접 사용

        # ── 4. 제목 입력 ─────────────────────────────────────────────────
        # NOTE: 셀렉터는 Naver 에디터 버전에 따라 다를 수 있습니다.
        #       주로 사용되는 셀렉터 후보: .se-title-input, #subject, input[name=subject]
        title_selectors = [
            ".se-title-input",              # Smart Editor ONE (최신)
            "input.input_title",            # 구형 Smart Editor 3.0
            "input[name='subject']",        # 레거시
            "#subject",
        ]
        title_filled = False
        for sel in title_selectors:
            try:
                el = await main_frame.wait_for_selector(sel, timeout=5_000)
                await el.click()
                await el.fill(title)
                title_filled = True
                break
            except PWTimeoutError:
                continue

        if not title_filled:
            raise RuntimeError(
                "제목 입력란 셀렉터를 찾지 못했습니다. "
                f"현재 URL: {page.url} — 셀렉터를 수동으로 확인하세요."
            )

        # ── 5. 이미지 업로드 ─────────────────────────────────────────────
        if image_path and os.path.isfile(image_path):
            # Smart Editor 이미지 삽입 버튼 클릭 → 파일 선택 다이얼로그
            # NOTE: 버튼 셀렉터는 에디터 버전마다 다릅니다.
            #       .se-toolbar-item-image / .se-btn-image / button[data-type='image'] 등
            image_btn_selectors = [
                "button.se-toolbar-item-image",   # Smart Editor ONE
                ".se-btn-image",
                "button[data-type='image']",
                ".img_btn",                        # 구형 에디터
            ]
            btn_found = False
            for sel in image_btn_selectors:
                try:
                    btn = await main_frame.wait_for_selector(sel, timeout=5_000)
                    async with context.expect_file_chooser() as fc_info:
                        await btn.click()
                    file_chooser = await fc_info.value
                    await file_chooser.set_files(image_path)
                    btn_found = True
                    # 이미지 업로드 완료 대기 (네트워크 안정화)
                    await page.wait_for_load_state("networkidle", timeout=30_000)
                    break
                except PWTimeoutError:
                    continue
                except Exception as exc:
                    # 파일 다이얼로그 실패 시 경고만 출력하고 계속 진행
                    print(f"[naver_poster] 이미지 업로드 경고: {exc}")
                    btn_found = True
                    break

            if not btn_found:
                # 이미지 버튼을 찾지 못해도 본문 발행은 계속 진행
                print("[naver_poster] 이미지 업로드 버튼을 찾지 못했습니다. 본문만 발행합니다.")
        else:
            if image_path:
                print(f"[naver_poster] 이미지 파일이 없습니다: {image_path}")

        # ── 6. 본문 HTML 클립보드 복사 → Smart Editor에 붙여넣기 ──────────
        # Smart Editor 본문 영역 셀렉터 후보
        # NOTE: contenteditable 영역을 직접 클릭한 뒤 Ctrl+V
        body_selectors = [
            ".se-component.se-text .se-placeholder",   # Smart Editor ONE — 빈 상태
            ".se-component-content p",                  # Smart Editor ONE — 내용 있을 때
            "div.se-main-container",                    # Smart Editor ONE 컨테이너
            "#smarteditor_body",                        # 구형 Smart Editor 3.0 iframe 내부
            ".se_doc_viewer",                           # 구형
        ]

        # 클립보드에 HTML 복사
        pyperclip.copy(content_html)

        body_found = False
        for sel in body_selectors:
            try:
                body_el = await main_frame.wait_for_selector(sel, timeout=5_000)
                await body_el.click()
                await page.keyboard.press("Control+v")
                body_found = True
                break
            except PWTimeoutError:
                continue

        if not body_found:
            # fallback: Tab 키로 제목→본문 포커스 이동 후 붙여넣기
            print("[naver_poster] 본문 셀렉터를 찾지 못해 Tab 키 fallback을 시도합니다.")
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.5)
            await page.keyboard.press("Control+v")

        # 붙여넣기 후 짧게 대기 (에디터 렌더링)
        await asyncio.sleep(1.0)

        # ── 7. 태그 입력 ─────────────────────────────────────────────────
        # NOTE: 태그 입력란 셀렉터 후보
        #       .se-tag-input__input / input.tag_input / #tag
        tag_input_selectors = [
            ".se-tag-input__input",     # Smart Editor ONE
            "input.tag_input",          # 구형
            "input[placeholder*='태그']",
            "#tag",
        ]
        for sel in tag_input_selectors:
            try:
                tag_el = await main_frame.wait_for_selector(sel, timeout=5_000)
                for tag in tags:
                    await tag_el.click()
                    await tag_el.fill(tag)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(0.3)
                break
            except PWTimeoutError:
                continue
        else:
            print("[naver_poster] 태그 입력란을 찾지 못했습니다. 태그 없이 발행합니다.")

        # ── 8. 발행 버튼 클릭 ─────────────────────────────────────────────
        # NOTE: 발행 버튼 셀렉터 후보
        #       .publish_btn / button[class*='publish'] / #publish_btn 등
        publish_selectors = [
            "button.publish_btn",                        # Smart Editor ONE
            "button[class*='publish']",
            "a.btn_publish",                             # 일부 버전
            "#publish_btn",
            "button:has-text('발행')",                   # 텍스트 기반 fallback
            "button:has-text('등록')",
        ]
        published = False
        for sel in publish_selectors:
            try:
                btn = await main_frame.wait_for_selector(sel, timeout=5_000)
                await btn.click()
                published = True
                break
            except PWTimeoutError:
                continue

        if not published:
            raise RuntimeError(
                "발행 버튼을 찾지 못했습니다. 셀렉터를 수동으로 확인하세요."
            )

        # ── 9. 발행 확인 팝업 처리 (있을 경우) ───────────────────────────
        # 일부 에디터 버전에서 "공개 발행" 확인 팝업이 뜸
        confirm_selectors = [
            "button:has-text('확인')",
            "button.btn_confirm",
            ".btn_ok",
        ]
        for sel in confirm_selectors:
            try:
                confirm_btn = await page.wait_for_selector(sel, timeout=5_000)
                await confirm_btn.click()
                break
            except PWTimeoutError:
                continue

        # ── 10. 발행 후 URL 변경 대기 ────────────────────────────────────
        try:
            await page.wait_for_url(
                f"**/{BLOG_ID}/**",
                timeout=PUBLISH_TIMEOUT,
            )
        except PWTimeoutError:
            # URL 변경이 없을 경우 현재 URL로 검증
            pass

        published_url = page.url

        # ── 11. URL 검증 ─────────────────────────────────────────────────
        if EXPECTED_URL_FRAGMENT not in published_url:
            raise RuntimeError(
                f"발행 후 URL이 예상과 다릅니다: {published_url}\n"
                f"예상: blog.naver.com/{BLOG_ID} 포함"
            )

        await browser.close()
        return published_url


# ── CLI 테스트 진입점 ────────────────────────────────────────────────────────
async def _main():
    """로컬 테스트용. NAVER_COOKIES 환경변수에서 쿠키를 읽어 발행을 테스트합니다."""
    raw_cookies = os.environ.get("NAVER_COOKIES", "")
    if not raw_cookies:
        print("ERROR: NAVER_COOKIES 환경변수가 설정되지 않았습니다.")
        return

    cookies = json.loads(raw_cookies)

    title = "[테스트] 네이버 블로그 자동 발행 테스트"
    content_html = (
        "<h2>자동 발행 테스트</h2>"
        "<p>이 포스트는 <strong>naver_poster.py</strong>의 테스트 발행입니다.</p>"
    )
    image_path = ""  # 테스트 시 이미지 없이 진행
    tags = ["테스트", "자동발행", "비트코인"]

    url = await post_to_naver_blog(
        title=title,
        content_html=content_html,
        image_path=image_path,
        tags=tags,
        cookies=cookies,
    )
    print(f"\n발행 완료: {url}")


if __name__ == "__main__":
    asyncio.run(_main())
