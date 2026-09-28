import os
from flask import Flask
from dotenv import load_dotenv

# .env 파일이 있으면 환경 변수 로드
load_dotenv()

def create_app():
    """
    [애플리케이션 팩토리 함수]
    Flask 인스턴스를 생성하고 환경 설정 및 블루프린트(라우트)를 등록합니다.
    앱 팩토리 패턴을 사용하면 테스트가 용이해지고 확장성이 높아집니다.
    """
    app = Flask(__name__)

    # 기본 설정
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "default-dev-secret-key")

    # 블루프린트(라우트) 등록
    from app.routes.main import main_bp
    app.register_blueprint(main_bp)

    return app
