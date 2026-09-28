"""
VIBE-FASHION 실행 진입점 (Entry Point)
이 파일을 실행하여 로컬 개발 서버를 가동합니다.
"""
from app import create_app

# 애플리케이션 팩토리를 통해 Flask 앱 인스턴스 생성
app = create_app()

if __name__ == "__main__":
    # debug=True: 소스 코드 수정 시 서버 자동 재시작 및 디버그 페이지 제공
    print("🚀 VIBE-FASHION 쇼핑몰 서버가 시작됩니다! http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)
