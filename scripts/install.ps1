<#
  ZapretTG — установка одной командой (PowerShell):
    irm https://raw.githubusercontent.com/tendo432/ZapretTG/main/scripts/install.ps1 | iex

  Скачивает последний portable-релиз с GitHub, ставит в C:\Program Files\ZapretTG,
  по вашему согласию добавляет узкие исключения Защитника, создаёт ярлыки и запускает программу.
#>
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Repo = 'tendo432/ZapretTG'

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Admin)) {
    Write-Host 'Нужны права администратора — открываю окно с запросом UAC...' -ForegroundColor Yellow
    $cmd = "irm https://raw.githubusercontent.com/$Repo/main/scripts/install.ps1 | iex"
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -NoExit -Command `"$cmd`""
    return
}

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Write-Host ''
Write-Host '  ZapretTG — zapret + Telegram прокси + DNS для нейросетей' -ForegroundColor Magenta
Write-Host ''

$dest = Join-Path $env:ProgramFiles 'ZapretTG'
$data = Join-Path $env:ProgramData 'ZapretTG'

Write-Host '[1/5] Ищу последнюю версию...'
$rel = Invoke-RestMethod "https://api.github.com/repos/$Repo/releases/latest" -Headers @{ 'User-Agent' = 'ZapretTG-installer' }
$asset = $rel.assets | Where-Object { $_.name -like '*portable.zip' } | Select-Object -First 1
if (-not $asset) { throw 'В релизе не найден portable.zip' }
Write-Host "      версия $($rel.tag_name)"

Write-Host '[2/5] Исключения Защитника Windows (необязательно)'
Write-Host '      Защитник иногда удаляет winws.exe и драйвер WinDivert как «HackTool» — тогда обход не работает.'
Write-Host '      Можно исключить ТОЛЬКО две папки bin с этими файлами (вся остальная программа проверяется как обычно):'
$binApp  = Join-Path $dest '_internal\resources\zapret\bin'
$binData = Join-Path $data 'zapret\bin'
Write-Host "        $binApp"
Write-Host "        $binData"
$ans = 'n'
if ($env:ZAPRETTG_DEFENDER -eq '1') { $ans = 'y' } else { try { $ans = Read-Host '      Добавить эти папки в исключения? [y/N]' } catch {} }
if ($ans -match '^(y|д|yes|да)$') {
    try { Add-MpPreference -ExclusionPath $binApp, $binData -ErrorAction Stop; Write-Host '      добавлено' -ForegroundColor Green }
    catch { Write-Host '      не удалось (другой антивирус или «Защита от подделки») — можно добавить позже кнопкой в программе' -ForegroundColor Yellow }
} else { Write-Host '      пропущено — если обход перестанет работать, добавьте позже: вкладка «Проверка» в программе' }

Write-Host '[3/5] Скачиваю...'
$tmp = Join-Path $env:TEMP "zaprettg-$([guid]::NewGuid().ToString('N')).zip"
Invoke-WebRequest $asset.browser_download_url -OutFile $tmp -UseBasicParsing

Write-Host '[4/5] Устанавливаю в' $dest
Get-Process ZapretTG -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process winws -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
New-Item -ItemType Directory -Path $dest -Force | Out-Null
Expand-Archive -Path $tmp -DestinationPath $dest -Force
Remove-Item $tmp -Force
# если в архиве есть вложенная папка ZapretTG — поднять содержимое
$inner = Join-Path $dest 'ZapretTG'
if ((Test-Path $inner) -and -not (Test-Path (Join-Path $dest 'ZapretTG.exe'))) {
    Get-ChildItem $inner | Move-Item -Destination $dest -Force
    Remove-Item $inner -Recurse -Force
}
Get-ChildItem $dest -Recurse | Unblock-File -ErrorAction SilentlyContinue
$exe = Join-Path $dest 'ZapretTG.exe'

Write-Host '[5/5] Создаю ярлыки...'
$sh = New-Object -ComObject WScript.Shell
foreach ($lnkPath in @(
        (Join-Path ([Environment]::GetFolderPath('CommonStartMenu')) 'Programs\ZapretTG.lnk'),
        (Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'ZapretTG.lnk'))) {
    $l = $sh.CreateShortcut($lnkPath); $l.TargetPath = $exe; $l.WorkingDirectory = $dest; $l.Save()
}

Write-Host ''
Write-Host "Готово! ZapretTG $($rel.tag_name) установлен в $dest" -ForegroundColor Green
Write-Host 'Удаление: irm https://raw.githubusercontent.com/tendo432/ZapretTG/main/scripts/uninstall.ps1 | iex'
Start-Process $exe
