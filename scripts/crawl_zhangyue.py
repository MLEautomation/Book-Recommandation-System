"""Collect book metadata from Zhangyue's public category page.

This scraper uses ordinary DOM selectors and does not need an AI API or RAG.
It only collects metadata and a short summary. It does not collect book text,
chapters, comments, or reading content.
"""

import argparse
import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


DEFAULT_URL = "https://se.zhangyue.com/category/index?appId=5f72666e"
BOOK_LINK_RE = re.compile(r"/book/detail(?:\?|$)")
BOOK_ID_RE = re.compile(r"[?&]bookId=(\d+)")


def clean_text(value, limit=None):
    value = re.sub(r"\s+", " ", value or "").strip()
    return value[:limit] if limit else value


def query_value(url, key):
    values = parse_qs(urlparse(url).query).get(key, [])
    return values[0] if values else None


def parse_card_text(text):
    parts = [clean_text(line) for line in (text or "").splitlines() if clean_text(line)]
    title = parts[0] if parts else ""
    author = parts[1] if len(parts) > 1 else ""
    summary = clean_text(" ".join(parts[2:]), 800)
    return title, author, summary


async def find_cover_url(page_or_anchor, base_url):
    images = page_or_anchor.locator("img")
    candidates = await images.evaluate_all("""imgs => imgs.map(img => ({
        src: img.currentSrc || img.src || img.dataset.src || '',
        width: img.naturalWidth || img.width || 0,
        height: img.naturalHeight || img.height || 0
    }))""")
    candidates = [item for item in candidates if item["src"] and "modal_logo" not in item["src"]]
    candidates.sort(key=lambda item: (
        "bookbk.img.zhangyue01.com" in item["src"],
        "idc_1/m_1,w_300,h_400" in item["src"],
        item["height"] >= item["width"] * 1.05,
        item["width"] * item["height"],
    ), reverse=True)
    if not candidates:
        return None
    return urljoin(base_url, candidates[0]["src"])


async def collect_category_links(page, max_books):
    stable_rounds = 0
    last_count = 0
    records = {}

    while stable_rounds < 5 and len(records) < max_books:
        anchors = page.locator('a[href*="/book/detail"]')
        count = await anchors.count()
        for index in range(count):
            anchor = anchors.nth(index)
            href = await anchor.get_attribute("href")
            if not href or not BOOK_LINK_RE.search(href):
                continue
            url = urljoin(DEFAULT_URL, href)
            book_id = query_value(url, "bookId")
            if not book_id or book_id in records:
                continue
            text = await anchor.inner_text()
            title, author, summary = parse_card_text(text)
            cover_url = await find_cover_url(anchor, url)
            records[book_id] = {
                "source_book_id": book_id,
                "title": title,
                "author": author,
                "summary": summary,
                "url": url,
                "cover_url": cover_url,
                "source": "掌阅·南京图书馆公开分类页",
            }
            if len(records) >= max_books:
                break

        if len(records) == last_count:
            stable_rounds += 1
        else:
            stable_rounds = 0
            last_count = len(records)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        try:
            await page.wait_for_timeout(1200)
        except PlaywrightTimeoutError:
            pass
    return list(records.values())


async def collect_category_urls(page, limit):
    """Read first-level category links from the all-category page."""
    found = []
    anchors = page.locator('a[href*="/category/index"]')
    for index in range(await anchors.count()):
        anchor = anchors.nth(index)
        href = await anchor.get_attribute("href")
        name = clean_text(await anchor.inner_text())
        if not href or not query_value(urljoin(DEFAULT_URL, href), "cid") or not name:
            continue
        url = urljoin(DEFAULT_URL, href)
        if any(item["url"] == url for item in found):
            continue
        found.append({"name": name, "url": url})
        if len(found) >= limit:
            break
    return found


async def read_detail(context, record):
    page = await context.new_page()
    try:
        await page.goto(record["url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(500)
        body = await page.locator("body").inner_text()
        title_locator = page.locator("h1, .book-title, .bookName").first
        if await title_locator.count():
            record["title"] = clean_text(await title_locator.inner_text()) or record["title"]
        author_match = re.search(r"作者\s*[：:]\s*([^\n]+)", body)
        publisher_match = re.search(r"出版社\s*[：:]\s*([^\n]+)", body)
        isbn_match = re.search(r"ISBN\s*[：:]\s*([0-9Xx-]+)", body)
        year_match = re.search(r"上架时间\s*[：:]\s*(\d{4})[-年]", body)
        intro_match = re.search(r"【简介】\s*(.+?)(?:\s+随感|\s+图书更多信息|$)", body, re.S)
        if author_match:
            record["author"] = clean_text(author_match.group(1))
        if publisher_match:
            record["publisher"] = clean_text(publisher_match.group(1))
        if isbn_match:
            record["isbn"] = isbn_match.group(1)
        if year_match:
            record["publish_year"] = int(year_match.group(1))
        if intro_match:
            record["summary"] = clean_text(intro_match.group(1), 1200)
        detail_cover = await find_cover_url(page, record["url"])
        if detail_cover:
            record["cover_url"] = detail_cover
        return record
    finally:
        await page.close()


async def crawl(args):
    async with async_playwright() as playwright:
        executable = os.getenv("BRS_CHROMIUM_EXECUTABLE")
        if not executable:
            candidates = sorted(Path.home().glob("AppData/Local/ms-playwright/chromium-*/chrome-win64/chrome.exe"), reverse=True)
            executable = str(candidates[0]) if candidates else None
        launch_options = {"headless": not args.headful}
        if executable:
            launch_options["executable_path"] = executable
        browser = await playwright.chromium.launch(**launch_options)
        context = await browser.new_context(locale="zh-CN")
        page = await context.new_page()
        await page.goto(args.url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(1000)
        category_targets = [{"name": "全部分类", "url": args.url}]
        if args.all_categories:
            category_targets = await collect_category_urls(page, args.max_categories)
            if not category_targets:
                category_targets = [{"name": "全部分类", "url": args.url}]
        records_by_id = {}
        for category in category_targets:
            await page.goto(category["url"], wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(700)
            remaining = args.max_books - len(records_by_id)
            for record in await collect_category_links(page, min(args.per_category, remaining)):
                record["category"] = category["name"]
                records_by_id.setdefault(record["source_book_id"], record)
                if len(records_by_id) >= args.max_books:
                    break
            if len(records_by_id) >= args.max_books:
                break
        records = list(records_by_id.values())
        if args.details:
            for start in range(0, len(records), args.detail_batch):
                batch = records[start:start + args.detail_batch]
                await asyncio.gather(*(read_detail(context, item) for item in batch))
                await asyncio.sleep(args.delay)
        await browser.close()

    result = {
        "source_url": args.url,
        "crawled_at": datetime.now().astimezone().isoformat(),
        "count": len(records),
        "items": records,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(records)} books to {output}")


def main():
    parser = argparse.ArgumentParser(description="爬取掌阅公开分类页的图书元数据")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--output", default="data/import/zhangyue_books.json")
    parser.add_argument("--max-books", type=int, default=200)
    parser.add_argument("--per-category", type=int, default=5, help="每个一级分类最多采集多少本")
    parser.add_argument("--all-categories", action="store_true", help="遍历首页发现的一级分类")
    parser.add_argument("--max-categories", type=int, default=30)
    parser.add_argument("--details", action="store_true", help="逐本访问详情页补充出版社、ISBN、简介")
    parser.add_argument("--detail-batch", type=int, default=3)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--headful", action="store_true", help="显示浏览器窗口，便于观察采集过程")
    args = parser.parse_args()
    asyncio.run(crawl(args))


if __name__ == "__main__":
    main()
