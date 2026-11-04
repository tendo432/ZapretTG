<#
  ZapretTG — удаление (для установки через install.ps1):
    irm https://raw.githubusercontent.com/tendo432/ZapretTG/main/scripts/uninstall.ps1 | iex
  Возвращает DNS, удаляет автозапуск, службы zapret/WinDivert, ярлыки и файлы программы.
#>
$ErrorActionPreference = 'Continue'
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal $id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    $cmd = 'irm https://raw.githubusercontent.com/tendo432/ZapretTG/main/scripts/uninstall.ps1 | iex'
    Start-Process powershell -Verb RunAs -ArgumentList "-NoProfile -ExecutionPolicy Bypass -NoExit -Command `"$cmd`""
    return
}
$dest = Join-Path $env:ProgramFiles 'ZapretTG'
$data = Join-Path $env:ProgramData 'ZapretTG'
$exe = Join-Path $dest 'ZapretTG.exe'
if (Test-Path $exe) {
    Write-Host 'Возвращаю DNS и удаляю службы...'
    Start-Process $exe -ArgumentList '--cleanup' -Wait
}
Get-Process ZapretTG, winws -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 800
Remove-Item (Join-Path ([Environment]::GetFolderPath('CommonStartMenu')) 'Programs\ZapretTG.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item (Join-Path ([Environment]::GetFolderPath('CommonDesktopDirectory')) 'ZapretTG.lnk') -Force -ErrorAction SilentlyContinue
Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue
$ans = Read-Host 'Удалить настройки и логи (C:\ProgramData\ZapretTG)? [y/N]'
if ($ans -match '^(y|д)') { Remove-Item $data -Recurse -Force -ErrorAction SilentlyContinue }
try { Remove-MpPreference -ExclusionPath $dest, $data -ErrorAction SilentlyContinue } catch {}
Write-Host 'ZapretTG удалён.' -ForegroundColor Green
