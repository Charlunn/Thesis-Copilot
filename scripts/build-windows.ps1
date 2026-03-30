# QNU Thesis Copilot Windows Build Script
# 使用方法: powershell -ExecutionPolicy Bypass -File build-windows.ps1

$ErrorActionPreference = "Stop"

# 项目路径
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendAssets = Join-Path $ProjectRoot "backend\assets"
$DesktopDir = Join-Path $ProjectRoot "desktop"
$DistDir = Join-Path $DesktopDir "dist"
$ReleaseDir = Join-Path $ProjectRoot "release"

Write-Host "=== QNU Thesis Copilot Windows Build ===" -ForegroundColor Cyan

# 检查 Python
Write-Host "检查 Python..." -ForegroundColor Yellow
try {
    $pythonVersion = python --version 2>&1
    Write-Host "  $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "  错误: 未找到 Python" -ForegroundColor Red
    exit 1
}

# 检查 Node.js
Write-Host "检查 Node.js..." -ForegroundColor Yellow
try {
    $nodeVersion = node --version 2>&1
    Write-Host "  Node $nodeVersion" -ForegroundColor Green
} catch {
    Write-Host "  错误: 未找到 Node.js" -ForegroundColor Red
    exit 1
}

# 检查模板文件
Write-Host "检查模板文件..." -ForegroundColor Yellow
$templatePath = Join-Path $BackendAssets "templates\qnu-undergraduate-v1.docx"
if (Test-Path $templatePath) {
    Write-Host "  模板文件存在: $templatePath" -ForegroundColor Green
} else {
    Write-Host "  警告: 模板文件不存在，将使用默认样式" -ForegroundColor Yellow
}

# 构建前端
Write-Host "构建前端..." -ForegroundColor Yellow
Push-Location $DesktopDir
try {
    npm install
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  前端构建失败" -ForegroundColor Red
        exit 1
    }
    Write-Host "  前端构建完成" -ForegroundColor Green
} finally {
    Pop-Location
}

# 检查构建结果
if (Test-Path (Join-Path $DistDir "index.html")) {
    Write-Host "  构建产物检查通过" -ForegroundColor Green
} else {
    Write-Host "  错误: 构建产物不存在" -ForegroundColor Red
    exit 1
}

# 创建发布目录
Write-Host "准备发布包..." -ForegroundColor Yellow
if (-not (Test-Path $ReleaseDir)) {
    New-Item -ItemType Directory -Path $ReleaseDir -Force | Out-Null
}

# 打包说明
$ReadmeContent = @"
# QNU Thesis Copilot 发布包

## 使用说明

1. 确保已安装 Python 3.11+
2. 安装依赖: `pip install -r requirements.txt`
3. 运行: `python -m qnu_copilot.main`

## 模板文件

已将青海师范大学论文模板放置在:
`backend\assets\templates\qnu-undergraduate-v1.docx`

如需使用其他模板，请替换此文件。

## 目录结构

- `desktop/` - Electron 桌面应用
- `backend/` - Python 后端服务
- `docs/` - 项目文档

## 版本信息

构建时间: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")
"@

$ReadmePath = Join-Path $ReleaseDir "README.txt"
Set-Content -Path $ReadmePath -Value $ReadmeContent -Encoding UTF8

Write-Host ""
Write-Host "=== 构建完成 ===" -ForegroundColor Green
Write-Host "发布包位于: $ReleaseDir" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步:" -ForegroundColor Yellow
Write-Host "  1. 在 desktop/ 目录运行 npm run build"
Write-Host "  2. 使用 electron-builder 打包桌面应用"
Write-Host "  3. 复制整个 release 目录给用户"
