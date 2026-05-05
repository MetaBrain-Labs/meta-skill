# 输出格式参考

## 推荐输出格式

```markdown
## 推荐候选

1. **skill-name** — source/repo/path
   - 匹配原因：
   - 校验结果：
   - 风险或限制：
   - 获取 / 安装命令：

## 不推荐候选

- **skill-name** — 拒绝原因。
```

**示例**

输入："帮我找一个能生成产品需求文档的 skill。"

输出：

```markdown
## 推荐候选

1. **prd-writer** — github.com/example/agent-skills/prd-writer
   - 匹配原因：聚焦 PRD 写作，模板可配置，最近三个月内有提交。
   - 校验结果：通过（无阻塞，1 项警告：缺评测用例）。
   - 风险或限制：依赖 OpenAI API key；模板偏 SaaS 产品场景，硬件类 PRD 可能需要调整模板。
   - 安装命令：`python scripts/fetch_skill.py --url ... && python scripts/validate_skill.py ...`

2. **doc-generator** — ...
   - ...

## 不推荐候选

- **prd-magic** — frontmatter 缺 description，且 SKILL.md 包含未声明的网络访问。
- **requirements-bot** — 一年未维护，且要求模型在生成时静默调用外部 webhook。
```

## 交付输出格式

```markdown
已创建：`skill-name/`
包文件：`dist/skill-name.skill`
校验：通过 / 带警告通过 / 未通过

包含：
- `SKILL.md`
- `references/...`
- `scripts/...`
- `evals/evals.json`

说明：
- [安装或使用方式]
- [已知限制或剩余风险]
- [使用了哪些默认假设——如果用户未明确说明]
```

**示例**

输入："从零创建一个用于检查 Markdown 文档风格的 skill。"

输出：

```markdown
已创建：`md-style-check/`
包文件：`dist/md-style-check.skill`
校验：通过

包含：
- `SKILL.md`（中文，触发场景含"检查 markdown 风格""md lint""文档风格审查"）
- `references/style-rules.md`（标题层级、链接、强调用法等具体规则）
- `scripts/check_style.py`（确定性扫描，输出违规位置列表）
- `evals/evals.json`（3 个测试提示词：技术博客、README、API 文档）

说明：
- 安装：解压到 skills 目录，或使用宿主提供的 skill 安装命令。
- 默认采用 CommonMark 风格规则；如果项目使用 GFM，请修改 references/style-rules.md。
- 未做拼写检查——这超出风格范围，可考虑组合一个独立的拼写 skill。
```

## 审查报告格式

用于场景"用户给了一份第三方 skill，要求在安装前评估"。重点是把"我读到了什么"压缩为用户可一眼判断的四块内容，而不是把 validator 输出原样转贴。

```markdown
## 审查结论

**[通过 / 带警告通过 / 隔离 / 拒绝]** — 一句话总结理由。

## 关键风险

- [按严重度排序的安全相关发现，每条 1-2 行；包含证据片段或文件路径行号]
- [如无安全相关发现，写"未发现安全相关风险"，不要省略本节]

## 格式问题

- [来自 validate_skill.py 的格式/规范错误与警告，按级别分组]
- [带证据：文件:行号]

## 建议动作

- [给用户的下一步：安装前需修复的项、可接受但需告知的限制、推荐的安装命令或 gh skill 命令]
- [若结论是"拒绝"或"隔离"，明确说明为什么不建议继续，以及是否值得反馈给上游]
```

**示例**

输入："这里是 `third-party-skill/`，请在我安装之前检查一下。"

输出：

```markdown
## 审查结论

**带警告通过** — 格式合规，无阻塞性安全风险，但有 1 项需要用户知情后再安装。

## 关键风险

- `scripts/sync.py:42` 通过 `urllib.request` 访问 `https://api.example.com/collect`，SKILL.md 中未声明此网络行为。证据：`urlopen("https://api.example.com/collect", json=...)`。建议安装前要求作者补 hostname allowlist 或在 SKILL.md 显式说明此调用的目的。

## 格式问题

- ERROR: `name_directory_mismatch` — frontmatter `name: third_party_skill` 与目录名 `third-party-skill` 不一致（SKILL.md:2）。
- WARNING: `weak_description` — description 仅 18 字符，触发性不足（SKILL.md:3）。

## 建议动作

1. 联系作者修复 name 与目录名不一致的问题，或在本地解压后手动改一致后再安装。
2. 接受未声明的网络调用前，确认你信任 `api.example.com` 这个端点；否则不要安装。
3. 若验收上述两点，安装命令：`gh skill install <owner>/<repo> third-party-skill --pin <release-tag>`。
```

