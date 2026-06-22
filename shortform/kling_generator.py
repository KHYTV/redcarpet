"""Kling AI text2video 생성기.

인증 두 방식 모두 지원:
  - 신규: 단일 API Key → Authorization: Bearer <api_key> (JWT 불필요, 권장)
  - 레거시: AccessKey + SecretKey → JWT(HS256, 30분) → Authorization: Bearer <jwt>
장면별 영상 생성을 비동기 제출 후 폴링한다.
참고: https://kling.ai/document-api/api/get-started/authentication
"""

import logging
import time

import jwt
import requests

import config

logger = logging.getLogger(__name__)

CREATE_URL = f"{config.KLING_API_BASE}/v1/videos/text2video"
QUERY_URL = f"{config.KLING_API_BASE}/v1/videos/text2video/{{task_id}}"

POLL_INTERVAL = 10  # 초
POLL_TIMEOUT = 300  # 초 (최대 5분)
HTTP_TIMEOUT = 30

PROMPT_SUFFIX = ", cinematic quality, warm lighting, cute pet atmosphere, vertical 9:16"
NEGATIVE_PROMPT = "blurry, text, watermark, violent, scary"


def _make_token(access_key: str, secret_key: str) -> str:
    """레거시 Kling JWT 발급 (30분 유효)."""
    now = int(time.time())
    payload = {"iss": access_key, "exp": now + 1800, "nbf": now - 5}
    token = jwt.encode(payload, secret_key, algorithm="HS256", headers={"alg": "HS256", "typ": "JWT"})
    if isinstance(token, bytes):  # PyJWT 일부 버전은 bytes 반환
        token = token.decode("utf-8")
    return token


def _resolve_bearer(api_key: str, access_key: str, secret_key: str) -> tuple:
    """인증 토큰과 'JWT 여부'를 반환한다.

    api_key가 있으면 그대로 Bearer로 사용(고정), 없으면 ak/sk로 JWT 발급(만료 시 갱신 필요).
    반환: (bearer_token, is_jwt)
    """
    if api_key:
        return api_key, False
    if access_key and secret_key:
        return _make_token(access_key, secret_key), True
    raise ValueError("KLING_API_KEY 또는 KLING_ACCESS_KEY/KLING_SECRET_KEY가 필요합니다.")


def _headers(bearer: str) -> dict:
    return {"Authorization": f"Bearer {bearer}", "Content-Type": "application/json"}


def _submit_scene(scene: dict, bearer: str) -> str:
    """장면 1개 생성 요청 제출 → task_id 반환."""
    payload = {
        "model_name": "kling-v1-6",
        "mode": "pro",
        "duration": str(scene.get("duration", 5)),
        "aspect_ratio": "9:16",
        "prompt": scene.get("visual_prompt", "") + PROMPT_SUFFIX,
        "negative_prompt": NEGATIVE_PROMPT,
        "cfg_scale": 0.5,
    }
    resp = requests.post(CREATE_URL, json=payload, headers=_headers(bearer), timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    task_id = data.get("data", {}).get("task_id")
    if not task_id:
        raise RuntimeError(f"task_id 없음: {data}")
    return task_id


def _poll_task(task_id: str, api_key: str, access_key: str, secret_key: str) -> dict:
    """task_id 폴링 → {status, video_url}. JWT는 폴링마다 갱신한다."""
    url = QUERY_URL.format(task_id=task_id)
    deadline = time.time() + POLL_TIMEOUT
    while time.time() < deadline:
        bearer, _ = _resolve_bearer(api_key, access_key, secret_key)  # 만료 대비 매번 갱신
        resp = requests.get(url, headers=_headers(bearer), timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        status = data.get("task_status")
        if status == "succeed":
            videos = data.get("task_result", {}).get("videos", [])
            video_url = videos[0].get("url") if videos else None
            return {"status": "succeed", "video_url": video_url}
        if status == "failed":
            return {"status": "failed", "video_url": None}
        time.sleep(POLL_INTERVAL)
    return {"status": "timeout", "video_url": None}


def generate_all_scenes(scenes: list, api_key: str = "",
                        access_key: str = "", secret_key: str = "") -> list:
    """전체 장면 비동기 생성. [{scene_no, task_id, status, video_url}, ...] 반환.

    api_key(신규 단일 키) 우선, 없으면 access_key/secret_key(레거시)로 JWT 인증.
    """
    bearer, _ = _resolve_bearer(api_key, access_key, secret_key)  # 자격 검증 겸 최초 발급

    # 1) 전체 제출
    submitted = []
    for scene in scenes:
        scene_no = scene.get("scene_no")
        try:
            task_id = _submit_scene(scene, bearer)
            submitted.append({"scene_no": scene_no, "task_id": task_id})
            logger.info("장면 %s 제출: task_id=%s", scene_no, task_id)
        except Exception as exc:  # noqa: BLE001
            logger.error("장면 %s 제출 실패: %s", scene_no, exc)
            submitted.append({"scene_no": scene_no, "task_id": None})

    # 2) 폴링
    results = []
    for item in submitted:
        if not item["task_id"]:
            results.append({**item, "status": "submit_failed", "video_url": None})
            continue
        try:
            polled = _poll_task(item["task_id"], api_key, access_key, secret_key)
        except Exception as exc:  # noqa: BLE001
            logger.error("장면 %s 폴링 실패: %s", item["scene_no"], exc)
            polled = {"status": "error", "video_url": None}
        results.append({**item, **polled})
        logger.info("장면 %s 완료: %s", item["scene_no"], polled["status"])

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    demo_scenes = [{"scene_no": 1, "duration": 5, "visual_prompt": "a cute golden retriever walking in a park"}]
    print(generate_all_scenes(
        demo_scenes,
        api_key=config.KLING_API_KEY,
        access_key=config.KLING_ACCESS_KEY,
        secret_key=config.KLING_SECRET_KEY,
    ))
