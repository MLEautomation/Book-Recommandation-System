import hashlib
import json
import math
import os
import re
import secrets
from collections import Counter
from datetime import datetime, timedelta
from functools import wraps
from flask import (
    Blueprint,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func, or_
from werkzeug.security import check_password_hash, generate_password_hash
from .extensions import db
from .models import (
    Book,
    BookAttitude,
    BookTag,
    Comment,
    CommentAttitude,
    Favorite,
    LoginAttempt,
    Tag,
    TagType,
    User,
    UserInterest,
)
from .ai_recommender import recommend_from_prompt

pages = Blueprint("pages", __name__)
api = Blueprint("api", __name__)


RECOMMEND_TAG_TYPE_WEIGHTS = {
    "类型": 1.3,
    "地域背景": 1.0,
    "发售时间": 0.6,
    "篇幅": 0.5,
}
LOW_SIGNAL_TAG_NAMES = {"通用", "其他", "未标注"}


@pages.get("/")
def home():
    return render_template("index.html")


@pages.get("/<page>")
def page(page):
    allowed = {
        "filters": "filters.html",
        "ranking": "ranking.html",
        "login": "login.html",
        "register": "register.html",
        "profile": "profile.html",
        "favorites": "favorites.html",
        "my-comments": "my_comments.html",
        "admin": "admin.html",
        "import": "import.html",
        "user-agreement": "user_agreement.html",
        "privacy-policy": "privacy_policy.html",
    }
    if page == "book":
        abort(404)
    if page not in allowed:
        abort(404)
    if page in {"admin", "import"}:
        user = current_user()
        if not user:
            return redirect(url_for("pages.page", page="login"))
        if user.role != 1:
            abort(403)
    return render_template(allowed[page])


@pages.get("/book/<int:book_id>")
def book_page(book_id):
    return render_template("book_detail.html", book_id=book_id)


def current_user():
    uid = session.get("user_id")
    return db.session.get(User, uid) if uid else None


def auth_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return jsonify(error="请先登录"), 401
        return fn(*args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify(error="请先登录"), 401
        if user.role != 1:
            return jsonify(error="仅管理员可访问"), 403
        return fn(*args, **kwargs)

    return wrapper


def book_json(book):
    book_attitudes = (
        db.session.query(BookAttitude)
        .filter(BookAttitude.book_id == book.id, BookAttitude.status == 1)
        .all()
    )
    user_attitude = None
    user = current_user()
    is_favorite = False
    if user:
        row = (
            db.session.query(BookAttitude)
            .filter_by(user_id=user.id, book_id=book.id, status=1)
            .first()
        )
        user_attitude = row.attitude_type if row else None
        is_favorite = bool(
            db.session.query(Favorite)
            .filter_by(user_id=user.id, book_id=book.id)
            .first()
        )
    return {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "publisher": book.publisher,
        "publish_year": book.publish_year,
        "pages": book.pages,
        "price": float(book.price) if book.price is not None else None,
        "isbn": book.isbn,
        "url": book.url,
        "cover_path": book.cover_path,
        "summary": book.summary,
        "author_bio": book.author_bio,
        "source": book.source,
        "likes": sum(a.attitude_type == 1 for a in book_attitudes),
        "dislikes": sum(a.attitude_type == 2 for a in book_attitudes),
        "my_attitude": user_attitude,
        "is_favorite": is_favorite,
        "tags": [
            {"id": t.id, "type": t.tag_type.name, "name": t.name} for t in book.tags
        ],
    }


def comment_json(c):
    attitudes = (
        db.session.query(CommentAttitude)
        .filter(CommentAttitude.comment_id == c.id, CommentAttitude.status == 1)
        .all()
    )
    user = db.session.get(User, c.user_id)
    my_attitude = None
    viewer = current_user()
    is_mine = bool(viewer and viewer.id == c.user_id)
    if viewer:
        row = (
            db.session.query(CommentAttitude)
            .filter_by(user_id=viewer.id, comment_id=c.id, status=1)
            .first()
        )
        my_attitude = row.attitude_type if row else None
    return {
        "id": c.id,
        "book_id": c.book_id,
        "user_id": c.user_id,
        "content": c.content,
        "parent_id": c.parent_id,
        "username": user.username if user else "未知用户",
        "my_attitude": my_attitude,
        "is_mine": is_mine,
        "created_at": c.created_at.isoformat(),
        "likes": sum(a.attitude_type == 1 for a in attitudes),
        "dislikes": sum(a.attitude_type == 2 for a in attitudes),
    }


def recommend_tag_weight(tag):
    if tag.name in LOW_SIGNAL_TAG_NAMES:
        return 0.2
    return RECOMMEND_TAG_TYPE_WEIGHTS.get(tag.tag_type.name, 1.0)


@api.get("/session")
def session_api():
    u = current_user()
    return jsonify(
        user={"id": u.id, "username": u.username, "role": u.role} if u else None
    )


@api.get("/captcha")
def captcha():
    code = "".join(secrets.choice("23456789ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(5))
    session["captcha"] = code
    return jsonify(code=code)


@api.get("/tags")
def tags_api():
    rows = db.session.query(TagType).order_by(TagType.id).all()
    return jsonify(
        items=[
            {
                "id": x.id,
                "name": x.name,
                "tags": [
                    {"id": t.id, "name": t.name} for t in x.tags if t.name != "未标注"
                ],
            }
            for x in rows
        ]
    )


@api.get("/books")
def books_api():
    page = max(request.args.get("page", 1, type=int), 1)
    size = min(max(request.args.get("size", 24, type=int), 1), 100)
    selected = [x for x in request.args.get("tags", "").split(",") if x]
    search = request.args.get("q", "").strip()
    q = db.session.query(Book)
    if search:
        pattern = f"%{search}%"
        q = q.filter(
            or_(
                Book.title.ilike(pattern),
                Book.author.ilike(pattern),
                Book.publisher.ilike(pattern),
                Book.summary.ilike(pattern),
            )
        )
    for tag_id in selected:
        q = q.filter(Book.tags.any(Tag.id == int(tag_id)))
    total = q.distinct().count()
    books = q.distinct().order_by(Book.id).offset((page - 1) * size).limit(size).all()
    return jsonify(
        items=[book_json(b) for b in books],
        page=page,
        size=size,
        total=total,
        pages=math.ceil(total / size) if total else 0,
    )


@api.post("/qa/recommend")
def qa_recommend():
    data = request.get_json(silent=True) or {}
    prompt = str(data.get("prompt") or "").strip()
    if not prompt:
        return jsonify(error="请输入想看的内容或偏好"), 400
    try:
        result = recommend_from_prompt(prompt)
    except ValueError as exc:
        return jsonify(error=str(exc)), 503
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 502
    return jsonify(result)


@api.get("/books/<int:book_id>")
def book_api(book_id):
    book = db.session.get(Book, book_id)
    if not book:
        return jsonify(error="图书不存在"), 404
    return jsonify(book=book_json(book))


@api.get("/me/favorite-ids")
@auth_required
def favorite_ids():
    u = current_user()
    return jsonify(
        ids=[
            x.book_id for x in db.session.query(Favorite).filter_by(user_id=u.id).all()
        ]
    )


@api.post("/favorites")
@auth_required
def add_favorite():
    u = current_user()
    data = request.get_json(silent=True) or {}
    bid = data.get("book_id")
    if not db.session.get(Book, bid):
        return jsonify(error="图书不存在"), 404
    if not db.session.query(Favorite).filter_by(user_id=u.id, book_id=bid).first():
        db.session.add(Favorite(user_id=u.id, book_id=bid))
        db.session.commit()
    return jsonify(ok=True)


@api.delete("/favorites")
@auth_required
def remove_favorite():
    u = current_user()
    bid = (request.get_json(silent=True) or {}).get("book_id")
    row = db.session.query(Favorite).filter_by(user_id=u.id, book_id=bid).first()
    if row:
        db.session.delete(row)
        db.session.commit()
    return jsonify(ok=True)


@api.get("/books/<int:book_id>/comments")
def comments_api(book_id):
    sort = request.args.get("sort", "hot")
    page = max(request.args.get("page", 1, type=int), 1)
    rows = db.session.query(Comment).filter_by(book_id=book_id, parent_id=None).all()
    normal, pinned = [], []
    for c in rows:
        item = comment_json(c)
        score = item["likes"] + item["dislikes"]
        is_pinned = (
            score >= 10
            and item["dislikes"] > 0
            and item["likes"] / item["dislikes"] <= 0.25
        )
        (pinned if is_pinned else normal).append(item)
    normal.sort(
        key=lambda x: (
            -(x["likes"] + x["dislikes"]) if sort == "hot" else "",
            x["created_at"],
        ),
        reverse=sort != "hot",
    )
    pinned.sort(key=lambda x: x["created_at"], reverse=True)
    start = (page - 1) * 20
    return jsonify(
        normal=normal[start : start + 20], pinned=pinned, page=page, total=len(normal)
    )


@api.post("/books/<int:book_id>/attitude")
@auth_required
def book_attitude(book_id):
    data = request.get_json(silent=True) or {}
    typ = int(data.get("type", 0))
    u = current_user()
    if not db.session.get(Book, book_id):
        return jsonify(error="图书不存在"), 404
    if typ not in (0, 1, 2):
        return jsonify(error="态度类型错误"), 400
    row = (
        db.session.query(BookAttitude).filter_by(user_id=u.id, book_id=book_id).first()
    )
    if not row:
        db.session.add(
            BookAttitude(
                user_id=u.id, book_id=book_id, attitude_type=typ or 1, status=1
            )
        )
    elif typ == 0:
        row.status = 0
    elif row.status == 1 and row.attitude_type == typ:
        row.status = 0
    elif row.status == 1:
        return jsonify(error="请先取消当前态度"), 409
    else:
        row.attitude_type, row.status = typ, 1
    db.session.commit()
    return jsonify(ok=True)


@api.post("/books/<int:book_id>/comments")
@auth_required
def create_comment(book_id):
    data = request.get_json(silent=True) or {}
    content = str(data.get("content", "")).strip()
    if not content:
        return jsonify(error="评论内容不能为空"), 400
    if not db.session.get(Book, book_id):
        return jsonify(error="图书不存在"), 404
    parent_id = data.get("parent_id")
    if parent_id and not db.session.get(Comment, parent_id):
        return jsonify(error="父评论不存在"), 400
    c = Comment(
        book_id=book_id, user_id=current_user().id, parent_id=parent_id, content=content
    )
    db.session.add(c)
    db.session.commit()
    return jsonify(comment=comment_json(c)), 201


@api.post("/comments/<int:comment_id>/attitude")
@auth_required
def attitude(comment_id):
    data = request.get_json(silent=True) or {}
    typ = int(data.get("type", 0))
    u = current_user()
    if typ not in (0, 1, 2):
        return jsonify(error="态度类型错误"), 400
    row = (
        db.session.query(CommentAttitude)
        .filter_by(user_id=u.id, comment_id=comment_id)
        .first()
    )
    if not row:
        db.session.add(
            CommentAttitude(
                user_id=u.id, comment_id=comment_id, attitude_type=typ or 1, status=1
            )
        )
    elif typ == 0:
        row.status = 0
    elif row.status == 1 and row.attitude_type == typ:
        row.status = 0
    elif row.status == 1:
        return jsonify(error="请先取消当前态度"), 409
    else:
        row.attitude_type, row.status = typ, 1
    db.session.commit()
    return jsonify(ok=True)


@api.delete("/comments/<int:comment_id>")
@auth_required
def delete_comment(comment_id):
    u = current_user()
    c = db.session.get(Comment, comment_id)
    if not c or (c.user_id != u.id and u.role != 1):
        return jsonify(error="无权删除"), 403
    ids = [comment_id]
    changed = True
    while changed:
        kids = [
            x.id
            for x in db.session.query(Comment).filter(Comment.parent_id.in_(ids)).all()
        ]
        changed = bool(kids)
        ids.extend(kids)
    db.session.query(CommentAttitude).filter(
        CommentAttitude.comment_id.in_(ids)
    ).delete(synchronize_session=False)
    db.session.query(Comment).filter(Comment.id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.commit()
    return jsonify(ok=True)


@api.post("/auth/register")
def register():
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))
    captcha = str(data.get("captcha", "")).upper()
    if session.get("captcha") and captcha != session.get("captcha"):
        return jsonify(error="图形验证码不正确"), 400
    if not re.match(r"^[\u4e00-\u9fa5A-Za-z0-9_+\-=/*]{2,12}$", username):
        return jsonify(error="用户名格式错误"), 400
    if not re.match(r"^[^\s@]+@[^\s@]+\.[A-Za-z]{2,}$", email):
        return jsonify(error="邮箱格式错误"), 400
    if not data.get("agree"):
        return jsonify(error="请先同意用户协议和隐私政策"), 400
    if (
        len(password) < 8
        or not re.search(r"[A-Za-z]", password)
        or not re.search(r"[0-9]", password)
    ):
        return jsonify(error="密码至少 8 位且需包含字母和数字"), 400
    if (
        db.session.query(User)
        .filter((User.username == username) | (User.email == email))
        .first()
    ):
        return jsonify(error="用户名或邮箱已存在"), 409
    u = User(
        username=username, email=email, password_hash=generate_password_hash(password)
    )
    db.session.add(u)
    db.session.commit()
    return jsonify(ok=True), 201


@api.post("/auth/login")
def login():
    data = request.get_json(silent=True) or {}
    account = str(data.get("account", "")).strip()
    password = str(data.get("password", ""))
    u = (
        db.session.query(User)
        .filter((User.username == account) | (User.email == account.lower()))
        .first()
    )
    if not u or not check_password_hash(u.password_hash, password):
        return jsonify(error="账号不存在或密码错误"), 401
    if u.status == "banned":
        return jsonify(error="账号已被封禁，请联系管理员"), 403
    session.clear()
    session["user_id"] = u.id
    return jsonify(user={"id": u.id, "username": u.username, "role": u.role})


@api.post("/auth/logout")
def logout():
    session.clear()
    return jsonify(ok=True)


@api.get("/ranking")
def ranking():
    typ = request.args.get("type", "hot")
    page = max(request.args.get("page", 1, type=int), 1)
    books = db.session.query(Book).order_by(Book.id).all()
    favorite_counts = dict(
        db.session.query(Favorite.book_id, func.count(Favorite.id))
        .group_by(Favorite.book_id)
        .all()
    )
    comment_counts = dict(
        db.session.query(Comment.book_id, func.count(Comment.id))
        .group_by(Comment.book_id)
        .all()
    )
    attitude_counts = {
        (book_id, attitude_type): count
        for book_id, attitude_type, count in db.session.query(
            BookAttitude.book_id,
            BookAttitude.attitude_type,
            func.count(BookAttitude.id),
        )
        .filter(BookAttitude.status == 1)
        .group_by(BookAttitude.book_id, BookAttitude.attitude_type)
        .all()
    }
    rows = []
    for b in books:
        fav = favorite_counts.get(b.id, 0)
        cs = comment_counts.get(b.id, 0)
        likes = attitude_counts.get((b.id, 1), 0)
        dislikes = attitude_counts.get((b.id, 2), 0)
        metric = {
            "hot": fav + likes,
            "favorite": fav,
            "like": likes,
            "discuss": cs,
            "worst": dislikes,
        }.get(typ, fav + likes)
        rows.append({"book": book_json(b), "metric": metric})
    rows.sort(key=lambda x: (-x["metric"], x["book"]["id"]))
    start = (page - 1) * 10
    return jsonify(
        items=rows[start : start + 10],
        page=page,
        total=len(rows),
        pages=min(math.ceil(len(rows) / 10), 10),
    )


@api.get("/me/profile")
@auth_required
def profile():
    u = current_user()
    interests = db.session.query(UserInterest).filter_by(user_id=u.id).all()
    return jsonify(
        user={
            "id": u.id,
            "username": u.username,
            "email": u.email,
            "created_at": u.created_at.isoformat(),
        },
        interest_ids=[x.tag_id for x in interests],
    )


@api.put("/me/profile")
@auth_required
def update_profile():
    u = current_user()
    ids = (request.get_json(silent=True) or {}).get("interest_ids", [])
    db.session.query(UserInterest).filter_by(user_id=u.id).delete()
    db.session.add_all([UserInterest(user_id=u.id, tag_id=int(x)) for x in ids])
    db.session.commit()
    return jsonify(ok=True)


@api.get("/me/favorites")
@auth_required
def my_favorites():
    u = current_user()
    page = max(request.args.get("page", 1, type=int), 1)
    size = 12
    rows = (
        db.session.query(Favorite)
        .filter_by(user_id=u.id)
        .order_by(Favorite.created_at.desc())
        .all()
    )
    start = (page - 1) * size
    return jsonify(
        items=[
            book_json(db.session.get(Book, x.book_id))
            for x in rows[start : start + size]
        ],
        page=page,
        total=len(rows),
    )


@api.get("/me/comments")
@auth_required
def my_comments():
    u = current_user()
    page = max(request.args.get("page", 1, type=int), 1)
    size = 10
    rows = (
        db.session.query(Comment)
        .filter_by(user_id=u.id, parent_id=None)
        .order_by(Comment.created_at.desc())
        .all()
    )
    items = []
    for comment in rows[(page - 1) * size : page * size]:
        item = comment_json(comment)
        book = db.session.get(Book, comment.book_id)
        item["book"] = (
            {
                "id": book.id,
                "title": book.title,
                "author": book.author,
                "cover_path": book.cover_path,
            }
            if book
            else None
        )
        items.append(item)
    return jsonify(
        items=items,
        page=page,
        size=size,
        total=len(rows),
        pages=math.ceil(len(rows) / size) if rows else 0,
    )


@api.get("/me/replies")
@auth_required
def my_replies():
    u = current_user()
    rows = (
        db.session.query(Comment)
        .filter(Comment.user_id == u.id, Comment.parent_id.is_not(None))
        .order_by(Comment.created_at.desc())
        .all()
    )
    return jsonify(items=[comment_json(x) for x in rows])


@api.get("/recommend")
@auth_required
def recommend():
    u = current_user()
    offset = max(request.args.get("offset", 0, type=int), 0)
    favorite_rows = (
        db.session.query(Favorite)
        .filter_by(user_id=u.id)
        .order_by(Favorite.created_at.desc())
        .all()
    )
    favorite_ids = {x.book_id for x in favorite_rows}
    interest_ids = {
        x.tag_id for x in db.session.query(UserInterest).filter_by(user_id=u.id).all()
    }
    favorite_books = [db.session.get(Book, row.book_id) for row in favorite_rows]
    favorite_tag_counts = Counter(
        tag.id for book in favorite_books if book for tag in book.tags
    )
    interacted_ids = {
        x.book_id for x in db.session.query(Comment).filter_by(user_id=u.id).all()
    }
    favorite_counts = dict(
        db.session.query(Favorite.book_id, func.count(Favorite.id))
        .group_by(Favorite.book_id)
        .all()
    )
    like_counts = dict(
        db.session.query(BookAttitude.book_id, func.count(BookAttitude.id))
        .filter(BookAttitude.attitude_type == 1, BookAttitude.status == 1)
        .group_by(BookAttitude.book_id)
        .all()
    )
    comment_like_counts = dict(
        db.session.query(Comment.book_id, func.count(CommentAttitude.id))
        .join(CommentAttitude, CommentAttitude.comment_id == Comment.id)
        .filter(
            CommentAttitude.attitude_type == 1,
            CommentAttitude.status == 1,
        )
        .group_by(Comment.book_id)
        .all()
    )
    scored = []
    for book in db.session.query(Book).all():
        if book.id in favorite_ids:
            continue
        interest_score = sum(
            5 * recommend_tag_weight(tag) for tag in book.tags if tag.id in interest_ids
        )
        favorite_tag_score = sum(
            2.5 * favorite_tag_counts.get(tag.id, 0) * recommend_tag_weight(tag)
            for tag in book.tags
            if tag.id in favorite_tag_counts
        )
        behavior_score = 0
        if book.id in interacted_ids:
            behavior_score += 1
        favorite_count = favorite_counts.get(book.id, 0)
        like_count = like_counts.get(book.id, 0)
        comment_like_count = comment_like_counts.get(book.id, 0)
        hot_score = favorite_count + like_count + comment_like_count
        scored.append(
            (
                interest_score + favorite_tag_score + hot_score * 0.3 + behavior_score,
                book.id,
                book,
            )
        )
    scored.sort(key=lambda item: (-item[0], item[1]))
    books = [item[2] for item in scored]
    return jsonify(
        items=[book_json(x) for x in books[offset : offset + 10]],
        offset=offset,
        total=len(books),
    )


@api.get("/admin/users")
@admin_required
def admin_users():
    return jsonify(
        items=[
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "status": u.status,
                "created_at": u.created_at.isoformat(),
            }
            for u in db.session.query(User).order_by(User.id).all()
        ]
    )


@api.post("/admin/users/<int:user_id>/<action>")
@admin_required
def admin_user_action(user_id, action):
    u = db.session.get(User, user_id)
    me = current_user()
    if not u or u.id == me.id or u.role == 1 or action not in ("ban", "unban"):
        return jsonify(error="操作不允许"), 400
    u.status = "banned" if action == "ban" else "normal"
    db.session.commit()
    return jsonify(ok=True)


@api.get("/admin/comments")
@admin_required
def admin_comments():
    return jsonify(
        items=[
            comment_json(c)
            for c in db.session.query(Comment).order_by(Comment.created_at.desc()).all()
        ]
    )


@api.delete("/admin/comments/<int:comment_id>")
@admin_required
def admin_delete_comment(comment_id):
    c = db.session.get(Comment, comment_id)
    if not c:
        return jsonify(error="评论不存在"), 404
    ids = [comment_id]
    while True:
        kids = [
            x.id
            for x in db.session.query(Comment).filter(Comment.parent_id.in_(ids)).all()
        ]
        if not kids:
            break
        ids.extend(kids)
    db.session.query(CommentAttitude).filter(
        CommentAttitude.comment_id.in_(ids)
    ).delete(synchronize_session=False)
    db.session.query(Comment).filter(Comment.id.in_(ids)).delete(
        synchronize_session=False
    )
    db.session.commit()
    return jsonify(ok=True)


@api.post("/admin/import")
@admin_required
def admin_import():
    upload = request.files.get("file")
    if not upload:
        return jsonify(error="请选择 JSON 文件"), 400
    try:
        payload = json.load(upload.stream)
    except (ValueError, UnicodeDecodeError):
        return jsonify(error="JSON 文件格式错误"), 400
    rows = (
        payload
        if isinstance(payload, list)
        else payload.get("books", payload.get("items", []))
    )
    report = {"added": 0, "updated": 0, "skipped": 0, "failed": 0, "failures": []}
    allowed = {
        x.name: {t.name: t for t in x.tags} for x in db.session.query(TagType).all()
    }
    for index, item in enumerate(rows, 1):
        try:
            if not item.get("title") or not item.get("author"):
                raise ValueError("缺少书名或作者")
            tags = item.get("tags", {})
            for type_name, tag_name in tags.items():
                if type_name not in allowed or tag_name not in allowed[type_name]:
                    raise ValueError("标签不在允许范围内")
            book = (
                db.session.query(Book).filter_by(isbn=item.get("isbn")).first()
                if item.get("isbn")
                else None
            )
            if not book:
                book = (
                    db.session.query(Book)
                    .filter_by(title=item["title"], author=item["author"])
                    .first()
                )
            is_new = book is None
            if is_new:
                book = Book(title=item["title"], author=item["author"])
                db.session.add(book)
            for key in (
                "url",
                "source",
                "isbn",
                "publisher",
                "publish_year",
                "pages",
                "price",
                "cover_path",
                "summary",
                "author_bio",
            ):
                if key in item:
                    setattr(book, key, item[key])
            db.session.flush()
            book.tags = [allowed[k][v] for k, v in tags.items()]
            report["added" if is_new else "updated"] += 1
        except Exception as exc:
            report["failed"] += 1
            report["failures"].append({"row": index, "reason": str(exc)})
            db.session.rollback()
    db.session.commit()
    return jsonify(report=report)
