# Coin Report 프로젝트

## 프로젝트 개요
BTC 시황 + ICT 구조 분석 텔레그램 자동 발송 봇 + 네이버 블로그 자동 발행 시스템

## 핵심 파일
- `ict_writer.py` — 텔레그램 리포트 메인 스크립트 (모든 시간 슬롯에서 실행)
- `blog_main.py` — 네이버 블로그 발행 오케스트레이터 (17시·21시만 실행)
- `chart_generator.py` — mplfinance 캔들차트 PNG 생성
- `news_fetcher.py` — CryptoCompare BTC 뉴스 수집
- `blog_writer_afternoon.py` — 17시용 오후 시황 포스트 생성 (Claude API)
- `blog_writer_evening.py` — 21시용 마감 분석 포스트 생성 (Claude API)
- `naver_poster.py` — Playwright 기반 네이버 블로그 자동 발행
- `extract_naver_cookies.py` — 최초 1회 로컬 실행, 쿠키 추출 (GitHub Secrets 등록용)
- `combined_telegram_guideline.txt` — Claude 텔레그램 리포트 가이드라인
- `config.py` — API 키 (gitignore 처리됨, GitHub에 올라가지 않음)

## GitHub
- 레포: https://github.com/remember0706-MUTU/-coin-report (Public)
- 브랜치: `dryforge/naver-blog-auto` (작업 브랜치) → 테스트 후 main에 머지
- GitHub Actions 워크플로우: `.github/workflows/ict_report.yml`
- GitHub Secrets: ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID, NAVER_COOKIES

## 네이버 블로그 발행 구조
- 17시: `[MM/DD] 비트코인 오후 시황 | 현재 가격 흐름 점검` (48시간 캔들 차트)
- 21시: `[MM/DD] 비트코인 일일 마감 분석 | ICT·SMC 구조 + 내일 전망` (72시간 캔들 차트 + 뉴스)
- Playwright + Xvfb 방식 (headless=False + 가상 디스플레이)
- 본문 삽입: 클립보드(pyperclip) → Ctrl+V 붙여넣기
- 차트 저장 위치: `output_ict/charts/YYYYMMDD_HHMM_chart.png`

## 스케줄러 (cron-job.org)
- 매일 09:00 / 13:00 / 17:00 / 21:00 KST 자동 실행
- cron-job.org에서 GitHub workflow_dispatch API 호출로 트리거 (time_slot 파라미터 포함)
- Job IDs: 7620986 / 7620987 / 7620988 / 7620989
- GitHub PAT: config.py에 보관 (gitignore 처리됨, GitHub에 올라가지 않음)
- ⚠️ cron-job.org 기존 4개 잡에 `time_slot` 파라미터 추가 필요 (T10 수동 작업)

## 텔레그램
- 채널: @remember070605
- 푸터 (별도 메시지로 항상 마지막에 발송):
  🔴 𝗽𝗿𝗶𝗰𝗲 𝗶𝘀 𝗮 𝘀𝘁𝗼𝗿𝘆 𝗮𝗻𝗱 𝗹𝗶𝗾𝘂𝗶𝗱𝗶𝘁𝘆 𝗶𝘀 𝘁𝗵𝗲 𝗺𝗮𝗽 🔴
  📝 https://blog.naver.com/remember0706

## OHLCV 데이터
- Binance/Bybit → GitHub Actions에서 지역 차단(451/403)으로 막힘
- CryptoCompare API로 교체 (https://min-api.cryptocompare.com)

## 워크플로우 수동 실행 방법
```powershell
# 텔레그램만 (09 또는 13)
$body = '{"ref":"dryforge/naver-blog-auto","inputs":{"time_slot":"09"}}' 
# 텔레그램 + 블로그 (17 또는 21)
$body = '{"ref":"dryforge/naver-blog-auto","inputs":{"time_slot":"17"}}'

$headers = @{
    "Authorization" = "Bearer $env:GITHUB_PAT"
    "Accept" = "application/vnd.github+json"
    "Content-Type" = "application/json"
    "X-GitHub-Api-Version" = "2022-11-28"
}
Invoke-RestMethod -Uri "https://api.github.com/repos/remember0706-MUTU/-coin-report/actions/workflows/ict_report.yml/dispatches" -Method POST -Headers $headers -Body $body
```

## 로컬 dry-run 테스트
```powershell
# 발행 없이 내용만 출력 (쿠키 불필요)
python blog_main.py --dry-run 17
python blog_main.py --dry-run 21
```

## 사용자 정보
- 블로그: https://blog.naver.com/remember0706
- 초보자 - 단계별 안내 필요, 스크린샷으로 소통
