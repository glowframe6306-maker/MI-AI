# PowerShell script to fix mojibake corruption in index.html

$filePath = "c:\Users\Administrator\MI-AI\frontend\index.html"
Write-Host "Reading file: $filePath"

$content = Get-Content $filePath -Encoding UTF8 -Raw

$replacements = @{
    'ðŸ''' = '👑'
    'ðŸ"Œ' = '📂'
    'ðŸ"¬' = '🗑'
    'ðŸ"œ' = '📄'
    'âŒ' = '✕'
    'ðŸŽ§' = '🎧'
}

foreach ($mojibake in $replacements.Keys) {
    $correct = $replacements[$mojibake]
    $count = ($content | Select-String -Pattern ([regex]::Escape($mojibake)) -AllMatches).Matches.Count
    if ($count -gt 0) {
        Write-Host "Replacing '$mojibake' ($count times) with '$correct'"
        $content = $content -replace ([regex]::Escape($mojibake)), $correct
    }
}

Write-Host "Writing fixed content..."
$content | Out-File $filePath -Encoding UTF8 -NoNewline

Write-Host "✓ Mojibake fixed successfully"
