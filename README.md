# 复旦大学2026级研究生入学教育测试自动答题 Agent
<img width="956" height="504" alt="image" src="https://github.com/user-attachments/assets/81b9e5e4-38ad-4da6-a1c0-1df75a0a6625" />

已在复旦大学2026级研究生入学教育测试中连续多次获得90+成绩。


这是一个面向固定测试网页的 DOM 驱动答题 Agent。Playwright 负责确定性页面读取与点击，LLM 只负责语义判断，`DecisionPolicy` 在两者之间校验索引和置信度。单选使用整数索引，多选使用整数索引数组；程序永远不会点击“提交试卷/交卷”等最终提交按钮。

详细的设计思路、技术架构和功能说明参见[项目介绍](项目介绍.md)。

> [!IMPORTANT]
> 本项目仅用于浏览器自动化、LLM Agent 和 RAG 技术研究，以及获得明确授权的测试场景。使用者应遵守所在学校、平台或组织的规则，不得将其用于未经授权的考试、规避考核或其他违反学术诚信的行为。

## 最快开始

克隆仓库后，在 Windows PowerShell 中执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

脚本会创建 `.venv`、安装 Python 依赖和 Playwright Chromium，并在缺少 `.env` 时从 `.env.example` 创建一份。随后只需在 `.env` 中填写自己的目标网页和 LLM 配置：

```env
TARGET_URL=https://你的测试网页
LLM_BASE_URL=https://你的兼容接口地址
LLM_API_KEY=你的API密钥
LLM_MODEL=你的模型名称
```

保存后运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

Linux/macOS 用户可以依次执行 `./setup.sh`、编辑 `.env`、`./run.sh`。安装脚本不会覆盖已有 `.env`，启动脚本也不会输出其中的密钥。

## 环境要求

- Python 3.10+
- Chrome（优先）或 Playwright Chromium
- 一个 OpenAI-compatible Chat Completions API；也可用 MockSolver 离线调试

## 安装

```bash
python -m venv .venv
```

Windows：

```bash
.venv\Scripts\activate
```

Linux/macOS：

```bash
source .venv/bin/activate
```

安装依赖和浏览器：

```bash
pip install -r requirements.txt
playwright install chromium
```

如果本机已安装 Chrome，默认会优先使用 `channel=chrome`；不可用时自动回退到 Playwright Chromium。

## 配置

在 Windows PowerShell 中：

```powershell
Copy-Item .env.example .env
```

Linux/macOS：

```bash
cp .env.example .env
```

至少填写：

```env
TARGET_URL=https://example.com/quiz
LLM_BASE_URL=https://api.example.com/v1
LLM_API_KEY=your-secret-key
LLM_MODEL=your-model-name
```

OpenAI 官方接口可将 `LLM_BASE_URL` 留空。DeepSeek、本地服务等填写其 OpenAI-compatible `/v1` 基址。Key 只保存在被 `.gitignore` 忽略的 `.env` 中。

DeepSeek 示例：

```env
LLM_BASE_URL=https://api.deepseek.com
LLM_API_KEY=新生成的密钥
LLM_MODEL=deepseek-v4-flash
```

不要把真实 Key 写入 `.env.example`。如果 Key 曾出现在终端、聊天或版本库中，应先在服务商控制台吊销并重新生成。

常用运行策略：

```env
AGENT_MODE=manual
MIN_CONFIDENCE=0.70
LOW_CONFIDENCE_MODE=manual
```

`AGENT_MODE` 支持：

- `manual`：LLM 建议后每题由用户确认或覆盖索引（默认）。
- `auto`：通过策略校验后自动选择并前往下一题。
- `dry_run`：只读取当前题并分析，不点击页面。

低置信度策略支持 `manual`、`retry`、`accept`、`stop`。无 LLM API 时可设置：

```env
SOLVER_TYPE=mock
MOCK_MODE=manual
```

## 启动

首次配置后先进行不启动浏览器的 LLM 测试：

```bash
python main.py --test-llm
```

测试题固定为“2 + 2”，预期 `choice=1`。该命令验证 API 连接、模型名、JSON 解析和 Pydantic 校验，但不会输出 API Key。模型不存在时程序不会自动换模型。

确认 LLM 测试通过后，在 `quiz_agent` 目录运行：

```bash
python main.py
```

操作顺序：

1. 浏览器自动打开 `TARGET_URL`。
2. 用户手动登录（程序不处理验证码、SSO 或二次验证）。
3. 用户进入测试第一题。
4. 返回终端按 Enter。
5. Agent 按配置模式运行，遇到最终提交页即停止。
6. 最后一题完成后浏览器会保持打开；请人工核对并自行决定是否最终提交，然后回到终端按 Enter 关闭浏览器。

`manual` 模式每题会显示建议，然后接受：`y` 使用 AI 答案、`0-N` 手动指定、`s` 跳过、`q` 停止。多选题可用 `1,3,4` 格式人工指定多个索引。只有确认答案后才会点击，并在核对 radio/checkbox 的最终状态后进入下一页。

运行记录逐题追加到 `runs/YYYY-MM-DD_HHMMSS.jsonl`，高置信度答案缓存于 `data/question_cache_rag.json`。两者都不会因中途异常丢失已写记录。

答案缓存采用版本化的 v2 结构，保存的是“最终答案文本”，而不是页面上不稳定的选项序号。命中缓存时，程序会校验题干、题型和与顺序无关的选项集合指纹，再把答案文本映射到本次页面的实际序号。因此同一道题即使每次随机打乱选项，也能选择同一个答案。题干或选项内容发生变化时会自动视为未命中并重新调用 LLM；旧版仅保存序号的缓存因无法安全迁移会被自动忽略，无需反复手动清缓存。

## 本地 PDF 与联网检索

仓库已包含项目当前使用的学习参考 PDF。首次运行时会自动提取文字并在本地建立页级 BM25 索引；该索引不是向量数据库，而是可以随时从 PDF 重建的派生缓存，因此不会提交到 GitHub。每道题求解前先检索本地 PDF；本地相关性不足时，`WEB_SEARCH_MODE=auto` 会使用有超时限制的公共网页搜索作为补充。PDF 文件发生变化时索引会自动重建。

参考 PDF 的权利归原权利人所有，不适用本项目的 MIT 软件许可证。详情见 [REFERENCE_MATERIALS.md](REFERENCE_MATERIALS.md)。如需使用其他资料，可将 PDF 放入项目根目录；默认 `REFERENCE_PDF_GLOB=*.pdf` 会同时检索它们。

```env
ENABLE_LOCAL_RETRIEVAL=true
REFERENCE_PDF_GLOB=*.pdf
LOCAL_RETRIEVAL_MIN_SCORE=12
WEB_SEARCH_MODE=auto
WEB_SEARCH_BACKEND=startpage
WEB_SEARCH_TIMEOUT_SECONDS=8
```

`WEB_SEARCH_MODE` 支持 `off`、`auto`、`always`。联网失败不会中止答题；同一次运行中首次联网失败后会关闭后续联网检索，避免每题重复等待。搜索查询和摘要缓存在 `data/web_search_cache.json`。

可以在不启动浏览器、不调用 LLM 的情况下检查检索结果：

```powershell
python main.py --test-retrieval "论文评阅书中哪些情况属于存在异议"
```

终端中的 `Sources` 和运行日志中的 `sources` 会列出实际提供给 LLM 的 PDF 页码或网页地址。启用 RAG 后使用独立的 `data/question_cache_rag.json`，不会复用此前无参考资料生成的旧答案缓存。

## 验证 DOM（推荐先做）

```bash
python main.py --debug-dom
```

登录并按 Enter 后，此模式只输出当前 URL、题目 ID、题目文本、题型、选项数量及文本、下一题按钮和最终提交按钮检测结果。它不调用 LLM，也不点击任何元素。

所有站点相关 selector 都集中在 [`browser/selectors.py`](browser/selectors.py)。当前优先读取隐藏的 `textarea[name="question_text"]` 的 DOM `value`，不依赖可见性；答案优先读取 `.answers .answer_label`，点击 `.answers .answer`。

如果实际 DOM 不匹配，请提供以下脱敏信息：

- 一道题的题目容器完整 HTML（包含稳定 ID/data 属性）。
- 一个答案区域的完整 HTML（至少包含两项及 input/label 结构）。
- “下一题”和最终“提交/完成”按钮的 HTML。
- 点击下一题前后的 URL 是否变化，以及题目节点中哪些属性变化。
- 页面是否位于 iframe 或 shadow DOM 内。

不要提供账号、密码、Cookie、Token 或真实 API Key。

## 测试

```bash
pytest -q
```

纯逻辑测试覆盖模型、JSON 解析、choice/置信度边界、决策策略和缓存。浏览器部分应先使用 `--debug-dom` 在目标站验证 selectors。

## 贡献与安全

欢迎通过 Issue 或 Pull Request 提交改进。参与开发前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)。如果发现可能泄露凭据、越权操作或绕过最终提交保护的安全问题，请按照 [SECURITY.md](SECURITY.md) 中的方式报告，不要在公开 Issue 中披露敏感细节。

## 许可证

项目代码采用 [MIT License](LICENSE) 发布。项目使用者自行添加的 PDF、题库和其他参考资料不属于本许可证的授权范围。
