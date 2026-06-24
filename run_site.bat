@echo off
REM RedCar Pet 일일 웹사이트 빌드 (Windows 작업 스케줄러용)
REM 매일 오전 9시(KST) 실행 → 수집·1차·2차 심층·윤리검증 → web_sample.html 재생성
cd /d "D:\alcohol studies\redcarpet"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1
if not exist logs mkdir logs
echo ===== %DATE% %TIME% 빌드 시작 ===== >> "logs\daily_build.log"
python build_site.py >> "logs\daily_build.log" 2>&1
echo ===== %DATE% %TIME% 빌드 종료 (exit %ERRORLEVEL%) ===== >> "logs\daily_build.log"
