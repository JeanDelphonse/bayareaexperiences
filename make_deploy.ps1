$source = 'C:\Users\jeand\OneDrive\Opts\bayareaexperiences'
$dest   = 'C:\Users\jeand\OneDrive\Opts\bayareaexperiences_deploy.zip'

$excludeDirs  = '__pycache__', '.git', 'instance', 'logs', 'marketing_agent', 'docs'
$excludeFiles = 'send_test_email.py', 'make_deploy.ps1', '.env.example'
$excludeExts  = '.pyc', '.db'

if (Test-Path $dest) { Remove-Item $dest }

Add-Type -Assembly 'System.IO.Compression.FileSystem'
$zip = [System.IO.Compression.ZipFile]::Open($dest, 'Create')

Get-ChildItem -Path $source -Recurse -File -Force | Where-Object {
    $rel   = $_.FullName.Substring($source.Length + 1)
    $parts = $rel -split [regex]::Escape('\')
    $skipDir  = $parts | Where-Object { $excludeDirs -contains $_ }
    $skipFile = $excludeFiles -contains $_.Name
    $skipExt  = $excludeExts -contains $_.Extension
    (-not $skipDir) -and (-not $skipFile) -and (-not $skipExt)
} | ForEach-Object {
    $entry = $_.FullName.Substring($source.Length + 1) -replace '\\', '/'
    [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $_.FullName, $entry)
}

$zip.Dispose()
Write-Host "Created: $dest"
