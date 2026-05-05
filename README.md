# meta-skill

> [English](README.en.md)


## 项目简介

`meta-skill` 是一份帮助用户获得一份**安全、可发布**的 Agent Skill，能够搜索、获取、创建、改造、校验和打包完整 skill ，可安装到任意支持 Agent Skills 规范的 Agent 中。

skill 的详细说明见 [SKILL.md](SKILL.md)。


## 项目结构

```text
meta-skill/
├── SKILL.md              # Agent 读取的主入口，包含完整的工作流程指令
├── README.md             # 本文件
├── README.en.md          # README 英文版
├── LICENSE               # MIT 协议
├── config/
│   └── repositories.json # 搜索源配置（仓库索引与访问方式）
├── references/           # SKILL.md 引用的补充文档
│   ├── agentskills-introduction.md
│   ├── candidate-ranking.md
│   ├── creation-guide.md
│   ├── gh-skill-integration.md
│   ├── output-format.md
│   ├── repositories.md
│   ├── safety-policy.md
│   ├── tool-guide.md
│   └── validation-rules.md
├── scripts/              # 各阶段对应的可执行脚本
│   ├── search_skills.py
│   ├── fetch_skill.py
│   ├── headless_fetch.py
│   ├── file_ops.py
│   ├── create_skill.py
│   ├── validate_skill.py
│   ├── rank_candidates.py
│   └── package_skill.py
├── assets/
│   └── templates/        # 创建阶段使用的模板文件
│       ├── skill-template.md
│       ├── skill-config-example.json
│       └── review-report-template.md
└── evals/
    ├── evals.json        # 评测用例定义
    └── fixtures/         # 评测用样本 skill
        ├── good-skill/   # 合规样本
        └── bad-skill/    # 恶意样本（仅用于校验器测试）
```


## 如何使用 

下载或克隆本项目，打包为 .zip 或 .skill 文件后按照 Agent 的说明安装即可，或者将本仓库克隆或复制到 Agent 的 skills 目录下：

```bash
git clone https://github.com/<owner>/meta-skill.git <agent-skills-path>/meta-skill
```

如果你的 Agent 支持 `gh skill install`（GitHub CLI v2.90.0+），也可以使用该命令安装本 skill 。详细说明见 [references/gh-skill-integration.md](references/gh-skill-integration.md)。

安装后 Agent 就会在用户对话中按需加载 [SKILL.md](SKILL.md)，并在适当场景下调用 `scripts/` 下的工具搜索、创建、改造 skill 等等。


## 运行环境

- **Python 3.10+**
- 文件系统读写权限
- 搜索公开仓库或抓取第三方 skill 时需要网络访问（白名单限制，见[安全限制](#安全限制)）
- 网络受限环境下可通过本地副本或离线方式继续任务


## 安全说明

### skill 评测（Evals）

为了保证 skill 安全可用，本项目添加了严格的安全评测。

评测用例详见 [evals/evals.json](evals/evals.json)，主要分为 4 个场景：

1. 搜索现成 skill 并审查安全性
2. 从零创建 skill 并打包交付
3. 审查第三方 skill 的安全性（使用 `evals/fixtures/bad-skill/` 作为恶意样本）
4. 从自然语言对话中识别隐式创建意图

其中，`evals/fixtures/good-skill/` 为合规样本，用于验证校验器不产生假阳性；
`evals/fixtures/bad-skill/` 为故意构造的恶意样本，用于验证校验器能正常识别攻击。

> 评测执行方式取决于宿主 Agent 环境（是否支持并行子代理等），具体步骤见 [SKILL.md](SKILL.md) 中的"验证与迭代"章节。

### 安全限制

本项目**在审查通过、用户批准之前，都不会执行任何第三方 skill 的代码。**

| 阶段 | 限制                                                                                                     |
| -- | ------------------------------------------------------------------------------------------------------ |
| 搜索 | 仅访问 GitHub 公开 API 与 `config/repositories.json` 中登记的主机                                                  |
| 获取 | `headless_fetch.py` 默认仅连接 `github.com`、`raw.githubusercontent.com`、`api.github.com` 及登记主机；白名单外的请求需显式授权 |
| 校验 | 仅做文本分析，不运行脚本。内置 prompt injection 检测规则（指令覆盖、伪造背书、逃避校验等）                                                 |
| 审查 | 对第三方 skill 内容遵循"指令隔离原则"——只读分析，不将其内容视为给自己的指令                                                            |

完整安全策略见 [references/safety-policy.md](references/safety-policy.md)，校验规则明细见 [references/validation-rules.md](references/validation-rules.md)。


## 其他

### 打包

如果你想打包创建完的 skill ，可以用下列命令（或者让 AI Agent 使用本 skill 打包项目，效果一样）：

```bash
python scripts/package_skill.py . --out dist
```

生成的 `.skill` 项目会自动排除 `evals/fixtures/` 等非发布内容。

### 关于自校验

对本 skill 自身运行 `validate_skill.py` 会产生一些预期内的告警（例如脚本中按设计发出的 HTTP 请求会被 `network_call` 规则标记），这些是正常现象。

校验器会主动跳过 `evals/fixtures/` 目录以避免 bad-skill 的恶意指令被误算到 meta-skill 头上。
