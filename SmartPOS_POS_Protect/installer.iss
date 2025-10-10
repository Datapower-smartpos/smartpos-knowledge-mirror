[Setup]
AppName=SmartPOS POS-Protect
AppVersion=1.1.0-test
DefaultDirName={sd}\AI\SmartPOS\Protect
DisableDirPage=no


[Files]
Source: "pos_collector_healer_core.py"; DestDir: "{app}"
Source: "run_pos_collector_healer.py"; DestDir: "{app}"
Source: "smartpos_tray.ps1"; DestDir: "{app}"
Source: "config.json"; DestDir: "{app}"
Source: "profiles\\etw\\*.*"; DestDir: "{app}\\profiles\\etw"
Source: "eventlog_export\\*.*"; DestDir: "{app}\\eventlog_export"
Source: "*.ps1"; DestDir: "{app}"
Source: "*.reg"; DestDir: "{app}"
Source: "watchdog.xml"; DestDir: "{app}"


[Code]
var ApiKey: string;


function InitializeSetup(): Boolean;
begin
if not FileExists(ExpandConstant('{cmd}\\python.exe')) then begin
if MsgBox('Python не найден в PATH. Продолжить установку без запуска службы?', mbConfirmation, MB_YESNO) = IDNO then
Result := False
else Result := True;
end else Result := True;
end;


function NextButtonClick(CurPageID: Integer): Boolean;
begin
if CurPageID = wpSelectDir then begin
ApiKey := InputBox('API Key','Введите X-API-Key для локального API','CHANGE_ME');
if Length(ApiKey) < 8 then begin
MsgBox('Ключ слишком короткий.', mbError, MB_OK);
Result := False;
exit;
end;
end;
Result := True;
end;


procedure CurStepChanged(CurStep: TSetupStep);
var f: string;
begin
if CurStep=ssPostInstall then begin
f := ExpandConstant('{app}\\config.json');
StringChangeEx(ApiKey,'\\','\\\\',True);
SaveStringToFile(f, StringChange(LoadStringFromFile(f), 'CHANGE_ME', ApiKey), False);
end;
end;


[Run]
Filename: "powershell"; Parameters: "-ExecutionPolicy Bypass -File \"{app}\\profiles\\etw\\apply_etw_profile.ps1\" -Profile BASE"; Flags: runhidden
Filename: "powershell"; Parameters: "-ExecutionPolicy Bypass -File \"{app}\\enable_wer.ps1\""; Flags: runhidden
Filename: "powershell"; Parameters: "-ExecutionPolicy Bypass -File \"{app}\\enable_etw.ps1\""; Flags: runhidden
Filename: "schtasks"; Parameters: "/Create /TN SmartPOS_Watchdog /XML {app}\\watchdog.xml /F"; Flags: runhidden