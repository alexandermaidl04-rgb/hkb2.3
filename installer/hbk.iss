#define AppName "HBK Holzbau Kalkulation"
#define AppVersion "2.3.0"

[Setup]
AppId={{A3C1E5B2-7D4F-4C8A-9B21-5E0F6D7A1C33}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\HBK
DefaultGroupName=HBK
OutputDir=..\dist-installer
OutputBaseFilename=HBK-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\hbk\assets\HBK.ico
UninstallDisplayIcon={app}\HBK.exe
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayName={#AppName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknüpfung erstellen"; GroupDescription: "Zusätzliche Symbole:"

[Files]
Source: "..\dist\HBK\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\HBK"; Filename: "{app}\HBK.exe"
Name: "{autodesktop}\HBK"; Filename: "{app}\HBK.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\HBK.exe"; Description: "HBK jetzt starten"; Flags: nowait postinstall skipifsilent
