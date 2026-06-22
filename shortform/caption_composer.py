"""자막 합성기.

Kling 생성 영상을 다운로드하고 FFmpeg drawtext로 자막을 오버레이한 뒤,
장면들을 concat해 플랫폼별 최종 mp4를 만든다. FFmpeg가 없으면 예외를 던진다.
"""

import logging
import os
import shutil
import subprocess

import requests

import config

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 60

# 플랫폼별 자막 Y 위치 (FFmpeg drawtext y 표현식)
CAPTION_Y = {
    "youtube_shorts": "(h-text_h)/2",
    "instagram_reels": "h*0.75",
    "tiktok": "(h-text_h)/2",
    "naver_clip": "h*0.80",
}

# 한글 폰트 경로 (Linux 기준). 없으면 fallback.
KOREAN_FONT = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def _pick_font() -> str:
    if os.path.exists(KOREAN_FONT):
        return KOREAN_FONT
    return FALLBACK_FONT


def _escape_text(text: str) -> str:
    """FFmpeg drawtext 텍스트 이스케이프."""
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _download(url: str, dest: str) -> str:
    resp = requests.get(url, stream=True, timeout=HTTP_TIMEOUT)
    resp.raise_for_status()
    with open(dest, "wb") as fh:
        for chunk in resp.iter_content(chunk_size=8192):
            fh.write(chunk)
    return dest


def _overlay_caption(src: str, dest: str, caption: str, platform: str) -> str:
    font = _pick_font()
    y_expr = CAPTION_Y.get(platform, "(h-text_h)/2")
    drawtext = (
        f"drawtext=fontfile='{font}':text='{_escape_text(caption)}':"
        f"fontsize=72:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=10:"
        f"x=(w-text_w)/2:y={y_expr}"
    )
    cmd = [
        "ffmpeg", "-y", "-i", src,
        "-vf", drawtext,
        "-c:a", "copy",
        dest,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return dest


def compose_video(article_id: str, script: dict, scene_videos: list, platform: str) -> str:
    """장면별 자막 오버레이 후 concat → 최종 mp4 경로 반환."""
    if not _ffmpeg_available():
        raise RuntimeError("FFmpeg가 설치되어 있지 않습니다.")

    os.makedirs(config.SHORTFORM_DIR, exist_ok=True)
    os.makedirs(config.TEMP_DIR, exist_ok=True)

    scenes = {s["scene_no"]: s for s in script.get("scenes", [])}
    # video_url이 있는 장면만 순서대로 처리
    valid = sorted(
        [sv for sv in scene_videos if sv.get("video_url") and sv.get("status") == "succeed"],
        key=lambda x: x.get("scene_no", 0),
    )
    if not valid:
        raise RuntimeError("사용 가능한 장면 영상이 없습니다.")

    captioned_paths = []
    for sv in valid:
        scene_no = sv["scene_no"]
        raw = os.path.join(config.TEMP_DIR, f"{article_id}_{platform}_s{scene_no}_raw.mp4")
        cap = os.path.join(config.TEMP_DIR, f"{article_id}_{platform}_s{scene_no}_cap.mp4")
        _download(sv["video_url"], raw)
        caption = scenes.get(scene_no, {}).get("caption", "")
        _overlay_caption(raw, cap, caption, platform)
        captioned_paths.append(cap)

    # concat 리스트 파일 작성
    list_path = os.path.join(config.TEMP_DIR, f"{article_id}_{platform}_concat.txt")
    with open(list_path, "w", encoding="utf-8") as fh:
        for p in captioned_paths:
            fh.write(f"file '{os.path.abspath(p)}'\n")

    final_path = os.path.join(config.SHORTFORM_DIR, f"{article_id}_{platform}_final.mp4")
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", list_path, "-c", "copy", final_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    logger.info("자막 합성 완료: %s", final_path)
    return final_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("FFmpeg 사용 가능:", _ffmpeg_available())
