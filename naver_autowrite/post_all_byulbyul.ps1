# 별별연예 글을 네이버 블로그 임시저장으로 순서대로 올립니다 (발행하지 않음).
# 사용: naver_autowrite 폴더에서 .\post_all_byulbyul.ps1 [blogId]
param([string]$BlogId = "mnt202606")
Get-ChildItem "$PSScriptRoot\byulbyul_content\*.json" | Sort-Object Name | ForEach-Object {
  Write-Host "임시저장: $($_.Name)"
  node "$PSScriptRoot\post_draft.js" $BlogId $_.FullName
  Start-Sleep -Seconds 5
}
