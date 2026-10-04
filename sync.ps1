# sync.ps1 —— 把「本机已安装的技能」同步回仓库（维护者用）
#
# 用法：
#   pwsh -File .\sync.ps1
#   pwsh -File .\sync.ps1 -Source "D:\小说\.dsh\skills\jiazu-xiuxian"
#
# 作用：技能平时是在 DSH 技能根目录里用的，改动可能发生在那边；
#       本脚本把安装目录的 SKILL.md / README.md / references / scripts 覆盖回仓库，
#       保证「仓库 = 本机在用的版本」，然后你自己 git commit 即可。
#
# 注意：仓库根 README.md（安装总览）不会被覆盖。

[CmdletBinding()]
param(
    [string]$Source
)

$ErrorActionPreference = 'Stop'

if (-not $Source) {
    $dshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $HOME '.dsh' }
    $Source = Join-Path (Join-Path $dshHome 'skills') 'jiazu-xiuxian'
}

if (-not (Test-Path (Join-Path $Source 'SKILL.md'))) {
    Write-Error "源目录不含 SKILL.md：$Source"
}

$RepoRoot = $PSScriptRoot
$copied = @()

foreach ($item in @('SKILL.md', 'references', 'scripts')) {
    $src = Join-Path $Source $item
    if (-not (Test-Path $src)) { Write-Warning "源目录缺少 $item，跳过"; continue }
    Copy-Item $src $RepoRoot -Recurse -Force
    $copied += $item
}

# README.md 单独处理：源里的技能说明落到 references/how-to-use.md，避免覆盖仓库根 README
$srcReadme = Join-Path $Source 'README.md'
if (Test-Path $srcReadme) {
    Copy-Item $srcReadme (Join-Path $RepoRoot 'references\how-to-use.md') -Force
    $copied += 'README.md -> references/how-to-use.md'
}

Get-ChildItem $RepoRoot -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "已同步：$($copied -join '、')"
Write-Host "源：$Source"
Write-Host "接下来：git add -A; git commit -m 'sync skill content'; git push"
