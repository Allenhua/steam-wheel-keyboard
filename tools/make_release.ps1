# 生成发行包 release\SteamWheelKeyboard-vX.Y.Z-win64.zip
# （exe + 词库 + 许可证；不包含任何个人设置 config.json / user.json；不动 dist\ 里你正在用的那份）
# 前提：已 python build_dict.py --download，且装了 pyinstaller。
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$ver = (& $py main.py --version | Select-Object -Last 1) -replace '.*\s', ''
$name = "SteamWheelKeyboard-v$ver-win64"
$work = "release\_build"
$stage = "release\$name"

Remove-Item $work, $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force release | Out-Null
& $py -m PyInstaller --noconfirm --windowed --name SteamWheelKeyboard `
    --exclude-module jieba --exclude-module pypinyin --exclude-module tkinter --exclude-module sdl3 `
    --distpath $work --workpath "$work\w" --specpath "$work\s" main.py
Move-Item "$work\SteamWheelKeyboard" $stage
New-Item -ItemType Directory -Force "$stage\data" | Out-Null
Copy-Item data\dict.db "$stage\data\dict.db"
Copy-Item LICENSE, NOTICE.md, README.md, README.en.md, config.example.json $stage
Copy-Item docs "$stage\docs" -Recurse
Remove-Item $work -Recurse -Force

$zip = "release\$name.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
Compress-Archive -Path $stage -DestinationPath $zip -CompressionLevel Optimal
Write-Host ("完成：{0}  ({1:N1} MB)" -f $zip, ((Get-Item $zip).Length / 1MB))
