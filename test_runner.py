# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""모듈별 개별 테스트 러너.

사용법:
  python test_runner.py [1-7]

  1: Reddit 수집      2: RSS 수집        3: 기사 작성
  4: 팩트체크         5: 검수+등급       6: 숏폼 대본
  7: 전체 파이프라인
인자를 주지 않으면 API 불필요한 1,2만 실행한다.
"""

import json
import logging
import sys

import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

# 공용 샘플 기사
SAMPLE_ARTICLE = {
    "title": "강아지 산책, 하루 몇 번이 적당할까",
    "article_title": "강아지 산책, 하루 몇 번이 적당할까",
    "article_body": "반려견 건강을 위해 하루 2~3회 산책이 권장됩니다. 소형견은 짧게 자주, 대형견은 길게 운동시켜야 합니다.",
    "article_summary": "· 소형견 2회, 대형견 3회 이상\n· 정신건강에도 중요",
    "source_type": "reddit",
    "grade": "A",
    "score": 82,
}


def test_1_reddit():
    from collectors import reddit_collector
    items = reddit_collector.collect_reddit()
    print(f"\n수집 {len(items)}건. 첫 3개:")
    for it in items[:3]:
        print(json.dumps(it, ensure_ascii=False, indent=2))


def test_2_rss():
    from collectors import rss_collector
    items = rss_collector.collect_rss()
    print(f"\n수집 {len(items)}건. 첫 3개:")
    for it in items[:3]:
        print(json.dumps(it, ensure_ascii=False, indent=2))


def test_3_writer():
    from processors import article_writer
    sample = [{"title": SAMPLE_ARTICLE["title"], "content": "Dogs need 2-3 walks per day.", "source_type": "reddit"}]
    result = article_writer.write_articles(sample, config.ANTHROPIC_API_KEY)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def test_4_factcheck():
    from processors import fact_checker
    result = fact_checker.fact_check(SAMPLE_ARTICLE, config.ANTHROPIC_API_KEY)
    print("passed:", result.get("fact_check_passed"))
    print(result.get("fact_check_summary"))


def test_5_review_grade():
    from processors import article_reviewer, grader
    reviewed = article_reviewer.review_article(SAMPLE_ARTICLE, config.ANTHROPIC_API_KEY)
    graded = grader.grade_article(reviewed)
    print("score:", graded.get("score"), "grade:", graded.get("grade"), "action:", graded.get("action"))


def test_6_script():
    from shortform import script_generator
    script = script_generator.generate_script(SAMPLE_ARTICLE, config.ANTHROPIC_API_KEY)
    print(json.dumps(script, ensure_ascii=False, indent=2))


def test_7_full():
    import main
    summary = main.run()
    print("요약:", summary)


TESTS = {
    "1": test_1_reddit,
    "2": test_2_rss,
    "3": test_3_writer,
    "4": test_4_factcheck,
    "5": test_5_review_grade,
    "6": test_6_script,
    "7": test_7_full,
}


def main_cli():
    args = sys.argv[1:]
    if not args:
        print("인자 없음 → API 불필요 테스트(1, 2)만 실행\n")
        test_1_reddit()
        test_2_rss()
        return
    for arg in args:
        fn = TESTS.get(arg)
        if not fn:
            print(f"알 수 없는 테스트 번호: {arg} (1-7)")
            continue
        print(f"\n===== TEST {arg} =====")
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"TEST {arg} 실패: {exc}")


if __name__ == "__main__":
    main_cli()
