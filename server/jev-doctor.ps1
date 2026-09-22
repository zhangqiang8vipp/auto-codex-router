#!/usr/bin/env pwsh
# One-click Jev Codex Router self-check: readiness, auto state, scheduled task,
# today's counters and the log archive, with remediation hints for failures.
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = (Get-Command python -ErrorAction Stop).Source
& $python (Join-Path $here "jev_server.py") --doctor
exit $LASTEXITCODE
