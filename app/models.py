from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .extensions import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="normal")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TagType(Base):
    __tablename__ = "tag_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True)
    tags = relationship("Tag", back_populates="tag_type", cascade="all, delete-orphan")


class Tag(Base):
    __tablename__ = "tags"
    id: Mapped[int] = mapped_column(primary_key=True)
    type_id: Mapped[int] = mapped_column(ForeignKey("tag_types.id"), index=True)
    name: Mapped[str] = mapped_column(String(32))
    tag_type = relationship("TagType", back_populates="tags")
    __table_args__ = (UniqueConstraint("type_id", "name"),)


class Book(Base):
    __tablename__ = "books"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200), index=True)
    author: Mapped[str] = mapped_column(String(160))
    url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    isbn: Mapped[Optional[str]] = mapped_column(String(32), unique=True, nullable=True)
    publisher: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    publish_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pages: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    cover_path: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author_bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    tags = relationship("Tag", secondary="book_tags")


class BookTag(Base):
    __tablename__ = "book_tags"
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"), primary_key=True)


class Favorite(Base):
    __tablename__ = "favorites"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "book_id"),)


class Comment(Base):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("comments.id"), nullable=True
    )
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True
    )


class CommentAttitude(Base):
    __tablename__ = "comment_attitudes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    comment_id: Mapped[int] = mapped_column(ForeignKey("comments.id"), index=True)
    attitude_type: Mapped[int] = mapped_column(Integer)  # 1 like, 2 dislike
    status: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "comment_id"),)


class BookAttitude(Base):
    __tablename__ = "book_attitudes"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), index=True)
    attitude_type: Mapped[int] = mapped_column(Integer)  # 1 like, 2 dislike
    status: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "book_id"),)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    ip: Mapped[str] = mapped_column(String(64))
    ua_hash: Mapped[str] = mapped_column(String(64))
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    banned_until: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("ip", "ua_hash"),)


class UserInterest(Base):
    __tablename__ = "user_interests"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"), primary_key=True)
