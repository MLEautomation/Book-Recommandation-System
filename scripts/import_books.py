import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app
from app.extensions import db
from app.models import Book, Tag, TagType

ROOT = os.path.dirname(os.path.dirname(__file__))
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "data", "import", "books.json")


def first_match(text, rules, default=None):
    for pattern, value in rules:
        if re.search(pattern, text, re.I):
            return value
    return default


def infer_tags(item):
    text = " ".join(str(item.get(key) or "") for key in ("title", "author", "summary", "category"))
    category = str(item.get("category") or "")
    type_name = first_match(text, [
        (r"诗|诗集|诗词|文学|散文", "文学"),
        (r"科幻", "科幻"), (r"推理|悬疑|法医|刑警|侦探|烧脑", "推理"),
        (r"恐怖|惊悚|怪谈|诡", "恐怖"), (r"武侠|剑来", "武侠"),
        (r"军事|战争|军队|将军|兵法|战役|武器|国防|抗战|战场", "军事"),
        (r"言情|爱情|婚恋|甜宠|宅斗", "言情"), (r"奇幻|玄幻|仙侠", "奇幻"),
        (r"心理|情绪|自我肯定|失眠|心理医生", "心理"), (r"历史|王朝|帝王|传记|战争史", "历史"),
        (r"哲学|逻辑|思想|道德经|周易", "哲学"), (r"法律|法学", "法律"),
        (r"医学|健康|养生", "医学"), (r"科普|互联网|记忆|学习方法", "科普"),
    ], {"小说": "文学", "文学": "文学", "青春": "青春", "影视原著": "文学", "传记": "传记",
        "艺术": "艺术", "生活": "生活", "旅游": "旅游", "少儿": "少儿", "历史": "历史",
        "社会科学": "社会", "心理": "心理", "政治/军事": "社会", "哲学": "哲学",
        "法律": "法律", "励志": "励志", "经管": "经管", "医学": "医学",
        "科普/互联网+": "科普", "工业X.0": "职场", "外文图书": "其他", "杂志": "其他",
        "外语学习": "其他", "其他": "其他"}.get(category, "其他"))
    audience = first_match(text, [(r"儿童|少儿|幼儿|绘本", "儿童"), (r"青春|校园|高中|大学生", "青少年")], "通用")
    length = "长篇" if re.search(r"全集|合集|全\d+册|系列|长篇", text) else "中篇"
    mood = first_match(text, [(r"治愈|疗愈|轻盈|幸福", "治愈"), (r"励志|成功|成长|觉醒", "励志"),
                              (r"热血|战争|英雄|剑", "热血"), (r"恐怖|惊悚|黑暗|悬案", "黑暗"),
                              (r"幽默|不体面", "幽默"), (r"感人|生命|亲情", "感人")], "温馨")
    region = "日本" if re.search(r"日本|日式|山下英子|水岛广子|山崎丰子", text) else ("欧美" if re.search(r"英国|美国|欧美|罗伯特|迈克尔·|哈里斯", text) else "中国")
    language = "英文" if re.search(r"英文|英语|英语学习|外文", text) else ("日文" if region == "日本" else "中文")
    result = {"类型": type_name, "适合人群": audience, "篇幅": length, "情绪基调": mood, "地域背景": region, "语言": language}
    if item.get("publish_year"):
        year = int(item["publish_year"])
        result["发售时间"] = "2020年以前" if year < 2020 else f"{year}年"
    return result


app = create_app({"SQLALCHEMY_DATABASE_URI": os.getenv("BRS_DATABASE_URL", "sqlite:///brs.db")})
with app.app_context():
    payload = json.load(open(path, encoding="utf-8"))
    rows = payload.get("items", []) if isinstance(payload, dict) else payload
    type_rows = {x.name: x for x in db.session.query(TagType).all()}
    for item in rows:
        for type_name, tag_name in infer_tags(item).items():
            tag_type = type_rows.get(type_name)
            if tag_type and not db.session.query(Tag).filter_by(type_id=tag_type.id, name=tag_name).first():
                db.session.add(Tag(type_id=tag_type.id, name=tag_name))
    db.session.flush()
    lookup = {x.name: {tag.name: tag for tag in x.tags} for x in db.session.query(TagType).all()}
    for item in rows:
        book = db.session.query(Book).filter_by(isbn=item.get("isbn")).first() if item.get("isbn") else None
        if not book:
            book = db.session.query(Book).filter_by(title=item["title"], author=item["author"]).first()
        if not book:
            book = Book(title=item["title"], author=item["author"])
            db.session.add(book)
        for key in ("title", "author", "url", "isbn", "publisher", "publish_year", "pages", "price", "summary", "author_bio"):
            if key in item:
                setattr(book, key, item.get(key))
        book.source = "掌阅·" + str(item.get("category") or "全部分类")
        cover_url = item.get("cover_url")
        book.cover_path = cover_url if cover_url and "modal_logo" not in cover_url else None
        book.tags = [lookup[type_name][tag_name] for type_name, tag_name in infer_tags(item).items() if tag_name in lookup.get(type_name, {})]
    for book in db.session.query(Book).all():
        if not book.tags:
            legacy_item = {"title": book.title, "author": book.author, "summary": book.summary, "source": book.source}
            book.tags = [lookup[type_name][tag_name] for type_name, tag_name in infer_tags(legacy_item).items() if tag_name in lookup.get(type_name, {})]
    db.session.commit()
    print("imported and classified", len(rows), "books")
