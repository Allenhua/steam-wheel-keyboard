# 打包成 dist\SteamWheelKeyboard\SteamWheelKeyboard.exe（保留你已有的 config.json 和 user.json）
# 注意：开了 Windows "智能应用控制" 的电脑会拦截这种没有签名的新 exe。推荐改用
#   pythonw.exe + main.py 的方式启动（见 README），这个脚本只在你的电脑允许未签名程序时才有用。
# 用法：在本目录运行  powershell -ExecutionPolicy Bypass -File build_exe.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

$out = "dist\SteamWheelKeyboard"
$keep = @{}
foreach ($f in @("config.json", "data\user.json")) {
    if (Test-Path "$out\$f") { $keep[$f] = Get-Content "$out\$f" -Raw -Encoding UTF8 }
}
Get-Process SteamWheelKeyboard -ErrorAction SilentlyContinue | Stop-Process -Force

& $py -m PyInstaller --noconfirm --windowed --name SteamWheelKeyboard `
    --exclude-module jieba --exclude-module pypinyin --exclude-module tkinter --exclude-module sdl3 `
    --distpath dist --workpath build_tmp --specpath build_tmp main.py
New-Item -ItemType Directory -Force "$out\data" | Out-Null
Copy-Item data\dict.db "$out\data\dict.db" -Force      # 只带运行时词库；dict.txt 是源文件，不需要
Copy-Item README.md $out -Force
Remove-Item build_tmp -Recurse -Force -ErrorAction SilentlyContinue

foreach ($f in $keep.Keys) {
    New-Item -ItemType Directory -Force (Split-Path "$out\$f") | Out-Null
    [IO.File]::WriteAllText((Join-Path $PWD "$out\$f"), $keep[$f], (New-Object Text.UTF8Encoding($false)))
}
Write-Host "完成：$out\SteamWheelKeyboard.exe"
