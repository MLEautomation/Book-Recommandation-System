from flask import Flask, render_template
from .config import Config
from .extensions import db
from .models import *  # noqa: F401,F403
from .routes import api, pages


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    app.register_blueprint(pages)
    app.register_blueprint(api, url_prefix="/api")
    with app.app_context():
        db.create_all()
    return app

