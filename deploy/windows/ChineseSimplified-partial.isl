; 安装向导的中文界面文字（部分翻译）。
; 用法：MessagesFile: "compiler:Default.isl,ChineseSimplified-partial.isl"
; 以 Inno Setup 自带的英文 Default.isl 为底，这里覆盖安装向导上常见的文字，没有覆盖的仍显示英文。
; 有完整的中文语言文件（tools\innosetup\Languages\ChineseSimplified.isl）时打包脚本优先用完整的。

[LangOptions]
LanguageName=<7B80><4F53><4E2D><6587>
LanguageID=$0804

[Messages]
SetupAppTitle=安装
SetupWindowTitle=安装 - %1
UninstallAppTitle=卸载
UninstallAppFullTitle=%1 卸载
InformationTitle=信息
ConfirmTitle=确认
ErrorTitle=错误
SetupLdrStartupMessage=现在将安装 %1。是否继续？
ExitSetupTitle=退出安装
ExitSetupMessage=安装尚未完成。如果现在退出，程序将不会被安装。%n%n您可以以后再运行安装程序完成安装。%n%n是否退出安装？

ButtonBack=< 上一步(&B)
ButtonNext=下一步(&N) >
ButtonInstall=安装(&I)
ButtonOK=确定
ButtonCancel=取消
ButtonYes=是(&Y)
ButtonYesToAll=全是(&A)
ButtonNo=否(&N)
ButtonNoToAll=全否(&O)
ButtonFinish=完成(&F)
ButtonBrowse=浏览(&B)...
ButtonWizardBrowse=浏览(&R)...
ButtonNewFolder=新建文件夹(&M)

WelcomeLabel1=欢迎使用 [name] 安装向导
WelcomeLabel2=现在将在您的电脑上安装 [name/ver]。%n%n建议在继续之前关闭其他所有应用程序。

WizardSelectDir=选择安装位置
SelectDirDesc=[name] 要安装到哪里？
SelectDirLabel3=安装程序将把 [name] 安装到下面的文件夹。
SelectDirBrowseLabel=点击“下一步”继续。如果要选择其他文件夹，请点击“浏览”。
DirExistsTitle=文件夹已存在
DirExists=文件夹：%n%n%1%n%n已经存在。仍然要安装到这个文件夹吗？

WizardSelectComponents=选择组件
SelectComponentsDesc=要安装哪些组件？
SelectComponentsLabel2=勾选要安装的组件，取消不需要的组件。准备好后点击“下一步”。
FullInstallation=完全安装
CompactInstallation=简洁安装
CustomInstallation=自定义安装

WizardSelectTasks=选择附加任务
SelectTasksDesc=要执行哪些附加任务？
SelectTasksLabel2=选择安装 [name] 时要执行的附加任务，然后点击“下一步”。

WizardReady=准备安装
ReadyLabel1=安装程序已准备好在您的电脑上安装 [name]。
ReadyLabel2a=点击“安装”开始安装；如果要查看或修改设置，请点击“上一步”。
ReadyLabel2b=点击“安装”开始安装。
ReadyMemoDir=安装位置：
ReadyMemoType=安装类型：
ReadyMemoComponents=选择的组件：
ReadyMemoGroup=开始菜单文件夹：
ReadyMemoTasks=附加任务：

WizardPreparing=正在准备安装
PreparingDesc=安装程序正在准备在您的电脑上安装 [name]。

WizardInstalling=正在安装
InstallingLabel=正在您的电脑上安装 [name]，请稍候。

FinishedHeadingLabel=[name] 安装完成
FinishedLabelNoIcons=[name] 已安装到您的电脑上。
FinishedLabel=[name] 已安装到您的电脑上。可以通过已创建的快捷方式打开。
ClickFinish=点击“完成”退出安装程序。
RunEntryShellExec=打开 %1
RunEntryExec=运行 %1

StatusExtractFiles=正在解压文件...
StatusCreateIcons=正在创建快捷方式...
StatusCreateIniEntries=正在创建配置项...
StatusRunProgram=正在完成安装...
StatusRollback=正在撤销更改...

WizardUninstalling=卸载状态
StatusUninstalling=正在卸载 %1...
ConfirmUninstall=确定要完全删除 %1 及其所有组件吗？
UninstallStatusLabel=正在从您的电脑上删除 %1，请稍候。
UninstalledAll=%1 已从您的电脑上删除。
