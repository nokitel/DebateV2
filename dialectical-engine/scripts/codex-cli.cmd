@echo off
set "REPO_ROOT=%~dp0.."
set "LOCAL_CODEX=%REPO_ROOT%\node_modules\.bin\codex.cmd"
if exist "%LOCAL_CODEX%" (
  "%LOCAL_CODEX%" %*
  exit /b %ERRORLEVEL%
)

set "GLOBAL_CODEX=%APPDATA%\npm\node_modules\@openai\codex\bin\codex.js"
node "%GLOBAL_CODEX%" %*
