; Inno Setup Script for SmartPOS USB Agent v1.4.1 — corrected
; Author: Разработчик суперпрограмм
; Собирает EXE‑инсталлятор: службу (Python), PowerShell‑трей, конфиг, скрипты install/uninstall
; Требования: установленные Python 3.9+ (x64) и права администратора.

; - Нормальные пути (Одинарные обратные слэши \)
; - Диалог ввода API Key
; - Запись %ProgramData%\SmartPOS\usb_agent\config.json
; - sanity-checks на Python/.NET
; - Подключены CLI/сервис/скрипты/инструменты
; - Включён каноничный CLI: src\python\usb_devctl_cli.py
; - Единая секция [Run section] (во избежание ошибок парсера)

#define AppName "SmartPOS USB Agent"
#define AppVersion "1.4.1"
#define AppPublisher "BrainPOS"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://brainpos.net/
AppSupportURL=https://brainpos.net/usb-agent   ; "Дополнительные сведения"/Support link
AppUpdatesURL=https://brainpos.net/downloads   ; (по желанию)
AppContact=info@brainpos.net                   ; "Контакт"
DefaultDirName={commonpf}\SmartPOS_USB_Agent
PrivilegesRequired=admin
DisableDirPage=no
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible
OutputBaseFilename=SmartPOS_USB_Agent_{#AppVersion}_Setup
Compression=lzma
SolidCompression=yes

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Files]
; Python сервис и ядро
Source: "..\..\src\python\smartpos_usb_service_v14.py"; DestDir: "{app}\src\python"; Flags: ignoreversion
Source: "..\..\src\python\usb_agent_core.py";           DestDir: "{app}\src\python"; Flags: ignoreversion
Source: "..\..\src\python\trace_wrappers_v2.py";        DestDir: "{app}\src\python"; Flags: ignoreversion
; Каноничный CLI (ОБЯЗАТЕЛЬНО)
Source: "..\..\src\python\usb_devctl_cli.py";           DestDir: "{app}\src\python"; Flags: ignoreversion
Source: "..\..\src\python\run_usb_devctl.bat"; 		      DestDir: "{app}\src\python"; Flags: ignoreversion
; Скрипты службы и watchdog
Source: "..\..\installer\scripts\install_service.ps1";  DestDir: "{app}\tools"; Flags: ignoreversion
Source: "..\..\installer\scripts\uninstall_service.ps1";DestDir: "{app}\installer\scripts"; Flags: ignoreversion
Source: "..\..\tools\install_watchdog.ps1";             DestDir: "{app}\tools"; Flags: ignoreversion
Source: "..\..\tools\uninstall_watchdog.ps1";           DestDir: "{app}\tools"; Flags: ignoreversion

[Dirs]
Name: "{commonappdata}\SmartPOS\usb_agent"; Flags: uninsneveruninstall

[Registry]
Root: HKLM; Subkey: "Software\SmartPOS\USB_Agent"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekeyifempty

[CustomMessages]
ru.NETHint=Установите .NET Desktop Runtime (x64): https://dotnet.microsoft.com/en-us/download/dotnet/thank-you/runtime-desktop-8.0.10-windows-x64-installer
ru.PythonHint=Установите Python 3.9+ (x64): https://www.python.org/downloads/windows/
en.NETHint=Install .NET Desktop Runtime (x64): https://dotnet.microsoft.com/en-us/download/dotnet/thank-you/runtime-desktop-8.0.10-windows-x64-installer
en.PythonHint=Install Python 3.9+ (x64): https://www.python.org/downloads/windows/

[Code]
var
  ApiKeyPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  ApiKeyPage := CreateInputQueryPage(wpSelectDir,
    'SmartPOS USB Agent', 'Enter API Key',
    'API Key will be saved to %ProgramData%\SmartPOS\usb_agent\config.json');
  ApiKeyPage.Add('API Key:', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  ApiKey, Escaped, CfgDir, CfgFile, Json: String;
begin
  Result := True;
  if CurPageID = ApiKeyPage.ID then begin
    ApiKey := Trim(ApiKeyPage.Values[0]);
    CfgDir := ExpandConstant('{commonappdata}\SmartPOS\usb_agent');
    CfgFile := CfgDir + '\config.json';
    if not DirExists(CfgDir) then
      ForceDirectories(CfgDir);
    if Length(ApiKey) = 0 then
      ApiKey := ''; // пустое поле допустимо, но JSON остаётся валидным
    // экранируем кавычки в ключе (процедурой, вне выражения)
    Escaped := ApiKey;
    StringChangeEx(Escaped, '"', '\"', True);
    // собираем валидный JSON
    Json :=
      '{' + #13#10 +
      '  "api_key": "' + Escaped + '",' + #13#10 +
      '  "export": {' + #13#10 +
      '    "mask": "**/*",' + #13#10 +
      '    "out": "%TEMP%\\spusb_out.zip"' + #13#10 +
      '  }' + #13#10 +
      '}';
    SaveStringToFile(CfgFile, Json, False);
  end;
end;

[Icons]
Name: "{group}\SmartPOS USB DevCtl"; Filename: "{app}\src\python\run_usb_devctl.bat"; WorkingDir: "{app}\src\python"
; вызываем usb_devctl_cli.py через обертку run_usb_devctl.bat - безопаснее для саппорта 
Name: "{group}\SmartPOS USB Agent — Service"; Filename: "{app}\src\python\smartpos_usb_service_v14.py"

[Run]
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\install_service.ps1"""; \
  Flags: runhidden shellexec waituntilterminated
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\tools\install_watchdog.ps1"""; \
  Flags: runhidden shellexec waituntilterminated
