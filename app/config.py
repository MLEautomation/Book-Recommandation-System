import os

try:
    from dotenv import load_dotenv
except ImportError:

    def load_dotenv(path):
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))


class Config:
    SECRET_KEY = os.getenv("BRS_SECRET_KEY", "replace-this-in-production")
    # MySQL is the deployment default. Set BRS_DATABASE_URL to sqlite for local smoke tests.
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "BRS_DATABASE_URL", "mysql+pymysql://root:password@127.0.0.1:3306/brs"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PAGE_SIZE = 24
    COMMENT_PAGE_SIZE = 20
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    COVER_DIR = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "app", "static", "covers"
    )
