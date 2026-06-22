"""숏폼 제작 파이프라인.

A등급 기사를 받아 대본 생성 → Kling 영상 생성 → 플랫폼별 자막 합성 →
결과 JSON 저장까지 오케스트레이션한다. 중간 단계 실패는 결과에 기록하고 계속한다.
"""

import json
import logging
import os

import config
from shortform import script_generator, kling_generator, caption_composer

logger = logging.getLogger(__name__)


def _article_id(article: dict, idx: int) -> str:
    return str(article.get("id") or article.get("url", "") or f"article_{idx}").split("/")[-1][:40] or f"article_{idx}"


def _process_one(article: dict, idx: int, anthropic_api_key: str,
                 kling_api_key: str, kling_access_key: str, kling_secret_key: str) -> dict:
    article_id = _article_id(article, idx)
    result = {
        "article_id": article_id,
        "article_title": article.get("article_title", ""),
        "grade": article.get("grade", ""),
        "script": None,
        "scene_videos": [],
        "platform_outputs": {},
        "status": "failed",
        "errors": [],
    }

    # 1) 대본
    try:
        script = script_generator.generate_script(article, anthropic_api_key)
        result["script"] = script
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"script: {exc}")
        logger.error("[%s] 대본 생성 실패: %s", article_id, exc)
        return result

    # 2) Kling 영상
    try:
        scene_videos = kling_generator.generate_all_scenes(
            script.get("scenes", []),
            api_key=kling_api_key,
            access_key=kling_access_key,
            secret_key=kling_secret_key,
        )
        result["scene_videos"] = scene_videos
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"kling: {exc}")
        logger.error("[%s] 영상 생성 실패: %s", article_id, exc)
        return result

    # 3) 플랫폼별 자막 합성
    hashtags = script.get("hashtags", {})
    for platform in config.TARGET_PLATFORMS:
        try:
            path = caption_composer.compose_video(article_id, script, scene_videos, platform)
            result["platform_outputs"][platform] = {
                "status": "completed",
                "file_path": path,
                "hashtags": hashtags.get(platform, []),
            }
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"compose[{platform}]: {exc}")
            result["platform_outputs"][platform] = {
                "status": "failed",
                "file_path": None,
                "hashtags": hashtags.get(platform, []),
            }
            logger.error("[%s] %s 합성 실패: %s", article_id, platform, exc)

    completed = any(v["status"] == "completed" for v in result["platform_outputs"].values())
    result["status"] = "completed" if completed else "failed"

    # 4) 결과 저장
    os.makedirs(config.RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(config.RESULTS_DIR, f"{article_id}_result.json")
    try:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(result, fh, ensure_ascii=False, indent=2)
    except OSError as exc:
        logger.error("[%s] 결과 저장 실패: %s", article_id, exc)

    return result


def run_shortform_pipeline(articles: list, anthropic_api_key: str,
                           kling_api_key: str = "",
                           kling_access_key: str = "", kling_secret_key: str = "") -> list:
    """A등급(action=publish) 기사만 골라 숏폼을 제작한다.

    kling_api_key(신규 단일 키) 우선, 없으면 access/secret(레거시 JWT) 사용.
    """
    targets = [a for a in articles if a.get("grade") == "A"]
    logger.info("숏폼 제작 대상: %d건", len(targets))

    results = []
    for idx, article in enumerate(targets):
        results.append(
            _process_one(article, idx, anthropic_api_key,
                         kling_api_key, kling_access_key, kling_secret_key)
        )
    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sample = [{
        "article_title": "강아지 산책 가이드",
        "article_body": "하루 2~3회 산책이 권장됩니다.",
        "article_summary": "· 소형견 2회",
        "grade": "A",
    }]
    print(run_shortform_pipeline(sample, config.ANTHROPIC_API_KEY,
                                 kling_api_key=config.KLING_API_KEY,
                                 kling_access_key=config.KLING_ACCESS_KEY,
                                 kling_secret_key=config.KLING_SECRET_KEY))
