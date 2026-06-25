# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""뉴스레터 이메일 발송기.

A등급 기사만 모아 Gmail SMTP(TLS)로 HTML 뉴스레터를 보낸다.
"""

import logging
import smtplib
from datetime import date
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import config

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _build_html(articles: list, today: str) -> str:
    blocks = []
    for a in articles:
        title = a.get("article_title", "(제목 없음)")
        summary = (a.get("article_summary", "") or "").replace("\n", "<br>")
        blocks.append(
            f"""
            <div style="margin-bottom:24px;">
              <h2 style="color:#c0392b;margin:0 0 8px;">{title}</h2>
              <div style="color:#333;line-height:1.6;">{summary}</div>
            </div>
            <hr style="border:none;border-top:1px solid #eee;">
            """
        )
    body = "".join(blocks) if blocks else "<p>오늘 발송할 A등급 기사가 없습니다.</p>"
    return f"""
    <html><body style="font-family:Apple SD Gothic Neo, Malgun Gothic, sans-serif;max-width:680px;margin:0 auto;padding:16px;">
      <h1 style="border-bottom:3px solid #c0392b;padding-bottom:8px;">🐾 RedCarpet 오늘의 반려동물 뉴스</h1>
      <p style="color:#888;">{today}</p>
      {body}
      <p style="color:#aaa;font-size:12px;">본 메일은 RedCarpet 자동화 시스템이 발송했습니다.</p>
    </body></html>
    """


def send_newsletter(articles: list, recipients: list) -> None:
    """A등급 기사 뉴스레터를 수신자에게 발송한다."""
    if not config.GMAIL_USER or not config.GMAIL_PASSWORD:
        logger.warning("Gmail 자격증명 없음 - 뉴스레터 발송 건너뜀")
        return
    if not recipients:
        logger.warning("수신자 없음 - 뉴스레터 발송 건너뜀")
        return

    a_articles = [a for a in articles if a.get("grade") == "A"]
    if not a_articles:
        logger.info("A등급 기사 없음 - 뉴스레터 발송 건너뜀")
        return

    today = date.today().isoformat()
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[RedCarpet] 오늘의 반려동물 뉴스 - {today}"
    msg["From"] = config.GMAIL_USER
    msg["To"] = ", ".join(recipients)
    msg.attach(MIMEText(_build_html(a_articles, today), "html", "utf-8"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(config.GMAIL_USER, config.GMAIL_PASSWORD)
        server.sendmail(config.GMAIL_USER, recipients, msg.as_string())

    logger.info("뉴스레터 발송 완료: %d명, A등급 %d건", len(recipients), len(a_articles))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo = [{"article_title": "테스트 기사", "article_summary": "· 요약1\n· 요약2", "grade": "A"}]
    print(_build_html(demo, date.today().isoformat())[:200])
