# install.ps1 —— 把 jiazu-xiuxian 技能安装到 DSH 技能根目录
#
# 用法：
#   pwsh -File .\install.ps1
#   pwsh -File .\install.ps1 -Dest "D:\小说\.dsh\skills"
#
# 默认安装到用户根：$env:DSH_HOME\skills 或 ~/.dsh/skills
# 已存在旧版时会先备份为 <目标目录>.bak-<时间戳>，再覆盖安装。

[CmdletBinding()]
param(
    [string]$Dest
)

$ErrorActionPreference = 'Stop'

$SkillName = 'jiazu-xiuxian'
$RepoRoot  = $PSScriptRoot

# 源文件校验：技能必需 SKILL.md，另外两处是技能要用的内容
foreach ($item in @('SKILL.md', 'references', 'scripts')) {
    if (-not (Test-Path (Join-Path $RepoRoot $item))) {
        Write-Error "仓库不完整：缺少 $item（请在仓库根目录运行本脚本）"
    }
}

# 目标技能根：未指定则用 DSH 用户根
if (-not $Dest) {
    $dshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $HOME '.dsh' }
    $Dest = Join-Path $dshHome 'skills'
}

if (-not (Test-Path $Dest)) {
    New-Item -ItemType Directory -Path $Dest -Force | Out-Null
    Write-Host "已创建技能根：$Dest"
}

$target = Join-Path $Dest $SkillName

if (Test-Path $target) {
    $stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backup = "$target.bak-$stamp"
    Move-Item $target $backup
    Write-Host "已备份旧版 -> $backup"
}

New-Item -ItemType Directory -Path $target -Force | Out-Null

# 技能必需部分：SKILL.md + references + scripts
foreach ($item in @('SKILL.md', 'references', 'scripts')) {
    $src = Join-Path $RepoRoot $item
    if (Test-Path $src) {
        Copy-Item $src $target -Recurse -Force
    }
}

# 仓库根 README.md（安装总览）也一并装上，技能目录里可随时查阅
if (Test-Path (Join-Path $RepoRoot 'README.md')) {
    Copy-Item (Join-Path $RepoRoot 'README.md') $target -Force
}

# 清掉可能被带过来的 Python 缓存
Get-ChildItem $target -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "安装完成：$target"
Get-ChildItem $target -Recurse -File |
    ForEach-Object { '  ' + $_.FullName.Replace("$target\", '') }
Write-Host ""
Write-Host "在 DSH 会话里用：skill: $SkillName"
Write-Host "前置条件：include:skill-filesystem / include:tool-skill / include:skill-badge 需为 enabled"
