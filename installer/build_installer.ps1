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
    $BinDir = Join-Path $PortableDir "bin"
    $FfmpegExe = Join-Path $BinDir "ffmpeg.exe"
    if (Test-Path $FfmpegExe) {
        Write-Host "==> [2/3] ffmpeg 已存在于 bin/，跳过下载"
    } else {
        Write-Host "==> [2/3] 下载 Windows ffmpeg (BtbN win64-gpl)"
        $Url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
        $Zip = Join-Path $env:TEMP "ffmpeg-win64-gpl.zip"
        # 兼容 PowerShell 5.1 / 7：优先用 curl（Win10+ 自带），否则回退 Invoke-WebRequest
        $hasCurl = Get-Command curl.exe -ErrorAction SilentlyContinue
        if ($hasCurl) {
            & curl.exe -L -o "$Zip" "$Url"
            if ($LASTEXITCODE -ne 0) { throw "curl 下载 ffmpeg 失败" }
        } else {
            Invoke-WebRequest -Uri $Url -OutFile $Zip -UseBasicParsing
        }
        New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
        # 只提取归档内 bin/*.exe（ffmpeg / ffprobe / ffplay）
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $archive = [System.IO.Compression.ZipFile]::OpenRead($Zip)
        try {
            foreach ($entry in $archive.Entries) {
                if ($entry.FullName -match 'bin/([^/]+\.exe)$') {
                    $name = $Matches[1]
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
            }
        } finally {
            $archive.Dispose()
        }
        Remove-Item $Zip -Force
        if (-not (Test-Path $FfmpegExe)) { throw "ffmpeg 提取失败，未得到 bin\ffmpeg.exe" }
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
    if (-not (Get-Command $Iscc -ErrorAction SilentlyContinue)) {
        throw "未找到 iscc。请安装 Inno Setup 6 并将 ISCC.exe 加入 PATH，或确认默认安装路径。" +
              "下载：https://jrsoftware.org/isdl.php"
    }
    Write-Host "==> [3/3] 编译安装程序 (iscc)"
    $env:BD_VERSION = $Version
    & "$Iscc" (Join-Path $Root "installer\installer.iss")
    if ($LASTEXITCODE -ne 0) { throw "iscc 编译失败（退出码 $LASTEXITCODE）" }

    $Out = Join-Path $Root "dist\BilibiliDownloader-Setup-$Version.exe"
    if (Test-Path $Out) {
        Write-Host "==> 完成: $Out"
    } else {
        Write-Host "==> 完成，但未在预期路径找到产物，请检查 installer\output\ 目录。"
    }
} finally {
    Pop-Location
}
