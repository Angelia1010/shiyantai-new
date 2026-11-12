; 标准台校验系统 安装包脚本（Inno Setup 6）。
; 不要直接编译本文件：用 build_installer.ps1 打包，它会准备好 StageDir 中的全部内容并传入下面的参数。

#define AppName "标准台校验系统"
#define AppNameEn "BenchCheck"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef StageDir
  #error 请用 build_installer.ps1 打包（缺少 StageDir）
#endif
#ifndef OutputDir
  #define OutputDir "output"
#endif

[Setup]
AppId={{6E2B9C1A-4F3D-4B8E-9A61-3C7D5E2F8B10}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=503 标准试验台
DefaultDirName={autopf}\{#AppNameEn}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#OutputDir}
OutputBaseFilename={#AppNameEn}-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
MinVersion=10.0
WizardStyle=modern
UninstallDisplayName={#AppName}
UninstallDisplayIcon={app}\python\python.exe
CloseApplications=no

[Languages]
#ifdef ChineseIsl
Name: "chs"; MessagesFile: "{#ChineseIsl}"
#else
Name: "en"; MessagesFile: "compiler:Default.isl"
#endif

[Types]
Name: "standard"; Description: "标准安装"
Name: "custom"; Description: "自定义安装"; Flags: iscustom

[Components]
Name: "main"; Description: "标准台校验系统（必需）"; Types: standard custom; Flags: fixed
Name: "llm"; Description: "智能助手（需要另外安装 Ollama 与大模型，见安装目录 app\DeepSeek-model 说明）"; Types: custom
Name: "amesim"; Description: "AMESim 仿真服务（需要本机已安装 AMESim）"; Types: custom

[Tasks]
Name: "lan"; Description: "允许局域网内其他电脑通过浏览器访问（会在防火墙中打开端口）"; Flags: unchecked
Name: "desktopicon"; Description: "在桌面创建快捷方式"

[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[INI]
Filename: "{app}\打开标准台校验系统.url"; Section: "InternetShortcut"; Key: "URL"; String: "http://localhost:{code:GetPort}/"

[Icons]
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\打开标准台校验系统.url"; Tasks: desktopicon
Name: "{group}\打开{#AppName}"; Filename: "{app}\打开标准台校验系统.url"
Name: "{group}\启动服务"; Filename: "{app}\启动服务.bat"
Name: "{group}\停止服务"; Filename: "{app}\停止服务.bat"
Name: "{group}\重启服务"; Filename: "{app}\重启服务.bat"
Name: "{group}\服务状态"; Filename: "{app}\服务状态.bat"
Name: "{group}\打开数据与日志目录"; Filename: "{commonappdata}\{#AppNameEn}"
Name: "{group}\卸载{#AppName}"; Filename: "{uninstallexe}"

[Run]
Filename: "{app}\python\python.exe"; Parameters: """{app}\installer_tools.py"" --home ""{commonappdata}\{#AppNameEn}"" configure {code:ConfigureArgs}"; StatusMsg: "正在写入配置…"; Flags: runhidden waituntilterminated
Filename: "{app}\python\python.exe"; Parameters: """{app}\installer_tools.py"" install-task"; StatusMsg: "正在注册开机自动运行…"; Flags: runhidden waituntilterminated
Filename: "{app}\python\python.exe"; Parameters: """{app}\installer_tools.py"" start"; StatusMsg: "正在启动服务…"; Flags: runhidden waituntilterminated
Filename: "{app}\python\python.exe"; Parameters: """{app}\installer_tools.py"" wait-ready --timeout 120"; StatusMsg: "正在等待服务就绪（首次启动约需半分钟）…"; Flags: runhidden waituntilterminated
Filename: "http://localhost:{code:GetPort}/"; Description: "打开{#AppName}"; Flags: shellexec postinstall nowait skipifsilent

[UninstallDelete]
Type: files; Name: "{app}\home.txt"
Type: files; Name: "{app}\打开标准台校验系统.url"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\python"

[Code]
var
  SettingsPage: TInputQueryWizardPage;
  AmePage: TInputDirWizardPage;
  Upgrading: Boolean;

function HomeDir(): String;
begin
  Result := ExpandConstant('{commonappdata}\{#AppNameEn}');
end;

function ExistingPort(): String;
var
  Lines: TArrayOfString;
  I: Integer;
begin
  Result := '8080';
  if LoadStringsFromFile(HomeDir() + '\.env', Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
      if Pos('GATEWAY_PORT=', Lines[I]) = 1 then
        Result := Trim(Copy(Lines[I], 14, 10));
end;

procedure InitializeWizard();
begin
  Upgrading := FileExists(HomeDir() + '\.env');
  SettingsPage := CreateInputQueryPage(wpSelectTasks, '登录与访问设置',
    '设置登录密码和网页端口',
    '登录用户名为 admin。' + #13#10 +
    '浏览器访问地址为 http://本机地址:端口/。' +
    #13#10 + #13#10 +
    '升级安装时密码可以留空，表示保留原来的密码。');
  SettingsPage.Add('登录密码（至少 6 位）：', True);
  SettingsPage.Add('再次输入密码：', True);
  SettingsPage.Add('网页端口：', False);
  SettingsPage.Values[2] := ExistingPort();

  AmePage := CreateInputDirPage(SettingsPage.ID, 'AMESim 安装目录',
    '选择本机 AMESim 的安装目录',
    'AMESim 仿真服务使用 AMESim 自带的 Python（目录下应有 sys\python\win64\python.exe）。', False, '');
  AmePage.Add('AMESim 安装目录：');
  AmePage.Values[0] := GetEnv('AME');
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := (PageID = AmePage.ID) and (not WizardIsComponentSelected('amesim'));
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Port: Integer;
begin
  Result := True;
  if CurPageID = SettingsPage.ID then
  begin
    if (SettingsPage.Values[0] = '') and (not Upgrading) then
    begin
      MsgBox('请设置登录密码。', mbError, MB_OK);
      Result := False;
    end
    else if (SettingsPage.Values[0] <> '') and (Length(SettingsPage.Values[0]) < 6) then
    begin
      MsgBox('密码至少 6 位。', mbError, MB_OK);
      Result := False;
    end
    else if SettingsPage.Values[0] <> SettingsPage.Values[1] then
    begin
      MsgBox('两次输入的密码不一致。', mbError, MB_OK);
      Result := False;
    end
    else
    begin
      Port := StrToIntDef(Trim(SettingsPage.Values[2]), 0);
      if (Port < 1024) or (Port > 65535) then
      begin
        MsgBox('端口应为 1024–65535 之间的数字，一般用 8080。', mbError, MB_OK);
        Result := False;
      end;
    end;
  end
  else if (CurPageID = AmePage.ID) and WizardIsComponentSelected('amesim') then
  begin
    if not FileExists(AddBackslash(AmePage.Values[0]) + 'sys\python\win64\python.exe') then
      Result := MsgBox('该目录下没有找到 sys\python\win64\python.exe，AMESim 服务可能无法启动。仍然继续吗？',
                       mbConfirmation, MB_YESNO) = IDYES;
  end;
end;

function GetPort(Param: String): String;
begin
  if SettingsPage <> nil then
    Result := Trim(SettingsPage.Values[2])
  else
    Result := ExistingPort();
end;

{ 密码写到临时文件交给配置工具（读取后即删除），不出现在命令行参数中 }
function ConfigureArgs(Param: String): String;
var
  PwFile: String;
begin
  Result := '--port ' + GetPort('');
  if SettingsPage.Values[0] <> '' then
  begin
    PwFile := ExpandConstant('{tmp}\bench_pw.txt');
    SaveStringToFile(PwFile, SettingsPage.Values[0], False);
    Result := Result + ' --password-file "' + PwFile + '"';
  end;
  if WizardIsTaskSelected('lan') then
    Result := Result + ' --lan';
  if WizardIsComponentSelected('llm') then
    Result := Result + ' --llm';
  if WizardIsComponentSelected('amesim') then
    Result := Result + ' --amesim --ame "' + AmePage.Values[0] + '"';
end;

{ 升级：覆盖文件前先停止正在运行的旧版本 }
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
  Tools, Py: String;
begin
  Result := '';
  Tools := ExpandConstant('{app}\installer_tools.py');
  Py := ExpandConstant('{app}\python\python.exe');
  if FileExists(Tools) and FileExists(Py) then
    Exec(Py, '"' + Tools + '" stop', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;

{ 卸载：停止服务、删除开机任务与防火墙规则；询问是否同时删除数据 }
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Code: Integer;
  Args: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    Args := '"' + ExpandConstant('{app}\installer_tools.py') + '" --home "' + HomeDir() + '" uninstall';
    if MsgBox('是否同时删除数据？' + #13#10 + #13#10 +
              '包括诊断记录、日志、自己建的仿真模型和设置（' + HomeDir() + '）。' + #13#10 +
              '选“否”则保留，重新安装后可以继续使用。', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      Args := Args + ' --purge';
    Exec(ExpandConstant('{app}\python\python.exe'), Args, '', SW_HIDE, ewWaitUntilTerminated, Code);
  end;
end;
