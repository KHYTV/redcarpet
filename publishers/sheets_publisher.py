"""Google Sheets 발행기.

Service Account로 Sheets API 인증 후 'articles'/'shortform' 시트에 행을 append 한다.
"""

import logging

from google.oauth2 import service_account
from googleapiclient.discovery import build

import config

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

ARTICLE_HEADER = [
    "date", "source", "original_title", "article_title", "article_body",
    "article_summary", "fact_check_result", "fact_check_summary",
    "score", "grade", "corrections", "published",
]
SHORTFORM_HEADER = [
    "date", "article_id", "article_title", "platform",
    "file_path", "status", "hashtags",
]


def _service():
    if not config.GOOGLE_SERVICE_ACCOUNT_JSON:
        raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON 환경변수가 필요합니다.")
    if not config.GOOGLE_SHEETS_ID:
        raise ValueError("GOOGLE_SHEETS_ID 환경변수가 필요합니다.")
    creds = service_account.Credentials.from_service_account_file(
        config.GOOGLE_SERVICE_ACCOUNT_JSON, scopes=SCOPES
    )
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def _append(sheet_name: str, rows: list) -> None:
    if not rows:
        logger.info("Sheets[%s] append 대상 없음", sheet_name)
        return
    service = _service()
    service.spreadsheets().values().append(
        spreadsheetId=config.GOOGLE_SHEETS_ID,
        range=f"{sheet_name}!A1",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    logger.info("Sheets[%s] %d행 append 완료", sheet_name, len(rows))


def save_articles(articles: list) -> None:
    """기사 데이터를 'articles' 시트에 append."""
    rows = []
    for a in articles:
        rows.append([
            a.get("written_at", "") or a.get("collected_at", ""),
            a.get("source_type", ""),
            a.get("title", ""),
            a.get("article_title", ""),
            a.get("article_body", ""),
            a.get("article_summary", ""),
            "PASS" if a.get("fact_check_passed") else "FAIL",
            a.get("fact_check_summary", ""),
            a.get("score", 0),
            a.get("grade", ""),
            a.get("corrections", ""),
            "Y" if a.get("action") == "publish" else "N",
        ])
    _append("articles", rows)


def save_shortform_results(results: list) -> None:
    """숏폼 결과를 'shortform' 시트에 플랫폼별 행으로 append."""
    rows = []
    for r in results:
        for platform, out in r.get("platform_outputs", {}).items():
            rows.append([
                "",  # date - Sheets에서 채우거나 호출부에서 지정
                r.get("article_id", ""),
                r.get("article_title", ""),
                platform,
                out.get("file_path", ""),
                out.get("status", ""),
                ", ".join(out.get("hashtags", [])),
            ])
    _append("shortform", rows)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("ARTICLE_HEADER:", ARTICLE_HEADER)
    print("SHORTFORM_HEADER:", SHORTFORM_HEADER)
