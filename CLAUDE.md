# Coin Report 프로젝트

## 프로젝트 개요
BTC 시황 + ICT 구조 분석 텔레그램 자동 발송 봇

## 핵심 파일
- `ict_writer.py` — 메인 스크립트 (CoinGecko + Binance + Claude API → 텔레그램 발송)
- `combined_telegram_guideline.txt` — Claude 리포트 작성 가이드라인
- `config.py` — API 키 (gitignore 처리됨, GitHub에 올라가지 않음)

## GitHub
- 레포: https://github.com/remember0706-MUTU/-coin-report (Public)
- GitHub Actions 워크플로우: `.github/workflows/ict_report.yml`
- GitHub Secrets: ANTHROPIC_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHANNEL_ID

## 스케줄러 (cron-job.org)
- 매일 09:00 / 13:00 / 17:00 / 21:00 KST 자동 실행
- cron-job.org에서 GitHub workflow_dispatch API 호출로 트리거
- Job IDs: 7620986 / 7620987 / 7620988 / 7620989
- GitHub PAT: config.py에 보관 (gitignore 처리됨, GitHub에 올라가지 않음)

## 텔레그램
- 채널: @remember070605
- 푸터 (별도 메시지로 항상 마지막에 발송):
  🔴 𝗽𝗿𝗶𝗰𝗲 𝗶𝘀 𝗮 𝘀𝘁𝗼𝗿𝘆 𝗮𝗻𝗱 𝗹𝗶𝗾𝘂𝗶𝗱𝗶𝘁𝘆 𝗶𝘀 𝘁𝗵𝗲 𝗺𝗮𝗽 🔴
  📝 https://blog.naver.com/remember0706

## OHLCV 데이터
- `api.binance.com` → GitHub Actions에서 지역 차단(451)으로 막힘
- `data-api.binance.vision` (Binance 공개 데이터 전용 도메인)으로 교체하여 사용 중
- BTCUSDT 4H/1H 캔들 100개씩 수집

## 워크플로우 수동 실행 방법
```powershell
$headers = @{
    "Authorization" = "Bearer $env:GITHUB_PAT"
    "Accept" = "application/vnd.github+json"
    "Content-Type" = "application/json"
    "X-GitHub-Api-Version" = "2022-11-28"
}
$body = '{"ref":"main"}' | ConvertFrom-Json | ConvertTo-Json
Invoke-RestMethod -Uri "https://api.github.com/repos/remember0706-MUTU/-coin-report/actions/workflows/ict_report.yml/dispatches" -Method POST -Headers $headers -Body $body
```

## 사용자 정보
- 블로그: https://blog.naver.com/remember0706
- 초보자 - 단계별 안내 필요, 스크린샷으로 소통
