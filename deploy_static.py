# Copyright (c) 2026 RedCarpet Project
# Licensed under the MIT License. See LICENSE.
"""정적 사이트 자동 배포.

output/web_sample.html → deploy/index.html 로 복사 후, DEPLOY_TARGET에 따라
Netlify 또는 Cloudflare Pages에 npx CLI로 배포한다(전역 설치 불필요).
인증 토큰은 .env에서 읽는다. 토큰 미설정 시 조용히 건너뛴다.

매일 빌드(build_site.py) 끝에서 호출되어 사이트가 자동 갱신된다.
"""

import os
import shutil
import subprocess
import sys

import config


def _prepare():
    src = os.path.join(config.OUTPUT_DIR, "web_sample.html")
    ddir = os.path.join(config.BASE_DIR, "deploy")
    os.makedirs(ddir, exist_ok=True)
    if not os.path.isfile(src):
        raise FileNotFoundError(src)
    shutil.copyfile(src, os.path.join(ddir, "index.html"))
    return ddir


def _run(cmd, env=None):
    """npx CLI 실행 (Windows는 shell 경유)."""
    print("배포 실행:", " ".join(c if "--auth" not in (cmd[i-1] if i else "") else "***"
                                 for i, c in enumerate(cmd)))
    r = subprocess.run(cmd, cwd=config.BASE_DIR, env=env, shell=(os.name == "nt"),
                       capture_output=True, text=True, encoding="utf-8", errors="ignore")
    out = (r.stdout or "") + (r.stderr or "")
    print(out[-1200:])
    return r.returncode == 0, out


def deploy():
    target = config.DEPLOY_TARGET
    if not target:
        print("DEPLOY_TARGET 미설정 - 자동배포 건너뜀 (.env 참고)")
        return None
    ddir = _prepare()

    if target == "netlify":
        if not (config.NETLIFY_AUTH_TOKEN and config.NETLIFY_SITE_ID):
            print("NETLIFY_AUTH_TOKEN/NETLIFY_SITE_ID 미설정 - 건너뜀")
            return None
        cmd = ["npx", "-y", "netlify-cli", "deploy", "--prod", "--dir", ddir,
               "--site", config.NETLIFY_SITE_ID, "--auth", config.NETLIFY_AUTH_TOKEN,
               "--message", "RedCarPet daily build"]
        ok, out = _run(cmd)

    elif target == "cloudflare":
        if not (config.CLOUDFLARE_API_TOKEN and config.CF_PAGES_PROJECT):
            print("CLOUDFLARE_API_TOKEN/CF_PAGES_PROJECT 미설정 - 건너뜀")
            return None
        env = {**os.environ, "CLOUDFLARE_API_TOKEN": config.CLOUDFLARE_API_TOKEN}
        cmd = ["npx", "-y", "wrangler", "pages", "deploy", ddir,
               "--project-name", config.CF_PAGES_PROJECT, "--commit-dirty=true"]
        ok, out = _run(cmd, env=env)
    else:
        print("알 수 없는 DEPLOY_TARGET:", target)
        return None

    print("자동 배포", "성공" if ok else "실패")
    return ok


if __name__ == "__main__":
    sys.exit(0 if deploy() else 1)
