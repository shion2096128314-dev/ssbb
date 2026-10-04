# publish.ps1 —— 一条命令：同步技能内容 → 提交 → 双推 Gitee + GitHub
#
# 用法：
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\publish.ps1 -Message "修了钩子打分"
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\publish.ps1 -Message "新增 09 篇" -NoPush
#   powershell -NoProfile -ExecutionPolicy Bypass -File .\publish.ps1 -Message "同步" -Source "D:\小说\.dsh\skills\jiazu-xiuxian"
#
# 做的事：
#   1) 校验仓库完整性与 git 身份
#   2) git pull --rebase 拉取远端最新（避免分叉），失败只警告不中断
#   3) 从「本机在用的技能目录」同步 SKILL.md / references / scripts / README 回仓库
#   4) 有改动才提交（-Message 不填则自动生成时间戳提交信息）
#   5) 依次推送到 gitee 与 github（任一失败会明确报出来，并给出单独重试命令）

[CmdletBinding()]
param(
    [string]$Message,
    [string]$Source,
    [switch]$NoPush,
    [switch]$SkipPull
)

$ErrorActionPreference = 'Stop'

# ---------- 0. 定位仓库与技能安装目录 ----------
$RepoRoot = $PSScriptRoot
if (-not (Test-Path (Join-Path $RepoRoot 'SKILL.md'))) {
    Write-Error "这里不是技能仓库根目录（找不到 SKILL.md）：$RepoRoot"
}

if (-not $Source) {
    $dshHome = if ($env:DSH_HOME) { $env:DSH_HOME } else { Join-Path $HOME '.dsh' }
    $Source = Join-Path (Join-Path $dshHome 'skills') 'jiazu-xiuxian'
}
if (-not (Test-Path (Join-Path $Source 'SKILL.md'))) {
    Write-Error "技能安装目录不含 SKILL.md：$Source`n请先用 install.ps1 安装，或用 -Source 指定正确路径。"
}

function Invoke-Git {
    param([string[]]$GitArgs)
    $out = & git @GitArgs 2>&1
    $code = $LASTEXITCODE
    return [pscustomobject]@{ Output = ($out | Out-String).Trim(); Code = $code }
}

Set-Location $RepoRoot

# ---------- 1. 环境校验 ----------
$r = Invoke-Git @('rev-parse', '--is-inside-work-tree')
if ($r.Code -ne 0) { Write-Error "不是 git 仓库：$RepoRoot" }

$name  = (Invoke-Git @('config', 'user.name')).Output
$email = (Invoke-Git @('config', 'user.email')).Output
if (-not $name -or -not $email) {
    Write-Error "git 身份未配置，请先执行：`n  git config user.name `"你的名字`"`n  git config user.email `"你的邮箱`""
}
Write-Host "[1/5] 仓库：$RepoRoot"
Write-Host "      身份：$name <$email>"
Write-Host "      技能源：$Source"

# ---------- 2. 拉取远端最新 ----------
if (-not $SkipPull) {
    $r = Invoke-Git @('pull', '--rebase', '--autostash')
    if ($r.Code -eq 0) {
        Write-Host "[2/5] 已拉取远端最新（pull --rebase）"
    } else {
        Write-Warning "[2/5] pull --rebase 失败，继续用本地状态提交。原始输出：`n$($r.Output)"
    }
} else {
    Write-Host "[2/5] 按 -SkipPull 跳过拉取"
}

# ---------- 3. 同步技能内容回仓库 ----------
$copied = @()
foreach ($item in @('SKILL.md', 'references', 'scripts')) {
    $src = Join-Path $Source $item
    if (-not (Test-Path $src)) { Write-Warning "源目录缺少 $item，跳过"; continue }
    Copy-Item $src $RepoRoot -Recurse -Force
    $copied += $item
}
# 技能包自带的 README（使用说明）落到 references/how-to-use.md，避免覆盖仓库根 README
$srcReadme = Join-Path $Source 'README.md'
if (Test-Path $srcReadme) {
    Copy-Item $srcReadme (Join-Path $RepoRoot 'references\how-to-use.md') -Force
    $copied += 'README.md → references/how-to-use.md'
}
Get-ChildItem $RepoRoot -Recurse -Directory -Filter '__pycache__' -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "[3/5] 已同步：$($copied -join '、')"

# ---------- 4. 有改动才提交 ----------
Invoke-Git @('add', '-A') | Out-Null
$staged = (Invoke-Git @('diff', '--cached', '--name-only')).Output
if (-not $staged) {
    Write-Host "[4/5] 没有内容变化，无需提交"
} else {
    if (-not $Message) {
        $Message = "sync: 同步技能内容 " + (Get-Date -Format 'yyyy-MM-dd HH:mm')
    }
    $r = Invoke-Git @('commit', '-m', $Message)
    if ($r.Code -ne 0) { Write-Error "提交失败：`n$($r.Output)" }
    Write-Host "[4/5] 已提交：$Message"
    Write-Host "      改动文件："
    $staged -split "`n" | Where-Object { $_.Trim() } | ForEach-Object { Write-Host "        $_" }
}

# ---------- 5. 双推 ----------
if ($NoPush) {
    Write-Host "[5/5] 按 -NoPush 跳过推送"
    return
}

$branch = (Invoke-Git @('rev-parse', '--abbrev-ref', 'HEAD')).Output
$failed = @()
foreach ($remote in @('gitee', 'github')) {
    $exists = (Invoke-Git @('remote', 'get-url', $remote)).Code -eq 0
    if (-not $exists) { Write-Warning "remote '$remote' 不存在，跳过"; continue }
    $r = Invoke-Git @('push', $remote, $branch)
    if ($r.Code -eq 0) {
        Write-Host "[5/5] 已推送 $remote/$branch ✓"
    } else {
        Write-Host "[5/5] 推送 $remote 失败 ✗" -ForegroundColor Red
        Write-Host $r.Output
        $failed += $remote
    }
}

if ($failed.Count -gt 0) {
    Write-Warning "有 $($failed.Count) 个远端推送失败：$($failed -join '、')。单独重试：`n  git push $($failed[0]) $branch"
    exit 1
}

$head = (Invoke-Git @('rev-parse', '--short', 'HEAD')).Output
Write-Host ""
Write-Host "完成：$branch @ $head 已同步到 gitee 与 github"
