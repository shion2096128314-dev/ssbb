# jiazu-xiuxian · 家族修仙 / 系统文 AI 写小说技能

给 **DeepSeek Harness（DSH）** 用的网文写作技能包，面向**起点（付费订阅）**与**番茄小说（免费阅读）**。主线是**家族修仙文**（族谱、字辈、族产、族战、族运），并覆盖**系统文**基础与两者的融合写法。

装上之后，在任何 DSH 会话里加载 `jiazu-xiuxian`，它就以家族流/系统流写手的身份，按平台逻辑交付：建族设定 → 境界与金手指体系 → 书名简介 → 分卷大纲与细纲 → 黄金三章 → 逐章正文，并在每次交付前跑脚本做体检。

全中文，约 4.7 万汉字；两个校验脚本为纯标准库 Python，无需第三方依赖。

> 目录说明：根目录这份 `README.md` 是**仓库安装与总览**；技能包自己的使用说明在 [`references/how-to-use.md`](references/how-to-use.md)。

---

## 一、它解决什么问题

家族修仙与系统文是两条**设定密集型**赛道，最容易死在三件事上：

1. **族谱与辈分喊错**——读者当场出戏，比错别字严重得多。
2. **力量体系三卷后崩**——境界贬值、越级变常态、灵石数字通胀。
3. **家族成长看不见**——打了三十章脸，家族还是那个样子，读者感觉不到推进。

这个技能包把三点写成**可执行的纪律与模板**，并配两个脚本，让「自检」不靠感觉：

| 脚本 | 作用 |
|---|---|
| `scripts/writing_check.py` | 单章体检：中文字数、去标点字数、段长（手机阅读纪律）、对话占比、注水词/套话命中、重复短语、**章末钩子打分**、是否缺「本章自检」行 |
| `scripts/family_check.py` | 族谱体检：同辈字辈一致、父子辈分倒挂、世代成环、年龄与辈分矛盾、称呼与血缘距离匹配、重名/近似重名 |

两个脚本都支持文件、目录递归、标准输入与 `--json`，带中文用法说明与明确退出码。

---

## 二、安装

这是 **DSH 本地技能（skill）目录包**：把 `SKILL.md`、`references/`、`scripts/` 放进任意一个被扫描的技能根目录即可，无需编译、无需重启。

| 位置 | 路径 | 作用范围 |
|---|---|---|
| 项目根 | `<项目目录>/.dsh/skills/` | 只在该工作区可见 |
| 用户根 | `~/.dsh/skills/`（Windows：`C:\Users\<你>\.dsh\skills\`） | 所有会话可见 |

### 方式 A：一键安装（Windows / PowerShell）

```powershell
git clone https://github.com/shion2096128314-dev/shionsuwako.git
cd shionsuwako
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
# 装到用户根 ~/.dsh/skills（默认）；装到某个项目：
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Dest "D:\小说\.dsh\skills"
```

> 脚本以 UTF-8 BOM 保存，Windows PowerShell 5.1 与 PowerShell 7 都能直接跑。
> 若你在 PowerShell 7 下使用，把 `powershell` 换成 `pwsh` 即可。

> 上面的仓库地址是原始仓库；如果你是从别人的 fork 克隆的，把 URL 换成你的 fork 地址（README 里的链接不影响脚本运行）。

### 方式 B：手动复制

```bash
git clone https://github.com/shion2096128314-dev/shionsuwako.git
mkdir -p ~/.dsh/skills/jiazu-xiuxian
cp -r shionsuwako/{SKILL.md,references,scripts} ~/.dsh/skills/jiazu-xiuxian/
```

Windows 上也可以直接把文件夹复制到 `C:\Users\<你>\.dsh\skills\jiazu-xiuxian\`。

### 前置条件：技能基础设施必须是启用状态

DSH 负责发现本地技能的插件若被禁用，技能目录会是空的，加载会报 `unknown`。需要这四个处于 `enabled: true`：

`@deepseek-ai/dsh-skill`、`@deepseek-ai/dsh-skill-filesystem`、`@deepseek-ai/dsh-tool-skill`、`@deepseek-ai/dsh-skill-badge`

用 `plugin_manager` 的 `list_plugins` 查看 `include:skill-filesystem`、`include:tool-skill`、`include:skill-badge` 是否为 `enabled: true`，不是就启用。**这是实测踩过的坑**：基础设施没开时，`~/.dsh/skills` 下已有的技能全都加载不了。

---

## 三、使用

在会话里加载技能：

```
skill: jiazu-xiuxian
```

或用自然语言触发（技能的 `whenToUse` 会自动匹配）：

```
用家族修仙技能，在番茄开一本家族修仙 + 系统文：
主角是三代旁支，金手指是能看见族运流向。计划 120 万字，日更 6000，单章 2000。
```

| 想要什么 | 就这么说 |
|---|---|
| 开新书全流程 | 「用 jiazu-xiuxian 在起点开一本家族修仙，主角靠祖灵传承」 |
| 只写一章 | 「按 jiazu-xiuxian 的规矩写第 12 章：族比初赛，炼气三层对炼气六层」 |
| 建族 | 「按 03 的模板设计一个家族：没落世家、字辈八代、15 个有名有姓的族人」 |
| 立体系 | 「按 04 设计境界阶梯和金手指，金手指要写满五项公式」 |
| 拆书改稿 | 「用家族修仙技能拆我这章，只讲最致命的 3 条」 |
| 体检一章 | 「跑一下 writing_check 看我这章」 |

### 手工跑脚本

```bash
# Windows 下的 Python 解释器通常是：
#   C:\Users\<你>\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe

python scripts/writing_check.py 第012章.txt
python scripts/writing_check.py 卷一/                # 目录递归：*.txt / *.md / 无扩展名文本
cat 第012章.txt | python scripts/writing_check.py     # 标准输入

python scripts/family_check.py --zipai-order 承,允,昭,克,绍 --lead 戚昭文 族谱.txt

python scripts/writing_check.py --help
python scripts/family_check.py --help
```

族谱清单每行一人，分隔符支持 `|`、逗号、制表符与多空格，也支持中文表头行和 `key=value` 行：

```
姓名 | 辈分字 | 世代 | 父辈 | 年龄 | 修为 | 称呼(对主角) | 与主角关系 | 备注
戚允岳 | 允 | 1 |      | 58 | 筑基九层 | 族叔祖 | 长辈
戚昭文 | 昭 | 2 | 戚允岳 | 26 | 炼气三层 | 本人 | 主角
```

---

## 四、仓库结构

```
shionsuwako/
├── SKILL.md                      技能入口：人设 / 开工六步 / 14 条硬纪律 / 输出格式
├── install.ps1                   一键安装到 DSH 技能根目录（含旧版备份）
├── sync.ps1                      把本机在用的技能版本同步回仓库
├── publish.ps1                   一条命令：同步 + 提交 + 双推 Gitee/GitHub
├── LICENSE                       MIT
├── VERSION                       版本号
├── references/
│   ├── how-to-use.md             技能包使用说明（安装位置、目录说明、联动其他技能）
│   ├── 01-平台规则与选题定位.md    起点 vs 番茄、选题表、书名四公式、简介五句结构
│   ├── 02-家族修仙玩法.md          爽点内核、资源流、6 层冲突阶梯、12 条翻车与改法
│   ├── 03-家族设计手册.md          建族清单、11 层组织、名册模板、字辈与称呼、命名库
│   ├── 04-境界与体系设计.md        境界阶梯、8 个金手指公式、物价表、地图尺度、崩溃前兆
│   ├── 05-系统文基础.md            面板模板、8 类系统、积分经济、系统出处、章骨架
│   ├── 06-黄金三章.md              前五章硬指标、第 1 章 800 字节拍表、开篇示例
│   ├── 07-反派与升级阶梯.md        8 层反派阶梯、打脸六节拍、反派台词库
│   └── 08-自检清单.md              开书/单章/卷末自检、退回重写清单、脚本实测记录
└── scripts/
    ├── writing_check.py          单章写作体检
    └── family_check.py           族谱一致性校验
```

---

## 五、写作纪律（`SKILL.md` 的浓缩版）

| 纪律 | 标准 |
|---|---|
| 第一句 | 必须是冲突，不写天气/背景/族史 |
| 每章 | ≥1 个小爽点 + 1 个章末钩子，缺一不可 |
| 主角憋屈 | 不超过一章（番茄不超过半章） |
| 家族成长 | 每 3–5 章让读者看见一次可见变化 |
| 辈分称呼 | 新角色出场先定辈分再给名字 |
| 数字 | 灵石/贡献点/物价按体系表写，不随手加零 |
| 越级 | 必须给条件，且不连续两章用同一招 |
| 金手指 | 必须有代价（次数/资源/暴露/反噬） |
| 系统面板 | 一次 3–5 行，且出现在冲突中 |
| 正文格式 | 纯文本，不用 Markdown 语法，段不过 3 行，对话用「」 |
| 时效性信息 | 签约/榜单/全勤/红线一律联网核实，区分官方口径与同行经验 |

---

## 六、实测记录（不是「应该能用」）

- **技能加载**：在 DSH 会话里 `skill: jiazu-xiuxian` 加载成功，技能根解析正确。
- **脚本实测**：`writing_check.py` 用真实稿件《补天眼》第 1–3 章跑通（3 章 3695 汉字、长段落 2、注水命中 6、弱钩子 0 章、缺自检 0 章）；`family_check.py` 用「正确族谱 + 注入错误的族谱」双向验证（正确 0 错误、`--strict` 退出码 0；错误稳定抓出 3 条、退出码 1）。
- **验收中修掉的两个真缺陷**（留档于 `references/08-自检清单.md`）：
  1. 「本章自检」行上方的 `——` 分隔符被当成章节末行，导致章末钩子分被系统性低估 → 已修，并写下回归测试约定。
  2. `--zipai-order` 原被当成绝对映射（第 1 代 = 表首字），族谱不从首代写起时整份误报 → 已改为相对锚点映射。
- **字数口径提醒**：本仓库字数均按 `[\u4e00-\u9fff]` 中文字符统计。PowerShell 5.1 下 `Get-Content -Raw` 默认 GBK，会得到乱码与虚高字数，请用 `[System.IO.File]::ReadAllText($p,[System.Text.Encoding]::UTF8)`。

---

## 七、配套技能

| 技能 | 关系 |
|---|---|
| `fanqie-shuangwen` | 番茄通用爽文节奏与选题；本包在其上补家族与体系专业度 |
| `duanju` | 竖屏短剧；要把家族文折成短剧时配合使用 |

三者可叠加：先用本包建族立体系，再用 `fanqie-shuangwen` 的平台节奏打磨番茄开篇。

---

## 八、许可与免责

MIT License，见 [LICENSE](LICENSE)。

技能内容为原创方法论与模板，**不含任何已有小说的原文、桥段或人设组合**。涉及平台政策、签约门槛、榜单口径、审核红线等时效性内容，技能内部一律标注「需联网核实」，不构成对收益、签约、上架的承诺。

---

## 九、更新与发布

### 9.1 你自己改了技能内容（在 DSH 技能根目录里改的）

```powershell
cd D:\小说\jiazu-xiuxian
powershell -NoProfile -ExecutionPolicy Bypass -File .\publish.ps1 -Message "改了钩子打分规则"
```

`publish.ps1` 会依次做五件事：

| 步骤 | 动作 |
|---|---|
| 1 | 校验仓库完整性、git 身份、技能安装目录 |
| 2 | `git pull --rebase --autostash` 拉取远端最新（失败只警告，不中断） |
| 3 | 把本机在用的技能内容同步回仓库（`SKILL.md`、`references`、`scripts`；技能包 README → `references/how-to-use.md`） |
| 4 | 有改动才提交；`-Message` 不填则自动生成时间戳提交信息 |
| 5 | 依次推送 `gitee` 与 `github`；任一失败会明确报出并给出单独重试命令，退出码 1 |

常用变体：

```powershell
# 只同步 + 提交，先不推（想检查 diff 时用）
powershell -NoProfile -ExecutionPolicy Bypass -File .\publish.ps1 -Message "wip" -NoPush

# 从指定技能目录同步（默认取 ~/.dsh/skills/jiazu-xiuxian）
powershell -NoProfile -ExecutionPolicy Bypass -File .\publish.ps1 -Message "同步" -Source "D:\小说\.dsh\skills\jiazu-xiuxian"

# 跳过 pull（离线或刚拉过）
powershell -NoProfile -ExecutionPolicy Bypass -File .\publish.ps1 -Message "同步" -SkipPull
```

### 9.2 别人更新了仓库，你要拉下来用

```powershell
cd D:\小说\jiazu-xiuxian
git pull
powershell -NoProfile -ExecutionPolicy Bypass -File .\install.ps1    # 覆盖安装，旧版自动备份
```

### 9.3 只想手动来

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\sync.ps1   # 仅同步回仓库
git add -A; git commit -m "更新说明"
git push both main                                              # 一条命令双推（已配好双 pushurl）
```

版本号见 [VERSION](VERSION)。

---

## 十、安装后检查清单

装完建议过一遍这四项，都是实测踩过的坑：

| # | 检查项 | 怎么查 / 怎么修 |
|---|---|---|
| 1 | 技能基础设施是启用的 | 用 `plugin_manager` 的 `list_plugins` 确认 `include:skill-filesystem`、`include:tool-skill`、`include:skill-badge` 均为 `enabled: true`。**未启用时技能目录为空，加载会报 unknown**，而 `~/.dsh/skills` 下已有的技能也会一起失效 |
| 2 | 技能能被加载 | 在会话里执行 `skill: jiazu-xiuxian`，能返回技能正文即成功 |
| 3 | 脚本能跑 | `python scripts/writing_check.py --help` 与 `python scripts/family_check.py --help` 均应输出中文用法、退出码 0 |
| 4 | 平台默认分支是 `main` | 见下方说明 |

### 关于默认分支（重要）

推上去的分支叫 `main`，但仓库的**默认分支**由平台设置决定，git 改不了它：

- **GitHub**：新建仓库默认已是 `main`，一般无需处理。若你的仓库默认是 `master`，去 `Settings → Branches → Default branch` 改成 `main`。
- **Gitee**：建仓时若勾了「初始化仓库」，会生成一个空的 `master`（带一个 README 的初始提交），默认分支仍是 `master`——**这会导致访客打开仓库页看到的是空内容**，而你的代码在 `main` 上。
  改法：`管理 → 仓库设置 → 默认分支` 选 `main`；顺手把无用的 `master` 删掉（`管理 → 分支管理`）。

用 Gitee API 也可以改（需要个人令牌，勾 `projects` 权限）：

```bash
# 设默认分支为 main
curl -X PATCH "https://gitee.com/api/v5/repos/<owner>/<repo>" \
  -d "access_token=<你的令牌>&default_branch=main"

# 删掉多余的 master 分支
curl -X DELETE "https://gitee.com/api/v5/repos/<owner>/<repo>/branches/master" \
  -d "access_token=<你的令牌>"
```

> 为什么不让脚本自动改：平台设置需要账号令牌，而令牌属于你的凭据，不应写进仓库或脚本里。
