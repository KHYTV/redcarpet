# 🐾 RedCarpet

반려동물 콘텐츠 자동화 파이프라인. Reddit·RSS에서 소재를 수집해 한국어 기사로 재작성하고,
하이브리드 팩트체크 → 검수/등급 판정 → A등급 기사 숏폼 영상 제작 → Google Sheets 저장 & 뉴스레터 발송까지 자동화한다.

## 파이프라인 개요

```
수집(Reddit/RSS) → 필터 → 기사작성(Claude) → 팩트체크(Claude+PubMed/Google)
  → 검수·교정(Claude) → 등급(A/B/C) → 숏폼제작(Kling AI+FFmpeg) → 저장/발송
```

## 디렉토리 구조

```
redcarpet/
├── main.py                 # 전체 오케스트레이션
├── config.py               # 환경변수 로드 + 상수
├── requirements.txt
├── .env.example
├── collectors/             # 수집 + 필터
│   ├── reddit_collector.py
│   ├── rss_collector.py
│   └── filter.py
├── processors/             # 기사 작성/팩트체크/검수/등급
│   ├── article_writer.py
│   ├── fact_checker.py
│   ├── article_reviewer.py
│   └── grader.py
├── shortform/              # 대본/영상/자막/파이프라인
│   ├── script_generator.py
│   ├── kling_generator.py
│   ├── caption_composer.py
│   └── pipeline.py
├── publishers/             # Sheets/이메일 발행
│   ├── sheets_publisher.py
│   └── email_publisher.py
├── output/{shortform,temp,results}
└── logs/
```

## 설치

```bash
cd redcarpet
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

FFmpeg(자막 합성용)와 한글 폰트(NanumGothic)는 별도 설치가 필요하다.

```bash
# Ubuntu/Debian
sudo apt install ffmpeg fonts-nanum
```

## .env 설정

`.env.example`을 복사해 `.env`로 만들고 값을 채운다.

| 변수 | 필수 | 설명 |
|------|------|------|
| `ANTHROPIC_API_KEY` | ✅ | 기사작성·팩트체크·검수·대본 |
| `KLING_API_KEY` | 숏폼 시 | Kling AI 영상 생성 (신규 단일 키, `kling.ai/dev/api-key`) |
| `KLING_ACCESS_KEY` / `KLING_SECRET_KEY` | 레거시 | 3.0 이전 모델용 (API Key 없을 때만) |
| `GOOGLE_SEARCH_API_KEY` / `GOOGLE_CSE_ID` | 선택 | 팩트체크 2차검증(비의료) |
| `GOOGLE_SERVICE_ACCOUNT_JSON` / `GOOGLE_SHEETS_ID` | 저장 시 | Sheets 발행 |
| `GMAIL_USER` / `GMAIL_PASSWORD` | 발송 시 | Gmail 앱 비밀번호 |
| `NEWSLETTER_RECIPIENTS` | 선택 | 콤마 구분 수신자 |

> `.env`는 절대 git에 커밋하지 않는다(`.gitignore`에 포함됨).

## 실행

```bash
# 전체 파이프라인
python main.py

# 모듈별 테스트 (1~7)
python test_runner.py 1     # Reddit 수집
python test_runner.py 2     # RSS 수집
python test_runner.py 6     # 숏폼 대본 (Kling 키 불필요)
python test_runner.py       # 인자 없으면 1,2만 실행 (API 불필요)
```

## 등급 기준

| 등급 | 점수 | action | 처리 |
|------|------|--------|------|
| A | 75+ | publish | 숏폼 제작 + 뉴스레터 |
| B | 50~74 | hold | 보류 |
| C | ~49 | discard | 폐기 |

> 팩트체크에서 high severity 오류 발견 시 점수와 무관하게 강제 C등급.

## cron 배포

매일 오전 5시(Asia/Seoul) 실행:

```cron
0 5 * * * /path/to/redcarpet/run.sh
```

```bash
chmod +x run.sh
crontab -e   # 위 줄 추가
```

## 모듈 설명

- **collectors** — Reddit 수집(old.reddit.com HTML 스크래핑, 공식 JSON API가 IP 차단되어 대체)과 feedparser 기반 RSS 수집, Levenshtein 중복 제거 필터
  - Reddit: 점수 통과 셀프 게시물만 본문 fetch(요청 절약), 요청 간 2.5초 지연. `REDDIT_USER_AGENT`로 UA 변경 가능. ToS상 비공식 경로이므로 발행 시 콘텐츠 라이선스 검토 권장.
- **processors** — Claude Haiku로 기사 재작성, PubMed/Google 하이브리드 팩트체크, 100점 검수, **동물보도 윤리 준칙 검증**, A/B/C 등급
- **shortform** — Claude 대본 생성, Kling AI(JWT 인증) 세로형 영상, FFmpeg 자막 합성, 4개 플랫폼 출력
- **publishers** — Google Sheets append, Gmail SMTP 뉴스레터

## 🐾 동물보도 윤리 준칙 (차별점)

RedCarpet은 동물을 상품이 아닌 감응적 존재로 존중하는 **동물권 지향 언론보도**를 지향한다.
[동물보도 윤리 준칙 7원칙](docs/동물보도윤리준칙.md)을 코드화하여 파이프라인에 강제한다:

| 단계 | 메커니즘 |
|------|---------|
| 생성 | `ethics_guidelines.py`의 준칙을 작성 프롬프트에 '헌법'으로 주입 |
| 검증 | `ethics_reviewer.py`가 7원칙 0~3점 채점 + 위반 추출 |
| 발행 | 심각(high) 위반 시 점수 무관 **발행 거부** (`grader.py` ethics veto) |
| 감사 | 기사별 `ethics_score`·`ethics_violations` 기록 |

> 팩트체크와 윤리검증, **두 개의 독립적 거부권**이 발행을 통제한다. 단순 표방이 아니라 측정·강제·감사 가능한 구조.

## 라이선스 / 지적재산권

- 독점 라이선스 — [LICENSE](LICENSE) 참조 (무단 복제·배포·역설계 금지)
- 소스코드·윤리 준칙 문서는 저작권법으로 보호됨. 프롬프트·점수 로직은 영업비밀
- © 2026 RedCarpet Project. All rights reserved.
