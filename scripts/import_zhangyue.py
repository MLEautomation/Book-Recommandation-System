import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import create_app
from app.extensions import db
from app.models import Book, BookTag, Tag, TagType, UserInterest

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = ROOT / "data" / "import" / "zhangyue_books.json"
OUTPUT_PATH = ROOT / "data" / "import" / "zhangyue_books_classified.json"
ACTIVE_TAG_TYPES = ("类型", "发售时间", "篇幅", "地域背景")


JAPANESE_MARKERS = (
    "日本",
    "山下英子",
    "东野圭吾",
    "村上春树",
    "水岛广子",
    "山崎丰子",
)
WESTERN_MARKERS = (
    "美国",
    "英国",
    "欧美",
    "罗伯特",
    "约翰",
    "迈克尔",
    "保罗",
    "亚伦",
    "苏珊",
    "戴尔·卡耐基",
    "柏拉图",
    "巴菲特",
    "索罗斯",
    "蒙哥马利",
    "圣埃克絮佩里",
    "卡萝尔",
    "法布尔",
    "霍布斯",
    "斯宾诺莎",
    "苏伊达",
)


def classify_length(item):
    text = " ".join(str(item.get(key) or "") for key in ("title", "summary"))
    if re.search(
        r"全集|合集|系列|套装|全[0-9一二三四五六七八九十百]+册|上下册|第[0-9一二三四五六七八九十]+卷",
        text,
    ):
        return "超长篇"
    if re.search(r"短篇", text):
        return "短篇"
    if re.search(r"长篇", text):
        return "长篇"
    return "未标注"


def classify_region(item):
    identity = " ".join(
        str(item.get(key) or "") for key in ("title", "author", "category")
    )
    summary = str(item.get("summary") or "")
    if any(marker in identity for marker in JAPANESE_MARKERS) or "日本" in summary:
        return "日本"
    if any(marker in identity for marker in WESTERN_MARKERS) or re.search(
        r"美国|英国|欧美", summary
    ):
        return "欧美"
    return "中国"


def classify_item(item):
    category = str(item.get("category") or "其他").strip() or "其他"
    year = item.get("publish_year")
    release_year = f"{int(year)}年" if year else "未标注"
    return {
        "类型": category,
        "发售时间": release_year,
        "篇幅": classify_length(item),
        "地域背景": classify_region(item),
    }


def load_items(source_path):
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    rows = payload.get("items", []) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("JSON 中没有有效的 items 数组")
    return payload, rows


def write_classified_json(payload, rows):
    output = dict(payload) if isinstance(payload, dict) else {"items": rows}
    output["items"] = [{**item, "tags": classify_item(item)} for item in rows]
    OUTPUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def reset_tag_tables():
    saved_interests = []
    for row in db.session.query(UserInterest).all():
        tag = db.session.get(Tag, row.tag_id)
        if tag and tag.tag_type.name in ACTIVE_TAG_TYPES:
            saved_interests.append((row.user_id, tag.tag_type.name, tag.name))

    db.session.query(BookTag).delete(synchronize_session=False)
    db.session.query(UserInterest).delete(synchronize_session=False)
    for tag_type in db.session.query(TagType).all():
        db.session.query(Tag).filter_by(type_id=tag_type.id).delete(
            synchronize_session=False
        )
        db.session.delete(tag_type)
    db.session.flush()
    return saved_interests


def create_tag_lookup(rows):
    values = {name: set() for name in ACTIVE_TAG_TYPES}
    for item in rows:
        values_for_item = classify_item(item)
        for type_name, tag_name in values_for_item.items():
            values[type_name].add(tag_name)

    lookup = {}
    for type_name in ACTIVE_TAG_TYPES:
        tag_type = TagType(name=type_name)
        db.session.add(tag_type)
        db.session.flush()
        lookup[type_name] = {}
        for tag_name in sorted(values[type_name]):
            tag = Tag(type_id=tag_type.id, name=tag_name)
            db.session.add(tag)
            lookup[type_name][tag_name] = tag
    db.session.flush()
    return lookup


def find_book(item):
    book = (
        db.session.query(Book)
        .filter_by(title=item["title"], author=item["author"])
        .first()
    )
    if book:
        return book
    return None


def update_book(book, item, tags):
    if book is None:
        book = Book(title=item["title"], author=item["author"])
        db.session.add(book)
    isbn = item.get("isbn")
    if isbn:
        isbn_owner = db.session.query(Book).filter_by(isbn=isbn).first()
        if isbn_owner and isbn_owner.id != book.id:
            isbn = None
    for key in (
        "title",
        "author",
        "url",
        "publisher",
        "publish_year",
        "pages",
        "price",
        "summary",
        "author_bio",
    ):
        if key in item:
            setattr(book, key, item.get(key))
    book.isbn = isbn
    book.source = item.get("source") or f"掌阅·{item.get('category') or '全部分类'}"
    cover_url = item.get("cover_url")
    book.cover_path = cover_url if cover_url and "modal_logo" not in cover_url else None
    book.tags = [
        tags[type_name][tag_name] for type_name, tag_name in classify_item(item).items()
    ]
    return book


def restore_interests(saved_interests, lookup):
    for user_id, type_name, tag_name in saved_interests:
        tag = lookup.get(type_name, {}).get(tag_name)
        if tag:
            db.session.add(UserInterest(user_id=user_id, tag_id=tag.id))


def main():
    source_path = Path(sys.argv[1]) if len(sys.argv) > 1 else SOURCE_PATH
    payload, rows = load_items(source_path)
    write_classified_json(payload, rows)
    app = create_app()
    with app.app_context():
        saved_interests = reset_tag_tables()
        lookup = create_tag_lookup(rows)
        for item in rows:
            update_book(find_book(item), item, lookup)
        restore_interests(saved_interests, lookup)
        db.session.commit()
        print(f"imported {len(rows)} books")
        print(f"classified file: {OUTPUT_PATH}")
        print(f"tag types: {', '.join(ACTIVE_TAG_TYPES)}")


if __name__ == "__main__":
    main()
