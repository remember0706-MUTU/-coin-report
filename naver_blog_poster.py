import base64
import json
import os
import time
from pathlib import Path

COOKIES_FILE = Path(__file__).parent / "naver_cookies.json"
BLOG_ID = "remember0706"
WRITE_URL = f"https://blog.naver.com/PostWrite.naver?blogId={BLOG_ID}"  # 폴백용


def post_to_naver_blog(
    title: str,
    html: str,
    chart_png_path: str | None = None,
) -> str | None:
    """Playwright로 네이버 블로그에 발행. 성공 시 포스트 URL, 실패/쿠키 만료 시 None."""
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    cookies = _load_cookies()
    if cookies is None:
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
        )
        context.add_cookies(cookies)

        try:
            page = context.new_page()

            # 로그인 상태 확인
            page.goto(f"https://blog.naver.com/{BLOG_ID}", wait_until="domcontentloaded", timeout=20000)
            if _is_logged_out(page):
                print("⚠️ 네이버 쿠키 만료 — refresh_naver_cookies.py 실행 후 NAVER_COOKIES_JSON 시크릿 갱신 필요")
                browser.close()
                return None

            print("✅ 네이버 로그인 상태 확인 완료")

            # 블로그 홈에서 글쓰기 버튼 href 추출
            write_url = _find_write_url(page) or WRITE_URL
            print(f"📝 글쓰기 URL: {write_url}")

            # 글 쓰기 페이지 이동
            page.goto(write_url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(5)  # 에디터 JS 초기화 대기

            # 디버그: 프레임 목록 + 스크린샷
            frames_info = [(f.name or "(no name)", f.url[:80]) for f in page.frames]
            print(f"🔍 프레임 목록: {frames_info}")
            try:
                page.screenshot(path="debug_editor.png")
                print("📸 스크린샷 저장: debug_editor.png")
            except Exception:
                pass

            # mainFrame 내부 접근
            post_url = _write_in_frame(page, context, title, html, chart_png_path)

        except PWTimeout as e:
            print(f"⚠️ 타임아웃: {e}")
            post_url = None
        except Exception as e:
            print(f"⚠️ 발행 중 오류: {e}")
            post_url = None
        finally:
            browser.close()

    return post_url


def _write_in_frame(page, context, title: str, html: str, chart_png_path: str | None) -> str | None:
    from playwright.sync_api import TimeoutError as PWTimeout

    # mainFrame 내부 접근 시도
    try:
        frame = page.frame(name="mainFrame") or page.frame(url=lambda u: "PostWrite" in str(u))
    except Exception:
        frame = None

    if frame is None:
        # 직접 페이지에서 작업 시도 (신형 에디터)
        frame = page

    # 제목 입력
    _set_title(frame, title)
    time.sleep(1)

    # 차트 이미지 업로드 (있는 경우)
    if chart_png_path and Path(chart_png_path).exists():
        _upload_image(frame, page, chart_png_path)
        time.sleep(2)

    # HTML 콘텐츠 주입
    _inject_content(frame, html)
    time.sleep(1)

    # 발행
    return _publish(frame, page, context)


def _set_title(frame, title: str):
    selectors = [
        "input#subject",
        "input[name='subject']",
        "input.se_inputArea__title",
        "[placeholder*='제목']",
        "[aria-label*='제목']",
    ]
    for sel in selectors:
        try:
            elem = frame.locator(sel).first
            if elem.count() > 0:
                elem.click()
                elem.fill(title)
                print(f"✅ 제목 입력 완료 ({sel})")
                return
        except Exception:
            continue
    # fallback: JavaScript
    try:
        frame.evaluate(f"""
            const inputs = document.querySelectorAll('input');
            for (const input of inputs) {{
                if (input.type !== 'hidden') {{
                    input.value = {json.dumps(title)};
                    input.dispatchEvent(new Event('input', {{bubbles: true}}));
                    break;
                }}
            }}
        """)
        print("✅ 제목 JavaScript 주입 완료")
    except Exception as e:
        print(f"⚠️ 제목 입력 실패: {e}")


def _upload_image(frame, page, chart_png_path: str):
    try:
        # 이미지 삽입 버튼 클릭
        img_btn_selectors = [
            "button[title*='이미지']",
            "button[aria-label*='이미지']",
            ".se-toolbar-item-image",
            "[data-name='image']",
        ]
        for sel in img_btn_selectors:
            try:
                btn = frame.locator(sel).first
                if btn.count() > 0:
                    btn.click()
                    time.sleep(1)
                    break
            except Exception:
                continue

        # 파일 input 찾아서 업로드
        with page.expect_file_chooser() as fc_info:
            file_inputs = frame.locator("input[type='file']")
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(chart_png_path)
            else:
                frame.evaluate("document.querySelector('input[type=\"file\"]').click()")
        fc = fc_info.value
        fc.set_files(chart_png_path)
        print(f"✅ 차트 이미지 업로드 완료: {chart_png_path}")
        time.sleep(3)
    except Exception as e:
        print(f"⚠️ 이미지 업로드 실패 (건너뜀): {e}")


def _inject_content(frame, html: str):
    """SmartEditor 3.0 콘텐츠 주입 — 여러 방법 순차 시도."""
    # 방법 1: SE3 API
    try:
        result = frame.evaluate(f"""
            (() => {{
                const editorInstances = window.se2_instance || window.__SE_INSTANCE
                    || (window.nhn && window.nhn.husky && window.nhn.husky.EditorCore);
                if (editorInstances) {{
                    if (typeof editorInstances.setIR === 'function') {{
                        editorInstances.setIR({json.dumps(html)});
                        return 'api';
                    }}
                }}
                return null;
            }})()
        """)
        if result == "api":
            print("✅ 콘텐츠 SE3 API 주입 완료")
            return
    except Exception:
        pass

    # 방법 2: contenteditable 직접 주입 — 현재 frame + 모든 중첩 frame 순회
    content_selectors = [
        ".se-content",
        ".se2_inputarea",
        "div[contenteditable='true']",
        "[contenteditable='true']",
        "#editor_body",
        ".se-placeholder",
        ".editorContentArea",
    ]
    all_frames = frame.page.frames if hasattr(frame, "page") else []

    def _try_inject(target_frame, sel):
        try:
            elem = target_frame.locator(sel).first
            if elem.count() > 0:
                target_frame.evaluate(
                    f"document.querySelector({json.dumps(sel)}).innerHTML = {json.dumps(html)}"
                )
                target_frame.evaluate(
                    f"""
                    const el = document.querySelector({json.dumps(sel)});
                    if (el) el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    """
                )
                name = getattr(target_frame, "name", "?") or target_frame.url[:40]
                print(f"✅ 콘텐츠 innerHTML 주입 완료 ({sel}, frame={name})")
                return True
        except Exception:
            pass
        return False

    for sel in content_selectors:
        if _try_inject(frame, sel):
            return

    for f in all_frames:
        for sel in content_selectors:
            if _try_inject(f, sel):
                return

    print("⚠️ 콘텐츠 주입 실패 — 선택자를 찾지 못했습니다")


def _publish(frame, page, context) -> str | None:
    publish_selectors = [
        "button:has-text('발행')",
        "button:has-text('등록')",
        "button:has-text('저장')",
        "button:has-text('완료')",
        "input[value='발행']",
        "input[value='등록']",
        ".se-toolbar-item-publish",
        "#btn_publish",
        ".btn_publish",
        "#publish_btn",
        "[class*='publish']",
    ]
    for sel in publish_selectors:
        try:
            btn = frame.locator(sel).first
            if btn.count() > 0:
                btn.click()
                print(f"✅ 발행 버튼 클릭 ({sel})")
                time.sleep(3)

                # 발행 확인 팝업 처리
                confirm_selectors = [
                    "button:has-text('확인')",
                    "button:has-text('발행')",
                    ".se_btn_publish",
                ]
                for csel in confirm_selectors:
                    try:
                        confirm_btn = page.locator(csel).first
                        if confirm_btn.count() > 0:
                            confirm_btn.click()
                            time.sleep(3)
                            break
                    except Exception:
                        continue

                # 발행 후 URL 확인
                current_url = page.url
                if "logNo=" in current_url or f"/{BLOG_ID}/" in current_url:
                    print(f"✅ 발행 완료: {current_url}")
                    return current_url

                # 리다이렉트 대기
                try:
                    page.wait_for_url(lambda u: "logNo=" in u or (f"/{BLOG_ID}/" in u and "PostWrite" not in u), timeout=15000)
                    post_url = page.url
                    print(f"✅ 발행 완료: {post_url}")
                    return post_url
                except Exception:
                    print("⚠️ 발행 URL 확인 실패 — 발행됐을 수 있으나 URL을 가져오지 못했습니다")
                    return None
        except Exception:
            continue

    print("⚠️ 발행 버튼을 찾지 못했습니다")
    return None


def _load_cookies() -> list | None:
    """NAVER_COOKIES_JSON 환경변수 또는 naver_cookies.json 파일에서 쿠키 로드."""
    # GitHub Actions: 환경변수에서 (base64 디코드)
    env_cookies = os.environ.get("NAVER_COOKIES", "") or os.environ.get("NAVER_COOKIES_JSON", "")
    if env_cookies:
        try:
            decoded = base64.b64decode(env_cookies).decode("utf-8")
            cookies = json.loads(decoded)
            print(f"✅ 쿠키 로드 완료 (환경변수, {len(cookies)}개)")
            return cookies
        except Exception as e:
            print(f"⚠️ NAVER_COOKIES_JSON 디코딩 실패: {e}")

    # 로컬 실행: 파일에서
    if COOKIES_FILE.exists():
        try:
            cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
            print(f"✅ 쿠키 로드 완료 (파일, {len(cookies)}개)")
            return cookies
        except Exception as e:
            print(f"⚠️ 쿠키 파일 읽기 실패: {e}")

    print("⚠️ 네이버 쿠키 없음 — refresh_naver_cookies.py 실행 후 NAVER_COOKIES_JSON 시크릿 설정 필요")
    return None


def _find_write_url(page) -> str | None:
    """블로그 홈에서 글쓰기 버튼 href를 추출해 실제 글쓰기 URL 반환."""
    selectors = [
        "a:has-text('글쓰기')",
        "a[href*='PostWrite']",
        "a[href*='DesignWrite']",
        "a[href*='write']",
        ".link_write",
        "#headerBlogWrite",
        "button:has-text('글쓰기')",
    ]
    for sel in selectors:
        try:
            elem = page.locator(sel).first
            if elem.count() > 0:
                href = elem.get_attribute("href")
                if href:
                    url = href if href.startswith("http") else f"https://blog.naver.com{href}"
                    print(f"✅ 글쓰기 URL 발견 ({sel}): {url[:80]}")
                    return url
        except Exception:
            continue
    print("⚠️ 글쓰기 버튼을 찾지 못해 폴백 URL 사용")
    return None


def _is_logged_out(page) -> bool:
    try:
        # 로그인 버튼이 있으면 로그아웃 상태
        login_btn = page.locator("a:has-text('로그인'), .btn_login, a[href*='login']").first
        if login_btn.count() > 0:
            return True
        # 현재 URL이 로그인 페이지로 리다이렉트됐는지 확인
        if "nidlogin" in page.url or "login" in page.url.lower():
            return True
        return False
    except Exception:
        return False
