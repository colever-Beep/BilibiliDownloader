@echo off
setlocal
set "MODE=cli"
set "PAUSE_AT_END=0"

:: =====================================================================
::  默认始终排除项（逗号/空格分隔，支持通配符）。
::  这些一般为运行态/敏感文件；即便以后被误跟踪也不会被提交。
::  你可以在这里增删，或在 push 时选择「自定义排除项」临时追加。
:: =====================================================================
set "DEFAULT_EXCLUDE=cookies*.txt *.log history.txt test.txt download.log"

:: ---------- 前置检查 ----------
where git >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 git，请先安装并加入 PATH。
    goto :end
)
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [错误] 当前目录不是 Git 仓库，请在项目根目录运行本脚本。
    goto :end
)

:: ---------- 无参数 -> 交互菜单；有参数 -> 命令行模式 ----------
if "%~1"=="" (
    set "MODE=menu"
    goto :menu
)
goto :cli

:: ================= 交互菜单 =================
:menu
set "PAUSE_AT_END=1"
cls
echo ==================================================
echo   BiliDownloader Git 工具箱  (GitHub CLI)
echo ==================================================
echo.
echo   1. 提交并推送当前分支        push
echo   2. 重建并推送版本标签        tag
echo   3. 创建 GitHub Release       release
echo   4. 拉取最新代码              pull
echo   5. 查看状态                  status
echo   6. 查看最近提交              log
echo   7. 查看分支                  branch
echo   8. 同步远程(fetch+status)    sync
echo   0. 退出
echo.
set /p "CHOICE=请选择操作 [0-8]: "
if "%CHOICE%"=="1" (call :do_push_menu & goto :after_action)
if "%CHOICE%"=="2" (call :do_tag_prompt & goto :after_action)
if "%CHOICE%"=="3" (call :do_release_prompt & goto :after_action)
if "%CHOICE%"=="4" (call :do_pull & goto :after_action)
if "%CHOICE%"=="5" (call :do_status & goto :after_action)
if "%CHOICE%"=="6" (call :do_log & goto :after_action)
if "%CHOICE%"=="7" (call :do_branch & goto :after_action)
if "%CHOICE%"=="8" (call :do_sync & goto :after_action)
if "%CHOICE%"=="0" goto :end
echo 无效选择，请重试。
goto :menu

:: 菜单操作后暂停，避免查看类输出一闪而过
:after_action
echo.
echo 按任意键返回菜单...
pause >nul
goto :menu

:: ================= 命令行入口 =================
:cli
set "CMD=%~1"
if /i "%CMD%"=="push"    (call :do_push "%~2" & goto :end)
if /i "%CMD%"=="tag"     (call :do_tag "%~2" "%~3" & goto :end)
if /i "%CMD%"=="release" (call :do_release "%~2" "%~3" & goto :end)
if /i "%CMD%"=="pull"    (call :do_pull & goto :end)
if /i "%CMD%"=="status"  (call :do_status & goto :end)
if /i "%CMD%"=="log"     (call :do_log & goto :end)
if /i "%CMD%"=="branch"  (call :do_branch & goto :end)
if /i "%CMD%"=="sync"    (call :do_sync & goto :end)
echo 未知命令: %CMD%
echo 用法: push.cmd [push^|tag^|release^|pull^|status^|log^|branch^|sync] [参数]
echo   示例:
echo     push.cmd push "修复导航内联化"
echo     push.cmd tag v2.1.0 "Release v2.1.0"
echo     push.cmd release v2.1.0 "版本发布说明"
goto :end

:: ================= 子程序 =================

:: 交互式提交（带暂存方式选择 + 预览 + 确认 + 排除）
:do_push_menu
set "MSG="
set /p "MSG=提交说明 (可留空自动生成): "
echo.
echo [push] 暂存方式:
echo   1) 全部      (git add -A，遵守 .gitignore)
echo   2) 仅已跟踪  (git add -u，不新增未跟踪文件)
echo   3) 全部+自定义排除项
set /p "ADDSEL=选择 [默认1]: "
if "%ADDSEL%"=="2" (
    echo [push] 仅暂存已跟踪文件的改动...
    git add -u
) else (
    echo [push] 暂存所有改动 (受 .gitignore 约束)...
    git add -A
    if "%ADDSEL%"=="3" (
        set /p "EXCL=要额外排除的文件/通配符 (逗号或空格分隔, 如 cache/*.tmp build/): "
        call :apply_exclude "%EXCL%"
    )
)
call :apply_exclude "%DEFAULT_EXCLUDE%"
echo.
echo [push] 以下改动将被提交:
git status --short
echo.
set /p "CONFIRM=确认提交以上改动？[Y/n]: "
if /i "%CONFIRM%"=="n" (
    echo [push] 已取消，未提交任何内容。
    goto :eof
)
call :do_commit_push "%MSG%"
goto :eof

:: 命令行式提交（非交互，直接全部暂存并应用默认排除）
:do_push
set "MSG=%~1"
git add -A
call :apply_exclude "%DEFAULT_EXCLUDE%"
call :do_commit_push "%MSG%"
goto :eof

:: 提交并推送（被上面两个入口复用）
:do_commit_push
set "MSG=%~1"
if "%MSG%"=="" (
    for /f "tokens=*" %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyy-MM-dd_HHmm" 2^>nul') do set "MSG=update %%i"
)
if "%MSG%"=="" set "MSG=update"
git diff --cached --quiet >nul 2>&1
if not errorlevel 1 (
    echo [push] 没有已暂存的改动，跳过提交。
    goto :eof
)
echo [push] 提交: %MSG%
git commit -m "%MSG%"
for /f "delims=" %%b in ('git rev-parse --abbrev-ref HEAD 2^>nul') do set "BR=%%b"
if "%BR%"=="" (
    echo [push] 无法确定分支，使用默认推送。
    git push
) else (
    echo [push] 推送到 %BR%...
    git push origin %BR%
)
echo [push] 完成。
goto :eof

:: 将逗号/空格分隔的排除项从暂存区移除（不删文件）
:apply_exclude
set "LIST=%~1"
if "%LIST%"=="" goto :eof
set "LIST=%LIST:,= %"
git reset -q -- %LIST% 2>nul
echo [push] 已对以下项执行排除(若有匹配则不会提交): %LIST%
goto :eof

:do_tag
set "VER=%~1"
set "MSG=%~2"
if "%VER%"=="" (echo [tag] 未提供版本号，取消。 & goto :eof)
if "%MSG%"=="" set "MSG=Release %VER%"
echo [tag] 删除本地标签 %VER% (若不存在可忽略)
git tag -d %VER% 2>nul
echo [tag] 删除远程标签 %VER% (若不存在可忽略)
git push origin --delete %VER% 2>nul
echo [tag] 创建附注标签 %VER%: %MSG%
git tag -a %VER% -m "%MSG%"
echo [tag] 推送标签 %VER%
git push origin %VER%
echo [tag] 完成。
goto :eof

:do_tag_prompt
set "VER="
set "MSG="
set /p "VER=版本号 (如 v2.1.0): "
if "%VER%"=="" (echo [tag] 已取消。 & goto :eof)
set /p "MSG=标签备注 (留空用默认): "
call :do_tag "%VER%" "%MSG%"
goto :eof

:do_release
set "VER=%~1"
set "MSG=%~2"
if "%VER%"=="" (echo [release] 未提供版本号，取消。 & goto :eof)
if "%MSG%"=="" set "MSG=Release %VER%"
where gh >nul 2>&1
if errorlevel 1 (
    echo [release] 未检测到 gh (GitHub CLI)，仅创建并推送标签。
    call :do_tag "%VER%" "%MSG%"
    goto :eof
)
echo [release] 创建/重建标签...
call :do_tag "%VER%" "%MSG%"
echo [release] 删除已存在的 Release (若存在)...
gh release delete %VER% -y >nul 2>&1
echo [release] 创建 GitHub Release %VER%...
gh release create %VER% --title "%VER%" --notes "%MSG%"
echo [release] 完成。
goto :eof

:do_release_prompt
set "VER="
set "MSG="
set /p "VER=版本号 (如 v2.1.0): "
if "%VER%"=="" (echo [release] 已取消。 & goto :eof)
set /p "MSG=Release 说明 (留空用默认): "
call :do_release "%VER%" "%MSG%"
goto :eof

:do_pull
echo [pull] 拉取当前分支最新代码...
git pull
echo [pull] 完成。
goto :eof

:do_status
echo [status] 当前仓库状态:
git status
goto :eof

:do_log
echo [log] 最近 15 条提交:
git log --oneline -15
goto :eof

:do_branch
echo [branch] 本地与远程分支:
git branch -a
goto :eof

:do_sync
echo [sync] 获取远程更新...
git fetch --all --prune
echo [sync] 当前状态:
git status
goto :eof

:end
if "%PAUSE_AT_END%"=="1" (
    echo.
    echo 按任意键退出...
    pause >nul
)
endlocal
