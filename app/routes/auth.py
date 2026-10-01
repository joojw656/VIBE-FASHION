import os
from functools import wraps

from flask import Blueprint, redirect, render_template, request, session, url_for
from supabase import ClientOptions, create_client

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SITE_URL = os.getenv("SITE_URL", "http://localhost:5000").rstrip("/")

MIN_PASSWORD_LENGTH = 6
VERIFY_OTP_TYPES = {"email", "signup", "recovery", "invite", "magiclink", "email_change"}

# URL 파라미터로 받은 코드만 한국어 메시지로 변환 (임의 문자열은 표시하지 않음)
ERROR_MESSAGES = {
    "email_not_confirmed": "이메일 인증이 완료되지 않았습니다. 메일함에서 인증 링크를 클릭해 주세요.",
    "invalid_credentials": "이메일 또는 비밀번호가 올바르지 않습니다.",
    "current_password_mismatch": "현재 비밀번호가 일치하지 않습니다.",
    "missing_fields": "필수 항목을 모두 입력해 주세요.",
    "password_mismatch": "비밀번호가 일치하지 않습니다.",
    "weak_password": f"비밀번호는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다.",
    "user_already_exists": "이미 가입된 이메일입니다.",
    "invalid_link": "인증 링크가 유효하지 않거나 만료되었습니다. 다시 시도해 주세요.",
    "session_expired": "세션이 만료되었습니다. 비밀번호 찾기를 다시 진행해 주세요.",
    "login_required": "로그인이 필요한 페이지입니다.",
    "rate_limited": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
    "same_password": "새로운 비밀번호가 현재 비밀번호와 동일합니다.",
    "server_error": "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
    "oauth_failed": "카카오 로그인에 실패했습니다. 다시 시도해 주세요.",
}
SUCCESS_MESSAGES = {
    "reset_email_sent": "입력하신 이메일로 비밀번호 재설정 링크를 보냈습니다. 메일함을 확인해 주세요.",
    "password_updated": "비밀번호가 변경되었습니다.",
    "logged_out": "로그아웃되었습니다.",
    "email_confirmed": "이메일 인증이 완료되었습니다.",
    "profile_updated": "회원 정보가 성공적으로 수정되었습니다.",
}


def _get_client():
    """요청마다 새 Supabase 클라이언트를 만들어 사용자 간 인증 세션이 섞이지 않도록 합니다."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print("[Supabase] SUPABASE_URL 또는 SUPABASE_ANON_KEY가 설정되지 않았습니다.")
        return None
    try:
        return create_client(
            SUPABASE_URL,
            SUPABASE_ANON_KEY,
            options=ClientOptions(auto_refresh_token=False, persist_session=False),
        )
    except Exception as exc:
        print(f"[Supabase] 클라이언트 생성 실패: {exc}")
        return None


def _error_code(exc):
    """Supabase 인증 예외를 내부 에러 코드로 변환합니다."""
    code = getattr(exc, "code", None) or ""
    text = str(exc).lower()
    if code == "email_not_confirmed" or "email not confirmed" in text:
        return "email_not_confirmed"
    if code == "invalid_credentials" or "invalid login credentials" in text:
        return "invalid_credentials"
    if code in ("user_already_exists", "email_exists") or "already registered" in text:
        return "user_already_exists"
    if code == "weak_password" or "password should be" in text:
        return "weak_password"
    if code == "same_password":
        return "same_password"
    if code in ("otp_expired", "otp_disabled", "bad_jwt", "flow_state_expired"):
        return "invalid_link"
    if code.startswith("over_") or "rate limit" in text:
        return "rate_limited"
    return "server_error"


def get_messages():
    """URL 파라미터(error/message)를 한국어 메시지로 변환합니다."""
    err = ERROR_MESSAGES.get(request.args.get("error", ""))
    detail = session.pop("auth_error_detail", None)
    if err and detail:
        err = f"{err} ({detail})"
    return {
        "error_message": err,
        "success_message": SUCCESS_MESSAGES.get(request.args.get("message", "")),
    }


def _safe_next(target):
    """오픈 리다이렉트 방지: 같은 사이트 내부 경로만 허용합니다."""
    if target and target.startswith("/") and not target.startswith("//") and "\\" not in target:
        return target
    return None


def _save_session(auth_session, user):
    """Supabase 인증 결과를 Flask session에 저장합니다."""
    meta = user.user_metadata or {}
    session.clear()
    session["user_id"] = user.id
    # 카카오는 이메일 동의 없이 가입할 수 있어 닉네임으로 대체
    session["email"] = user.email or meta.get("name") or meta.get("full_name") or "카카오 회원"
    session["access_token"] = auth_session.access_token
    session["refresh_token"] = auth_session.refresh_token


def login_required(view):
    """Flask session에 user_id가 없으면 로그인 페이지로 보냅니다."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("auth.login", error="login_required", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """[1] 로그인 폼 + 처리"""
    if request.method == "GET":
        return render_template("auth/login.html", next=request.args.get("next", ""), **get_messages())

    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    next_url = _safe_next(request.form.get("next"))
    if not email or not password:
        return redirect(url_for("auth.login", error="missing_fields"))

    client = _get_client()
    if client is None:
        return redirect(url_for("auth.login", error="server_error"))

    try:
        res = client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as exc:
        print(f"[Supabase] 로그인 실패: {exc}")
        return redirect(url_for("auth.login", error=_error_code(exc)))

    if not res.session or not res.user:
        return redirect(url_for("auth.login", error="invalid_credentials"))

    _save_session(res.session, res.user)
    return redirect(next_url or url_for("main.mypage"))


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    """[2] 회원가입 폼 + 처리"""
    if request.method == "GET":
        return render_template("auth/signup.html", **get_messages())

    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "")
    password_confirm = request.form.get("password_confirm", "")

    if not name or not email or not password:
        return redirect(url_for("auth.signup", error="missing_fields"))
    if len(password) < MIN_PASSWORD_LENGTH:
        return redirect(url_for("auth.signup", error="weak_password"))
    if password != password_confirm:
        return redirect(url_for("auth.signup", error="password_mismatch"))

    client = _get_client()
    if client is None:
        return redirect(url_for("auth.signup", error="server_error"))

    try:
        res = client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {
                "email_redirect_to": f"{SITE_URL}/auth/confirm",
                # handle_new_user 트리거가 full_name으로 profiles.name을 채움
                "data": {"full_name": name},
            },
        })
    except Exception as exc:
        print(f"[Supabase] 회원가입 실패: {exc}")
        return redirect(url_for("auth.signup", error=_error_code(exc)))

    # 이미 가입된 이메일이면 Supabase가 identities가 빈 사용자를 반환함
    if res.user is not None and res.user.identities == []:
        return redirect(url_for("auth.signup", error="user_already_exists"))

    return redirect(url_for("auth.signup_complete"))


@auth_bp.route("/signup-complete")
def signup_complete():
    """[3] 인증 메일 발송 안내"""
    return render_template("auth/signup_complete.html")


@auth_bp.route("/confirm")
def confirm():
    """[4] 이메일 인증 링크 처리 (회원가입 인증 / 비밀번호 재설정 공용)"""
    token_hash = request.args.get("token_hash", "")
    otp_type = request.args.get("type", "email")
    if not token_hash or otp_type not in VERIFY_OTP_TYPES:
        return redirect(url_for("auth.login", error="invalid_link"))

    client = _get_client()
    if client is None:
        return redirect(url_for("auth.login", error="server_error"))

    try:
        res = client.auth.verify_otp({"token_hash": token_hash, "type": otp_type})
    except Exception as exc:
        print(f"[Supabase] 이메일 인증 실패: {exc}")
        return redirect(url_for("auth.login", error="invalid_link"))

    if not res.session or not res.user:
        return redirect(url_for("auth.login", error="invalid_link"))

    _save_session(res.session, res.user)
    if otp_type == "recovery":
        return redirect(url_for("auth.reset_password"))
    return redirect(url_for("main.mypage", message="email_confirmed"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """[5] 비밀번호 재설정 메일 발송"""
    if request.method == "GET":
        return render_template("auth/forgot_password.html", **get_messages())

    email = request.form.get("email", "").strip()
    if not email:
        return redirect(url_for("auth.forgot_password", error="missing_fields"))

    client = _get_client()
    if client is None:
        return redirect(url_for("auth.forgot_password", error="server_error"))

    try:
        client.auth.reset_password_for_email(email, {"redirect_to": f"{SITE_URL}/auth/confirm"})
    except Exception as exc:
        print(f"[Supabase] 비밀번호 재설정 메일 발송 실패: {exc}")
        code = _error_code(exc)
        # 가입 여부 노출을 막기 위해 속도 제한 외에는 동일한 성공 메시지 표시
        if code == "rate_limited":
            return redirect(url_for("auth.forgot_password", error=code))

    return redirect(url_for("auth.forgot_password", message="reset_email_sent"))


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """[6] 새 비밀번호 설정 (재설정 링크로 인증된 세션 필요)"""
    access_token = session.get("access_token")
    refresh_token = session.get("refresh_token")
    if not access_token or not refresh_token:
        return redirect(url_for("auth.forgot_password", error="session_expired"))

    if request.method == "GET":
        return render_template("auth/reset_password.html", **get_messages())

    password = request.form.get("password", "")
    password_confirm = request.form.get("password_confirm", "")
    if len(password) < MIN_PASSWORD_LENGTH:
        return redirect(url_for("auth.reset_password", error="weak_password"))
    if password != password_confirm:
        return redirect(url_for("auth.reset_password", error="password_mismatch"))

    client = _get_client()
    if client is None:
        return redirect(url_for("auth.reset_password", error="server_error"))

    try:
        client.auth.set_session(access_token, refresh_token)
        client.auth.update_user({"password": password})
    except Exception as exc:
        print(f"[Supabase] 비밀번호 변경 실패: {exc}")
        code = _error_code(exc)
        if code in ("invalid_link", "server_error"):
            session.clear()
            return redirect(url_for("auth.forgot_password", error="session_expired"))
        return redirect(url_for("auth.reset_password", error=code))

    session.clear()
    return redirect(url_for("auth.login", message="password_updated"))


@auth_bp.route("/kakao")
def kakao_login():
    """카카오 로그인 시작: Supabase OAuth(PKCE) 인증 페이지로 이동"""
    client = _get_client()
    if client is None:
        return redirect(url_for("auth.login", error="server_error"))

    session["oauth_next"] = _safe_next(request.args.get("next"))

    try:
        res = client.auth.sign_in_with_oauth({
            "provider": "kakao",
            "options": {
                "redirect_to": f"{SITE_URL}/auth/callback",
                "query_params": {
                    "scope": "profile_nickname,profile_image",
                },
            },
        })
        # sign_in_with_oauth가 내부적으로 생성한 PKCE verifier를 Flask 세션에 보관하여 콜백 시 검증에 사용
        session["pkce_verifier"] = client.auth._storage.get_item(
            f"{client.auth._storage_key}-code-verifier"
        )
    except Exception as exc:
        print(f"[Supabase] 카카오 로그인 URL 생성 실패: {exc}")
        return redirect(url_for("auth.login", error="oauth_failed"))

    return redirect(res.url)


@auth_bp.route("/callback")
def oauth_callback():
    """카카오 로그인 완료 후 돌아오는 주소: code를 세션으로 교환"""
    code = request.args.get("code", "")
    verifier = session.pop("pkce_verifier", None)
    next_url = session.pop("oauth_next", None)

    # 실패 원인을 정확히 알 수 있도록 상세 메시지를 세션/파라미터에 기록
    fail_detail = None
    if request.args.get("error"):
        fail_detail = f"카카오 응답 오류: {request.args.get('error_description') or request.args.get('error')}"
    elif not code:
        fail_detail = "카카오 인증 코드가 누락되었습니다."
    elif not verifier:
        fail_detail = "세션 검증값(PKCE verifier)이 유실되었습니다. 브라우저 쿠키 설정을 확인해 주세요."

    if fail_detail:
        print(f"[Supabase] {fail_detail}")
        session["auth_error_detail"] = fail_detail
        return redirect(url_for("auth.login", error="oauth_failed"))

    client = _get_client()
    if client is None:
        session["auth_error_detail"] = "데이터베이스 연결에 실패했습니다."
        return redirect(url_for("auth.login", error="server_error"))

    try:
        res = client.auth.exchange_code_for_session({"auth_code": code, "code_verifier": verifier})
    except Exception as exc:
        err_msg = str(exc)
        print(f"[Supabase] 카카오 로그인 세션 교환 실패: {err_msg}")
        session["auth_error_detail"] = f"세션 교환 오류: {err_msg}"
        return redirect(url_for("auth.login", error="oauth_failed"))

    if not res.session or not res.user:
        session["auth_error_detail"] = "사용자 세션 정보를 가져오지 못했습니다."
        return redirect(url_for("auth.login", error="oauth_failed"))

    _save_session(res.session, res.user)
    return redirect(next_url or url_for("main.mypage"))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """로그아웃: Flask session 삭제"""
    session.clear()
    return redirect(url_for("auth.login", message="logged_out"))
