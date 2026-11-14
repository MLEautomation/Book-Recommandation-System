# 图书推荐系统

本项目按需求文档实现 Flask + MySQL + 原生 HTML/CSS/JavaScript 架构。AI 荐书扩展已取消。

## 本地启动

1. 安装 `requirements.txt`
2. 配置 `BRS_DATABASE_URL`，默认使用 MySQL，也可以使用 `sqlite:///brs.db` 做本地验证
3. 执行 `python scripts/seed_data.py`
4. 执行 `python scripts/import_books.py`
5. 执行 `python run.py`

`import_books.py` 会读取 `data/import/zhangyue_books.json`，按原始 `category` 建立“类型”标签，并生成 `data/import/zhangyue_books_classified.json`。当前筛选标签包括类型、发售时间、篇幅和地域背景。

默认演示账号为 `admin / Admin1234` 和 `demo / Demo1234`。

首页的简单问答使用 LangChain 调用 MiniMax。请在 `.env` 中填写 `MINIMAX_API_KEY` 和 `MINIMAX_BASE_URL`，模型名称通过 `MINIMAX_MODEL` 配置，默认值为 `MiniMax-M3`。推荐使用带 `/v1` 的 OpenAI 兼容接口地址。

## 抓取公开图书元数据

掌阅分类页是动态页面，采集器使用 Playwright 的普通 DOM 解析，不需要 AI API、RAG 或模型密钥。首次使用需要在虚拟环境中安装浏览器运行时：

```powershell
python -m pip install playwright
python -m playwright install chromium
```

采集全站分类页中的图书元数据：

```powershell
python scripts/crawl_zhangyue.py --all-categories --per-category 5 --max-books 120 --details
```

输出文件为 `data/import/zhangyue_books.json`。采集字段包括书名、作者、简介摘要、出版社、ISBN、上架年份、封面地址、详情地址和来源分类，不采集正文、章节、评论或阅读内容。

