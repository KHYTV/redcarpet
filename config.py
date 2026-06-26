# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""RedCarpet 전역 설정.

.env 파일에서 환경변수를 로드하고, 파이프라인 전반에서 사용하는 상수를 정의한다.
원본 가이드에서 누락된 특수문자(따옴표, URL 스킴 등)를 복원했다.
"""

import os

from dotenv import load_dotenv

load_dotenv()


# ===== Claude API =====
# 필수값. 없으면 KeyError로 즉시 실패시켜 설정 누락을 빠르게 알린다.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL_WRITER = "claude-haiku-4-5-20251001"
MODEL_REVIEWER = "claude-haiku-4-5-20251001"
REQUEST_INTERVAL = 2  # 초, Claude API 호출 간 최소 간격

# ===== Kling AI =====
# 신규 단일 API Key 방식(권장). 있으면 Bearer 인증에 그대로 사용한다.
KLING_API_KEY = os.environ.get("KLING_API_KEY", "")
# 레거시 AccessKey/SecretKey 방식(3.0 이전 모델). API Key가 없을 때만 JWT로 fallback.
KLING_ACCESS_KEY = os.environ.get("KLING_ACCESS_KEY", "")
KLING_SECRET_KEY = os.environ.get("KLING_SECRET_KEY", "")
# 신규 플랫폼 도메인(중국 외 지역). 구 도메인 api.klingai.com에서 변경됨.
KLING_API_BASE = os.environ.get("KLING_API_BASE", "https://api-singapore.klingai.com")

# ===== 팩트체크 검색 API (선택) =====
GOOGLE_SEARCH_API_KEY = os.environ.get("GOOGLE_SEARCH_API_KEY", "")
GOOGLE_CSE_ID = os.environ.get("GOOGLE_CSE_ID", "")
PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

# ===== Reddit =====
SUBREDDITS = ["dogs", "cats", "pets", "AskVet", "dogtraining", "puppy101", "CatAdvice"]

# ===== 해외 RSS =====
OVERSEAS_RSS = [
    "https://www.dogingtonpost.com/feed",
    "https://www.goodnewsforpets.com/feed",
    "https://www.whole-dog-journal.com/feed",
    "https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-wildlife-health-lab/feed",
]

# ===== 국내 구글뉴스 RSS (URL 인코딩된 한글 검색어) =====
KOREAN_NEWS_RSS = [
    "https://news.google.com/rss/search?q=%EB%B0%98%EB%A0%A4%EB%8F%99%EB%AC%BC+%EA%B1%B4%EA%B0%95&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=%EB%B0%98%EB%A0%A4%EB%8F%99%EB%AC%BC+%EB%B3%B4%ED%97%98+%EC%A0%95%EC%B1%85&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=%EC%9C%A0%EA%B8%B0%EB%8F%99%EB%AC%BC+%EC%9E%85%EC%96%91&hl=ko&gl=KR&ceid=KR:ko",
    "https://news.google.com/rss/search?q=%ED%8E%AB%ED%85%8C%ED%81%AC+%EB%B0%98%EB%A0%A4%EB%8F%99%EB%AC%BC&hl=ko&gl=KR&ceid=KR:ko",
]

# ===== 필터링 =====
MAX_ITEMS = 20
MIN_REDDIT_SCORE = 10
DUPLICATE_THRESHOLD = 0.85

# ===== 등급 기준 =====
GRADE_A_MIN = 75
GRADE_B_MIN = 50

# ===== 숏폼 플랫폼 =====
TARGET_PLATFORMS = ["youtube_shorts", "instagram_reels", "tiktok", "naver_clip"]

# ===== Google / Gmail =====
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_SHEETS_ID = os.environ.get("GOOGLE_SHEETS_ID", "")
GMAIL_USER = os.environ.get("GMAIL_USER", "")
GMAIL_PASSWORD = os.environ.get("GMAIL_PASSWORD", "")

# ===== 뉴스레터 수신자 =====
NEWSLETTER_RECIPIENTS = [
    addr.strip()
    for addr in os.environ.get("NEWSLETTER_RECIPIENTS", "").split(",")
    if addr.strip()
]

# ===== 자동 배포 (정적 호스팅) =====
# DEPLOY_TARGET: netlify | cloudflare | "" (빈값이면 자동배포 안 함)
DEPLOY_TARGET = os.environ.get("DEPLOY_TARGET", "").lower()
# AUTO_GIT_PUSH=1 이면 일일 빌드가 docs/index.html을 커밋·푸시해 GitHub Pages 갱신
AUTO_GIT_PUSH = os.environ.get("AUTO_GIT_PUSH", "").lower() in ("1", "true", "yes")
NETLIFY_AUTH_TOKEN = os.environ.get("NETLIFY_AUTH_TOKEN", "")
NETLIFY_SITE_ID = os.environ.get("NETLIFY_SITE_ID", "")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")
CF_PAGES_PROJECT = os.environ.get("CF_PAGES_PROJECT", "")

# ===== 경로 =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
SHORTFORM_DIR = os.path.join(OUTPUT_DIR, "shortform")
TEMP_DIR = os.path.join(OUTPUT_DIR, "temp")
RESULTS_DIR = os.path.join(OUTPUT_DIR, "results")
LOG_DIR = os.path.join(BASE_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "automation.log")
