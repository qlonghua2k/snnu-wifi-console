param()

$ErrorActionPreference = "SilentlyContinue"

& wmic process where "commandline like '%\\web\\app.py%'" call terminate | Out-Null
