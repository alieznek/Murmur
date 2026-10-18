; Compile through build.py --installer after the bundled offline self-check passes.
#ifndef AppVersion
  #error AppVersion must be supplied by build.py
#endif

[Setup]
AppId={{5A7A0A36-A768-44D6-93B0-EAE4DDFDC267}
AppName=Murmur（译语）
AppVersion={#AppVersion}
AppVerName=Murmur（译语） {#AppVersion}
AppComments=屏幕识字与中英离线翻译工具
VersionInfoVersion={#NumericVersion}
VersionInfoDescription=Murmur（译语） 安装程序
DefaultDirName={localappdata}\Programs\Murmur
DefaultGroupName=Murmur（译语）
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible and not arm64
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename={#OutputName}
SetupIconFile=..\..\app-icon\translator.ico
UninstallDisplayIcon={app}\Murmur.exe
UninstallDisplayName=Murmur（译语） {#AppVersion}

WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

#include "obsolete-runtime.iss"

[Files]
Source: "{#BundleDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Murmur（译语）"; Filename: "{app}\Murmur.exe"; WorkingDir: "{app}"; AppUserModelID: "Murmur"
Name: "{group}\使用指南"; Filename: "{app}\guides\usage.md"
Name: "{group}\运行自检"; Filename: "{app}\运行自检.bat"; WorkingDir: "{app}"
Name: "{autodesktop}\Murmur（译语）"; Filename: "{app}\Murmur.exe"; WorkingDir: "{app}"; Tasks: desktopicon; AppUserModelID: "Murmur"

[Run]
Filename: "{app}\Murmur.exe"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,Murmur（译语）}"; Flags: nowait postinstall skipifsilent
