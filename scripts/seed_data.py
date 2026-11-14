import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from app import create_app
from app.extensions import db
from app.models import TagType, Tag, User
from werkzeug.security import generate_password_hash

TAGS = {
    "类型": ["科幻", "推理", "悬疑", "社会", "历史", "科普", "都市", "言情", "武侠", "奇幻", "职场", "心理", "青春", "恐怖", "文学", "传记", "艺术", "生活", "旅游", "少儿", "法律", "哲学", "经管", "医学", "军事", "其他"],
    "发售时间": ["2020年以前", "2020年", "2021年", "2022年", "2023年", "2024年", "2025年"],
    "适合人群": ["儿童", "青少年", "成人", "老年人", "通用"], "篇幅": ["短篇", "中篇", "长篇", "超长篇"],
    "情绪基调": ["治愈", "热血", "温馨", "黑暗", "幽默", "感人", "励志"], "地域背景": ["中国", "日本", "欧美", "其他"],
    "语言": ["中文", "英文", "日文", "其他"]}
app = create_app({"SQLALCHEMY_DATABASE_URI": os.getenv("BRS_DATABASE_URL", "sqlite:///brs.db")})
with app.app_context():
    for name, values in TAGS.items():
        typ = db.session.query(TagType).filter_by(name=name).first() or TagType(name=name)
        db.session.add(typ); db.session.flush()
        for value in values:
            if not db.session.query(Tag).filter_by(type_id=typ.id, name=value).first(): db.session.add(Tag(type_id=typ.id, name=value))
    if not db.session.query(User).filter_by(username="admin").first(): db.session.add(User(username="admin", email="admin@example.com", password_hash=generate_password_hash("Admin1234"), role=1))
    if not db.session.query(User).filter_by(username="demo").first(): db.session.add(User(username="demo", email="demo@example.com", password_hash=generate_password_hash("Demo1234")))
    db.session.commit(); print("seed complete")
