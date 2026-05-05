# 工具指南

## `scripts/search_skills.py`

在已配置的 GitHub 仓库和 awesome-list 索引中搜索候选 skill。网络访问限定于 GitHub 公开 API 及 `config/repositories.json` 中配置的仓库。

```bash
python scripts/search_skills.py "查询关键词" --config config/repositories.json --limit 10 --out candidates.json
```

GitHub 对未认证 API 限频约 60 次/小时/IP。可通过环境变量 `GITHUB_TOKEN` 或 `--token <pat>` 提升配额。无网络可用时，脚本会在结果为空且多源 403/429 时输出 `diagnosis` 字段提醒切换为本地副本路径。

## `scripts/fetch_skill.py`

将 GitHub skill 目录或原始 `SKILL.md` 获取到本地工作区。网络访问限定于 `github.com` 和 `raw.githubusercontent.com`。

```bash
python scripts/fetch_skill.py --url https://github.com/owner/repo/tree/main/path/to/skill --out workspace/fetched
```

## `scripts/validate_skill.py`

校验 frontmatter、目录结构和内容风险。

```bash
python scripts/validate_skill.py path/to/skill --json-out validation.json
```

## `scripts/create_skill.py`

生成包含 `SKILL.md`、references、可选 scripts 目录和评测用例的脚手架。

```bash
python scripts/create_skill.py --name my-skill --description "当用户需要..." --goal "..." --out ./my-skill --with-evals
```

## `scripts/rank_candidates.py`

对搜索和校验产出的候选 JSON 进行排序。

```bash
python scripts/rank_candidates.py candidates.json --query "查询关键词" --out ranked.json
```

## `scripts/package_skill.py`

校验并将 skill 打包为 `.skill` zip 归档文件及 manifest。

```bash
python scripts/package_skill.py ./my-skill --out dist
```

## `scripts/file_ops.py`

平台无关的小型辅助工具，用于创建、写入、追加、复制和哈希文件。

```bash
python scripts/file_ops.py write path/to/file.md --text "内容"
python scripts/file_ops.py hash path/to/file.md
```

## `scripts/headless_fetch.py`

抓取公开页面用于研究。安装了 Playwright 时可渲染 JavaScript 页面，否则回退到 `urllib` 处理简单页面。仅用于读取公开内容，不得用于绕过认证或访问私有数据。网络端点无限制，使用时应确认目标 URL 为公开可访问的文档或页面。

```bash
python scripts/headless_fetch.py https://example.com --out page.html
```
