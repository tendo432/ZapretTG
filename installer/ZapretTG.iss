; Установщик ZapretTG (Inno Setup 6). Собирается в GitHub Actions:
;   iscc /DAppVersion=1.2.0 installer\ZapretTG.iss
#ifndef AppVersion
  #define AppVersion "1.2.0"
#endif
#define AppName "ZapretTG"
#define AppExe "ZapretTG.exe"

[Setup]
AppId={{6E2B6F1C-3A5D-4C1E-9B7A-2F1D0C9E5A41}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=tendo432
AppPublisherURL=https://github.com/tendo432/ZapretTG
AppSupportURL=https://github.com/tendo432/ZapretTG/issues
AppUpdatesURL=https://github.com/tendo432/ZapretTG/releases
; путь без кириллицы и пробелов — так надёжнее для WinDivert
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=ZapretTG-Setup
SetupIconFile=..\build_assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ShowLanguageDialog=no

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Ярлык на рабочем столе"; GroupDescription: "Ярлыки:"
Name: "autostart"; Description: "Запускать вместе с Windows (свёрнуто в трей)"; GroupDescription: "Запуск:"
Name: "defender"; Description: "Добавить в исключения Защитника Windows (рекомендуется — иначе он может удалить winws.exe и WinDivert)"; GroupDescription: "Антивирус:"

[Files]
Source: "..\dist\ZapretTG\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Удалить {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Add-MpPreference -ExclusionPath '{app}','{commonappdata}\ZapretTG' -ErrorAction SilentlyContinue"""; Flags: runhidden; Tasks: defender; StatusMsg: "Добавление исключений Защитника..."
Filename: "{app}\{#AppExe}"; Parameters: "--autostart-on"; Flags: runhidden waituntilterminated; Tasks: autostart; StatusMsg: "Настройка автозапуска..."
Filename: "{app}\{#AppExe}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; вернуть DNS, удалить задачу автозапуска и службы zapret/WinDivert
Filename: "{app}\{#AppExe}"; Parameters: "--cleanup"; Flags: runhidden waituntilterminated; RunOnceId: "Cleanup"
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -Command ""Remove-MpPreference -ExclusionPath '{app}','{commonappdata}\ZapretTG' -ErrorAction SilentlyContinue"""; Flags: runhidden; RunOnceId: "Defender"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if MsgBox('Удалить также настройки и логи (C:\ProgramData\ZapretTG)?', mbConfirmation, MB_YESNO) = IDYES then
      DelTree(ExpandConstant('{commonappdata}\ZapretTG'), True, True, True);
end;
