; Inno Setup 安装脚本
; 将 build_portable.py 产出的 onedir（含内置 ffmpeg 的 bin/）打包为带中文向导的
; Windows 安装程序 BilibiliDownloader-Setup-<ver>.exe。
;
; 编译命令：iscc installer.iss   （需先安装 Inno Setup 6，并把 ISCC.exe 加入 PATH）
; 版本号通过环境变量 BD_VERSION 注入，缺省 0.0.0。

#encoding utf-8-bom

#define MyAppName "BilibiliDownloader"
#define MyAppVersion ReadEnv("BD_VERSION", "0.0.0")
#define MyAppPublisher "colever-Beep"
#define MyAppURL "https://github.com/colever-Beep/BilibiliDownloader"
#define MyAppExeName "BilibiliDownloader.exe"
; 便携版 onedir 目录（相对本脚本 installer/）：../dist/BilibiliDownloader
#define SourceDir "..\dist\BilibiliDownloader"

[Setup]
; AppId 必须唯一，用于覆盖安装 / 卸载识别（不同软件不可共用）
AppId={{6F3A1E2B-9C4D-4A8E-B1F2-7D3E5C9A0B1F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=output
OutputBaseFilename={#MyAppName}-Setup-{#MyAppVersion}
SetupIconFile=..\icon.ico
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
; 升级时已存在的目录不弹警告
DirExistsWarning=no

[Languages]
Name: "chinese"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "quicklaunchicon"; Description: "创建快速启动栏快捷方式"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 整个 onedir 目录（exe + _internal + bin/ffmpeg.exe 等）安装到 {app}
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
