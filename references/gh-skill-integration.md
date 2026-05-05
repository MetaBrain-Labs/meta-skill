# 与 `gh skill` 的关系

GitHub CLI 自 v2.90.0(2026-04 公开预览）起内置了 `gh skill` 子命令，直接覆盖 skill 的 search、preview、install、update、publish 流程，并带有版本固定与 supply-chain 校验。`gh skill` 是 Agent Skills 规范方提供的官方供应链工具，本 skill 在多数情形下应当优先调用它，而不是自己重新实现等价能力。

本 skill 的 `scripts/` 是 `gh skill` 不可用时的回退，而非替代。

## 何时优先使用 `gh skill`

满足以下全部条件时，优先用 `gh skill`，跳过 `scripts/search_skills.py`、`scripts/fetch_skill.py`、`scripts/package_skill.py` 中的等价步骤：

- 用户环境有 `gh` 命令（快速检查：`gh --version` 返回 v2.90.0+ 且 `gh skill --help` 可用）。
- 目标 skill 位于 GitHub 公开仓库或用户已 `gh auth login` 的私有仓库。
- 用户对 GitHub 生态没有显式排斥（例如要求"不要走 GitHub")。

当任一条件不满足时，回退到本 skill 的脚本——主要场景包括：无 `gh`、目标在非 GitHub 仓库（GitLab、私有 Gitea 等）、用户提供的是本地 skill 副本或压缩包、用户处于离线环境。

## 命令对照

| 流程阶段 | 优先（`gh skill`） | 回退（本 skill 脚本） |
|---------|------------------|----------------------|
| 搜索候选 | `gh skill search <query>` | `scripts/search_skills.py "<query>"` |
| 安装前预览 | `gh skill preview <owner>/<repo> <skill>` | `scripts/fetch_skill.py --url ...` 后人工读取 |
| 获取到本地 | `gh skill install <owner>/<repo> <skill> --pin <tag-or-sha>` | `scripts/fetch_skill.py --url <github-url>` |
| 检查更新 | `gh skill update [<skill>] [--all]` | 手动重新拉取 + diff |
| 校验 + 发布 | `gh skill publish [--fix]` | `scripts/validate_skill.py` + `scripts/package_skill.py` |

## 版本固定的硬性要求

`gh skill install` 必须带 `--pin <tag-or-sha>`，除非用户明确表示愿意接受浮动分支带来的供应链风险。理由：`safety-policy.md` 第 32 行的"优先使用固定 tag 或 commit SHA，而非浮动分支"原则正是 `--pin` 的设计目标——浮动分支会让"今天审查通过的 skill"在"明天安装时悄悄变成另一份代码"。

如果用户不知道选哪个 tag，默认推荐：

1. 仓库的最新 release tag(`gh release list --repo <owner>/<repo>`)。
2. 当前 main 分支的 HEAD SHA(`gh api repos/<owner>/<repo>/commits/main --jq .sha`)。

把所选 ref 在审查报告里明确写出，并在 `gh skill install --pin <ref>` 命令中使用同一个 ref。

## `gh skill preview` 与"先审查、不执行"原则

`gh skill preview` 在安装前打印 skill 内容，不写入磁盘、不执行任何脚本。这与本 skill `safety-policy.md` 中"第三方 skill 在审查前是不可信代码"的立场完全一致，审查阶段应当用它替代 `fetch_skill.py + 人工 cat`。

唯一例外：`gh skill preview` 不能解压脚本中的复杂逻辑；需要静态分析所有 .py 文件时，仍需通过 `fetch_skill.py` 拉到本地配合 `validate_skill.py` 做完整扫描。

## 发布阶段的差异

`gh skill publish` 做的事情比本 skill 的 `package_skill.py` 多一层：

- 校验 skill 是否符合 agentskills.io 规范（本 skill 的 validator 只覆盖部分规则）。
- 检查仓库的 supply-chain 设置：tag protection、secret scanning、code scanning、immutable releases。
- 把 provenance(repo、ref、tree SHA）写入 SKILL.md frontmatter，使溯源信息随文件流动。

如果用户的 skill 即将公开发布到 GitHub，优先用 `gh skill publish`;`package_skill.py` 用于本地交付、内部分发或离线场景（产出 `.skill` 归档文件，而非 GitHub release)。

## 主机适配

`gh skill install` 默认会把 skill 安装到当前主机的标准位置；如需指定目标主机，用 `--agent`:

```bash
gh skill install <owner>/<repo> <skill> --pin <ref> --agent claude-code --scope user
```

支持的主机包括 `claude-code`、`cursor`、`codex`、`gemini`、`antigravity`，以及默认的 GitHub Copilot。如果用户的 Agent 不在此列，使用本 skill 的 `fetch_skill.py` + 用户手动放置。
