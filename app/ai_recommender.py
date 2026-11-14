import json
import os
import re

from .extensions import db
from .models import Book, Tag, TagType


def _response_text(content):
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return " ".join(parts)
    return str(content or "")


def _extract_json(content):
    text = _response_text(content).strip()
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(
        r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE
    ).strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text).strip()
    decoder = json.JSONDecoder()
    for index, character in enumerate(text):
        if character not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
            if isinstance(value, (dict, list)):
                return value
        except json.JSONDecodeError:
            continue
    raise RuntimeError("模型返回内容中没有可解析的 JSON")


def _create_llm():
    api_key = os.getenv("MINIMAX_API_KEY") or os.getenv("AI_API_KEY")
    base_url = os.getenv("MINIMAX_BASE_URL") or os.getenv("AI_BASE_URL")
    model = os.getenv("MINIMAX_MODEL", "MiniMax-M3")
    if not api_key:
        raise ValueError("请在 .env 中配置 MINIMAX_API_KEY")
    if not base_url:
        raise ValueError("请在 .env 中配置 MINIMAX_BASE_URL")
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise ValueError("请先安装 langchain-openai 依赖") from exc
    normalized_url = base_url.rstrip("/")
    if "/anthropic" in normalized_url:
        normalized_url = normalized_url.replace("/anthropic", "")
    if not normalized_url.endswith("/v1"):
        normalized_url += "/v1"
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=normalized_url,
        temperature=0.1,
        max_tokens=1200,
        default_headers={"Content-Type": "application/json"},
    )


def _tag_catalog():
    rows = db.session.query(TagType).order_by(TagType.id).all()
    catalog = []
    for tag_type in rows:
        for tag in sorted(tag_type.tags, key=lambda item: item.name):
            if tag.name == "未标注":
                continue
            catalog.append(
                {
                    "id": tag.id,
                    "type": tag_type.name,
                    "name": tag.name,
                }
            )
    return catalog


def _extract_keywords(prompt, catalog):
    catalog_text = json.dumps(catalog, ensure_ascii=False)
    system_prompt = f"""
你是图书推荐系统的标签分析器。根据用户描述，从给定标签集合中选择最匹配的标签并排序。
只能使用标签集合中存在的 id。权重为 1 到 100 的数字，越符合用户描述权重越高。
请严格只返回 JSON，不要输出解释、Markdown 或其他字段。格式如下：
{{"keywords":[{{"tag_id":1,"weight":90}}]}}

可用标签集合：
{catalog_text}
""".strip()
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except ImportError as exc:
        raise ValueError("请先安装 langchain-core 依赖") from exc
    response = _create_llm().invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]
    )
    raw = _extract_json(response.content)
    values = raw.get("keywords", []) if isinstance(raw, dict) else raw
    if not isinstance(values, list):
        raise RuntimeError("模型 JSON 中缺少 keywords 数组")
    allowed = {item["id"]: item for item in catalog}
    keywords = []
    for item in values:
        if not isinstance(item, dict):
            continue
        try:
            tag_id = int(item.get("tag_id"))
            weight = float(item.get("weight"))
        except (TypeError, ValueError):
            continue
        if tag_id not in allowed or weight <= 0:
            continue
        tag = allowed[tag_id]
        keywords.append({**tag, "weight": min(weight, 100)})
    if not keywords:
        raise RuntimeError("模型没有识别出可用的图书标签")
    keywords.sort(key=lambda item: (-item["weight"], item["id"]))
    return keywords


def _candidate_payload(score, book):
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "publish_year": book.publish_year,
        "score": round(score, 2),
        "tags": [
            {"type": tag.tag_type.name, "name": tag.name}
            for tag in book.tags
            if tag.name != "未标注"
        ],
    }


def _select_books_with_llm(prompt, keywords, candidates):
    candidate_text = json.dumps(candidates, ensure_ascii=False)
    keyword_text = json.dumps(keywords, ensure_ascii=False)
    system_prompt = f"""
你是图书推荐系统的最终筛选器。第一阶段已经根据标签筛出了候选图书。
请结合用户原始提示词中的语义、时间范围、人物类型、地域、时代和其他限定条件，
从候选集合中选出基本符合的图书。候选集合之外的书不能选择。
例如用户说“中国近代历史人物的传记”，应优先选择近现代人物传记，
排除明显属于清朝、明朝等古代历史的书。无法确认符合的书不要选择。
如果没有符合项，返回空数组。
只返回 JSON，不要输出解释、Markdown 或其他文本。格式如下：
{{"selected_book_ids":[1,2,3]}}

用户原始提示词：
{prompt}

第一阶段识别的标签：
{keyword_text}

候选图书集合：
{candidate_text}
""".strip()
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
    except ImportError as exc:
        raise ValueError("请先安装 langchain-core 依赖") from exc
    response = _create_llm().invoke(
        [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]
    )
    raw = _extract_json(response.content)
    values = []
    if isinstance(raw, dict):
        values = raw.get("selected_book_ids", raw.get("book_ids", []))
    elif isinstance(raw, list):
        values = raw
    if not isinstance(values, list):
        raise RuntimeError("模型最终筛选结果不是数组")
    allowed_ids = {item["id"] for item in candidates}
    selected = []
    for value in values:
        value = value.get("book_id") if isinstance(value, dict) else value
        try:
            book_id = int(value)
        except (TypeError, ValueError):
            continue
        if book_id in allowed_ids and book_id not in selected:
            selected.append(book_id)
    return selected[:10]


def recommend_from_prompt(prompt):
    from .routes import book_json

    catalog = _tag_catalog()
    keywords = _extract_keywords(prompt, catalog)
    weights = {item["id"]: item["weight"] for item in keywords}
    scored = []
    for book in db.session.query(Book).all():
        score = sum(weights.get(tag.id, 0) for tag in book.tags)
        if score:
            scored.append((score, book.id, book))
    scored.sort(key=lambda item: (-item[0], item[1]))
    if not scored:
        return {
            "keywords": keywords,
            "items": [],
            "total": 0,
            "candidate_total": 0,
            "message": "没有找到包含相关标签的图书",
        }
    candidates = [_candidate_payload(score, book) for score, _, book in scored[:40]]
    selected_ids = _select_books_with_llm(prompt, keywords, candidates)
    selected_books = {book.id: book for _, _, book in scored if book.id in selected_ids}
    return {
        "keywords": keywords,
        "items": [book_json(selected_books[book_id]) for book_id in selected_ids],
        "total": len(selected_ids),
        "candidate_total": len(scored),
        "message": "已根据原始描述完成候选图书二次筛选",
    }
