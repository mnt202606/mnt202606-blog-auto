Set-Location "C:\Users\LG\Desktop\blog_auto\claude"
$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("PATH","User")
$prompt = Get-Content -Raw "daily_shorts_prompt.txt"
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content "daily_shorts_log.txt" "`n===== RUN START $timestamp ====="
claude -p "$prompt" --dangerously-skip-permissions *>> "daily_shorts_log.txt"
Add-Content "daily_shorts_log.txt" "===== RUN END $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ====="
