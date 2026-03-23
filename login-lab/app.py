import os

from flask import Flask

from routes import auth_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(auth_bp)
    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
