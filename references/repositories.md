# 仓库注册表

本文件说明 `config/repositories.json` 中配置的仓库来源，以及搜索时的优先级策略。

## 来源分类

**官方 / 第一方来源**
由 skill 格式标准的维护方或主要平台方发布的仓库。相关性和可信度最高，优先搜索。

**Curated 清单**
由社区维护的精选索引，通常包含经过人工审查的 skill 列表（如 awesome-list 风格的仓库）。可信度次之。

**社区索引**
通过 GitHub Topics、搜索 API 或社区论坛发现的仓库。范围广但质量参差，需要更严格的校验。

**通用 GitHub 搜索**
兜底策略。当以上来源无法找到合适候选时，使用 GitHub 代码或仓库搜索。结果质量最不确定，应配合完整的隔离审查流程。

## `purpose` 字段

部分条目带 `purpose` 字段，用于区分仓库的用途，影响搜索时是否将其纳入候选。

- `purpose: "specification"`：仓库主体是规范文档与参考实现，而不是可直接安装的 skill 集合。例如 `agentskills/agentskills` 是 Agent Skills 开放规范的官方仓库（Apache-2.0），主要内容是 spec 文档；其 `examples/` 下虽有少量示例 skill，但用户搜索"PDF 工具"或"代码审查"这类具体功能时，几乎不会在这里命中。
- 无 `purpose` 字段（默认）：作为 skill 集合检索。

`search_skills.py` 在用户没有显式提到"规范""spec""参考实现"等关键词时，会自动跳过 `purpose: "specification"` 的来源。如果用户明确要查规范，传 `--include-spec` 或在查询中包含 `spec/specification/规范/参考实现` 这类关键词。

## 搜索优先级

1. 先查 `config/repositories.json` 中标记为 `official` 或 `curated` 的来源（按 `priority` 字段降序）。
2. 再查标记为 `community` 的来源。
3. 最后回退到通用 GitHub 搜索。

如果没有网络访问权限，跳过所有在线搜索，要求用户提供本地路径、压缩包或候选 URL。

## 更新注册表

如需添加新的仓库来源，直接编辑 `config/repositories.json`，按现有条目的格式添加新条目，并注明 `type`（`official`、`curated` 或 `community`）和 `description`。如果新仓库主要是规范、文档或参考实现而非 skill 集合，加 `purpose: "specification"`。

