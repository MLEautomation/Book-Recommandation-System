from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, scoped_session, sessionmaker


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self):
        self.engine = None
        self.session = None

    def init_app(self, app: Flask):
        self.engine = create_engine(app.config["SQLALCHEMY_DATABASE_URI"], pool_pre_ping=True)
        self.session = scoped_session(sessionmaker(bind=self.engine, expire_on_commit=False))
        app.teardown_appcontext(self.remove)

    def remove(self, _exception=None):
        if self.session:
            self.session.remove()

    def create_all(self):
        Base.metadata.create_all(self.engine)


db = Database()

