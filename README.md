# FinSight Agent

FinSight Agent 是一个面向热点事件与舆情分析的智能分析系统。项目包含热点话题采集、多平台内容爬取、情感分析和深度研究报告生成能力，并提供 Flask Web 面板用于提交分析任务和查看报告。

## 功能

- 热点新闻与话题提取
- 小红书、抖音、快手、B 站、微博、贴吧、知乎等平台内容爬取
- 多语言情感分析
- 基于本地数据库与 LLM 的深度研究报告生成
- Web 面板查看任务进度、日志和 Markdown 报告

## 环境要求

- Python 3.11+
- MySQL 或 PostgreSQL
- LLM API Key
- 可选：Tavily / Bocha 搜索 API Key

## 安装

```bash
uv sync
```

如需使用浏览器爬取能力：

```bash
uv run playwright install
```

## 配置

在项目根目录创建 `.env`，配置数据库、模型和搜索服务：

```env
DB_DIALECT=mysql
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_password
DB_NAME=fsa
DB_CHARSET=utf8mb4

INSIGHT_ENGINE_API_KEY=your_api_key
INSIGHT_ENGINE_BASE_URL=https://api.example.com/v1
INSIGHT_ENGINE_MODEL_NAME=your_model

MINDSPIDER_API_KEY=your_api_key
MINDSPIDER_BASE_URL=https://api.example.com/v1
MINDSPIDER_MODEL_NAME=your_model

TAVILY_API_KEY=
BOCHA_WEB_SEARCH_API_KEY=
```

不要将 `.env` 或真实密钥提交到 GitHub。

## 运行

启动 InsightEngine Web 面板：

```bash
uv run python insight_server.py
```

默认访问：

```text
http://127.0.0.1:5050/insight
```

初始化 MindSpider：

```bash
uv run python MindSpider/main.py --setup
```

运行完整采集流程：

```bash
uv run python MindSpider/main.py --complete --test
```

只运行话题提取：

```bash
uv run python MindSpider/main.py --broad-topic
```

只运行内容爬取：

```bash
uv run python MindSpider/main.py --deep-sentiment --platforms wb xhs --max-keywords 10 --max-notes 20
```

## 目录结构

```text
InsightEngine/                  深度分析 Agent 与 Web 面板
MindSpider/                     热点话题提取与多平台爬取
SentimentAnalysisModel/         本地情感分析模型
insight_engine_streamlit_reports/ 生成的 Markdown 报告
insight_server.py               Flask 服务入口
config.py                       全局配置
pyproject.toml                  项目依赖
```

## 输出

分析报告会保存到：

```text
insight_engine_streamlit_reports/
```

