@echo off
setlocal
if "%~1"=="" (
  set CFG=target.example.toml
) else (
  set CFG=%~1
)
py -3 -m wise_miner "%CFG%"
