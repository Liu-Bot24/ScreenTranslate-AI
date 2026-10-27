; Inno Setup script for 译取. Built by scripts/build_installer.ps1, which passes AppVersion and SourceDir.
; Installs per user (no admin). Settings, API keys and history live in %LOCALAPPDATA%\YiQu and are
; never part of the package; uninstalling leaves them in place.

#ifndef AppVersion
  #error AppVersion must be defined (run scripts/build_installer.ps1)
#endif
#ifndef SourceDir
  #error SourceDir must be defined (run scripts/build_installer.ps1)
#endif

[Setup]
AppId={{6F1C2B9E-3A57-4C1E-9B7D-2E8A41D3C0F5}
AppName=译取
AppVerName=译取 {#AppVersion}
AppVersion={#AppVersion}
AppPublisher=YiQu
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\YiQu
DefaultGroupName=译取
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=..\release
OutputBaseFilename=YiQu-Setup-{#AppVersion}
SetupIconFile=..\src\YiQu\Assets\YiQu.ico
UninstallDisplayIcon={app}\YiQu.exe
UninstallDisplayName=译取
WizardStyle=modern
ShowLanguageDialog=no
Compression=lzma2/ultra64
SolidCompression=yes
; The app keeps running in the tray when its window is closed; Restart Manager closes it before replacing files
; (the app exits on session-end requests). No AppMutex: it would stop setup before that step.

CloseApplications=force
RestartApplications=no

[Languages]
; Unofficial translation from jrsoftware/issrc (tag is-6_7_3), Files/Languages/Unofficial.
Name: "chinesesimp"; MessagesFile: "Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart"; Description: "开机时自动启动译取"; GroupDescription: "启动选项："; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\译取"; Filename: "{app}\YiQu.exe"
Name: "{autodesktop}\译取"; Filename: "{app}\YiQu.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "YiQu"; ValueData: """{app}\YiQu.exe"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\YiQu.exe"; Description: "{cm:LaunchProgram,译取}"; Flags: nowait postinstall skipifsilent

[Code]
// The uninstaller has no Restart Manager step, and the tray app hides instead of closing.
// Stop only copies running from this install folder before files are removed.
function InitializeUninstall(): Boolean;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
    '-NoProfile -NonInteractive -Command "$d = ''' + ExpandConstant('{app}') + '\''; ' +
    'Get-Process YiQu -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($d, [StringComparison]::OrdinalIgnoreCase) } | Stop-Process -Force; Start-Sleep -Milliseconds 500"',
    '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Result := True;
end;