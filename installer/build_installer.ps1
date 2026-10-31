<#
.SYNOPSIS
    本地一键生成 Windows 安装程序（Inno Setup）。

.DESCRIPTION
    1) 用 build_portable.py 产出 onedir 便携版（dist\BilibiliDownloader\）。
    2) 下载 Windows ffmpeg 到 dist\BilibiliDownloader\bin\（内置，离线可用）。
    3) 用 iscc 编译 installer\installer.iss -> dist\BilibiliDownloader-Setup-<ver>.exe。

.PARAMETER Version
    安装包版本号。缺省时取 git describe --tags（去掉 v 前缀），再不行回退 0.0.0。

.EXAMPLE
    .\installer\build_installer.ps1
    .\installer\build_installer.ps1 -Version 1.2.3

.NOTES
    前置依赖：
      - Python 环境已装好项目依赖（含 auto-py-to-exe / pyinstaller / -r requirements.txt）。
      - 已安装 Inno Setup 6，且 ISCC.exe 在 PATH，或位于默认安装目录
        C:\Program Files (x86)\Inno Setup 6\ISCC.exe。
        下载：https://jrsoftware.org/isdl.php
#>
param(
    [string]$Version = ""
)

$ErrorActionPreference = "Stop"

# 项目根 = 本脚本所在 installer/ 的上级
$Root = Split-Path -Parent $MyInvocation.MyCommand.Definition | Split-Path -Parent
Push-Location $Root
try {
    # ---- 版本号 ----
    if (-not $Version) {
        try { $Version = (git describe --tags --always 2>$null).Trim() } catch { }
    }
    if (-not $Version) { $Version = "0.0.0" }
    $Version = $Version -replace '^v', ''
    if ($Version -notmatch '^\d+(\.\d+){0,3}$') {
        Write-Host "版本号 '$Version' 不是 Inno Setup 支持的数字格式，回退到 0.0.0"
        $Version = "0.0.0"
    }
    Write-Host "==> 版本号: $Version"

    # ---- 1. 构建 onedir 便携版 ----
    Write-Host "==> [1/3] 构建 onedir (build_portable.py)"
    python build_portable.py
    $PortableDir = Join-Path $Root "dist\BilibiliDownloader"
    $ExePath = Join-Path $PortableDir "BilibiliDownloader.exe"
    if (-not (Test-Path $ExePath)) {
        throw "未找到 $ExePath，便携版构建失败，请检查 build_portable.py 输出。"
    }

    # ---- 2. 下载并放入 ffmpeg（内置，离线可用）----
    # 只分发 ffmpeg.exe + ffprobe.exe 两个文件：
    #   - ffprobe：yt-dlp 的 FFmpegMetadata（内嵌元数据）强依赖，缺失会直接报错中断下载；
    #   - ffmpeg：音视频合并 / 格式转换必需。
    # 刻意不分发 ffplay.exe：它只是播放器，本项目与 yt-dlp 全程不调用，
    # 而静态构建里单个 ffplay.exe 就有 160MB+，白白撑大安装包。
    $BinDir = Join-Path $PortableDir "bin"
    $FfmpegExe = Join-Path $BinDir "ffmpeg.exe"
    $FfprobeExe = Join-Path $BinDir "ffprobe.exe"
    if ((Test-Path $FfmpegExe) -and (Test-Path $FfprobeExe)) {
        Write-Host "==> [2/3] ffmpeg 已存在于 bin/，跳过下载"
    } else {
        Write-Host "==> [2/3] 下载 Windows ffmpeg"
        # 候选源按优先级排列：gyan 的 essentials 构建体积小得多（不含 whisper/CUDA/
        # vmaf 等本项目用不到的库），BtbN 的 GPL 构建作为兜底。
        $Sources = @(
            @{ Url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"; Label = "gyan essentials" },
            @{ Url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"; Label = "BtbN win64-gpl" }
        )
        $hasCurl = Get-Command curl.exe -ErrorAction SilentlyContinue
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $Ok = $false
        foreach ($src in $Sources) {
            $Zip = Join-Path $env:TEMP "ffmpeg-win64.zip"
            try {
                Write-Host "       从 $($src.Label) 下载…"
                if ($hasCurl) {
                    & curl.exe -L -f -o "$Zip" "$($src.Url)"
                    if ($LASTEXITCODE -ne 0) { throw "curl 下载 ffmpeg 失败（退出码 $LASTEXITCODE）" }
                } else {
                    Invoke-WebRequest -Uri $src.Url -OutFile $Zip -UseBasicParsing
                }
                New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
                # 只提取归档内 bin/ffmpeg.exe 与 bin/ffprobe.exe（跳过 ffplay.exe）
                $archive = [System.IO.Compression.ZipFile]::OpenRead($Zip)
                try {
                    foreach ($entry in $archive.Entries) {
                        if ($entry.FullName -notmatch 'bin/([^/]+\.exe)$') { continue }
                        $name = $Matches[1]
                        if ($name -notin @("ffmpeg.exe", "ffprobe.exe")) { continue }
                        $dest = Join-Path $BinDir $name
                        # 注意：ExtractToFile 是 ZipFileExtensions 的扩展方法，PowerShell 无法通过
                        # [ZipFile]::ExtractToFile(...) 静态语法调用；改用条目流 + Stream.CopyTo 最稳妥。
                        $inStream = $entry.Open()
                        try {
                            $outStream = [System.IO.File]::Create($dest)
                            try { $inStream.CopyTo($outStream) } finally { $outStream.Dispose() }
                        } finally { $inStream.Dispose() }
                        Write-Host "       提取 $name"
                    }
                } finally { $archive.Dispose() }
                if ((Test-Path $FfmpegExe) -and (Test-Path $FfprobeExe)) {
                    $Ok = $true
                    break
                }
                throw "归档中未找到 ffmpeg.exe / ffprobe.exe"
            } catch {
                Write-Host "       源 $($src.Label) 失败：$($_.Exception.Message)"
            } finally {
                if (Test-Path $Zip) { Remove-Item $Zip -Force }
            }
        }
        if (-not $Ok) { throw "ffmpeg 下载失败，所有候选源均不可用" }
    }

    # ---- 3. 编译 Inno Setup 安装程序 ----
    $Iscc = "iscc"
    $IsccDefault = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
    if (Test-Path $IsccDefault) {
        $Iscc = $IsccDefault
    } else {
        # 兜底：在 Program Files (x86) 下查找任意 Inno Setup 安装目录
        # （例如 choco 装成 7.x 落到 “Inno Setup 7”，或版本目录名不同）
        $innoDir = Get-ChildItem -Path ${env:ProgramFiles(x86)} -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -like 'Inno Setup*' } |
            Sort-Object Name -Descending | Select-Object -First 1
        if ($innoDir) {
            $cand = Join-Path $innoDir.FullName 'ISCC.exe'
            if (Test-Path $cand) { $Iscc = $cand }
        }
    }
    # 语言文件兜底：若仓库 installer/Languages 下缺 .isl，则从已安装的 Inno Setup
    # 复制（通常装在 Languages 或 Languages\Unofficial 下）。
    # 说明：本仓库已自带 installer/Languages/ChineseSimplified.isl（随仓库版本管理），
    # 故正常 CI / 本地均走相对 include，不依赖 runner 装了什么语言包。
    $repoLangDir = Join-Path $Root "installer\Languages"
    $destLang = Join-Path $repoLangDir "ChineseSimplified.isl"
    if (-not (Test-Path $destLang)) {
        $innoBase = Split-Path -Parent $Iscc
        $srcCandidates = @(
            (Join-Path $innoBase "Languages\ChineseSimplified.isl"),
            (Join-Path $innoBase "Languages\Unofficial\ChineseSimplified.isl")
        )
        foreach ($src in $srcCandidates) {
            if (Test-Path $src) {
                if (-not (Test-Path $repoLangDir)) { New-Item -ItemType Directory -Force -Path $repoLangDir | Out-Null }
                Copy-Item -Path $src -Destination $destLang -Force
                Write-Host "从 $src 复制语言文件到 installer\Languages"
                break
            }
        }
    }
    if (-not (Get-Command $Iscc -ErrorAction SilentlyContinue)) {
        throw "未找到 iscc。请安装 Inno Setup 6 并将 ISCC.exe 加入 PATH，或确认默认安装路径。" +
              "下载：https://jrsoftware.org/isdl.php"
    }
    Write-Host "==> [3/3] 编译安装程序 (iscc)"
    $env:BD_VERSION = $Version
    $env:BD_VERSION_NUMERIC = $Version
    & "$Iscc" (Join-Path $Root "installer\installer.iss")
    if ($LASTEXITCODE -ne 0) { throw "iscc 编译失败（退出码 $LASTEXITCODE）" }

    $Out = Join-Path $Root "dist\BilibiliDownloader-Setup-$Version.exe"
    if (Test-Path $Out) {
        Write-Host "==> 完成: $Out"
    } else {
        # 找不到产物直接抛错，避免“iscc 静默失败 / OutputDir 配置错位”时
        # 仍被当成成功、release 里只出现便携版而漏掉安装版。
        throw "未找到安装包产物 $Out。请检查 installer.iss 的 OutputDir 是否指向 dist/，以及 iscc 是否真正执行成功。"
    }
} finally {
    Pop-Location
}
