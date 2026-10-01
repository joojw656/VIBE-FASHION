import hmac
import os
import secrets

from flask import Flask, abort, request, session
from dotenv import load_dotenv

# .env 파일이 있으면 환경 변수 로드
load_dotenv()


def _csrf_token():
    """세션별 CSRF 토큰을 발급합니다."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def create_app():
    """
    [애플리케이션 팩토리 함수]
    Flask 인스턴스를 생성하고 환경 설정 및 블루프린트(라우트)를 등록합니다.
    앱 팩토리 패턴을 사용하면 테스트가 용이해지고 확장성이 높아집니다.
    """
    app = Flask(__name__)

    # 기본 설정 (SECRET_KEY가 없으면 추측 불가능한 임시 키 사용 → 재시작 시 로그아웃됨)
    secret_key = os.getenv("SECRET_KEY")
    if not secret_key:
        print("[경고] SECRET_KEY가 설정되지 않아 임시 키를 사용합니다.")
        secret_key = secrets.token_hex(32)
    app.config["SECRET_KEY"] = secret_key
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    # 모든 POST 요청에 CSRF 토큰 검사 (Form의 csrf_token 또는 Header의 X-CSRFToken)
    @app.before_request
    def _check_csrf():
        if request.method == "POST":
            # Form 데이터, JSON 바디, 또는 HTTP 헤더에서 CSRF 토큰 확인
            req_json = request.get_json(silent=True) or {}
            sent = (
                request.form.get("csrf_token")
                or req_json.get("csrf_token")
                or request.headers.get("X-CSRFToken")
                or request.headers.get("X-CSRF-Token")
                or ""
            )
            expected = session.get("csrf_token", "")
            if not expected or not hmac.compare_digest(sent, expected):
                abort(400)

    app.jinja_env.globals["csrf_token"] = _csrf_token

    # 블루프린트(라우트) 등록
    from app.routes.main import main_bp
    from app.routes.auth import auth_bp
    from app.routes.cart import cart_bp, get_cart_count
    from app.routes.order import order_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(order_bp)

    # 모든 템플릿에서 장바구니 개수 조회 가능하도록 컨텍스트 프로세서 등록
    @app.context_processor
    def inject_cart_count():
        try:
            return {"cart_count": get_cart_count()}
        except Exception:
            return {"cart_count": 0}

    return app
