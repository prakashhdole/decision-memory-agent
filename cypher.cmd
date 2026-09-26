@echo off
REM Shortcut: runs cypher.ps1 even though Windows blocks .ps1 scripts by default.
REM Usage:  .\cypher            (interactive shell)
REM         .\cypher "MATCH (n) RETURN count(n);"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0cypher.ps1" %*
