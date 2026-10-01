import os
from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for
from supabase import create_client

from app.routes.auth import SUPABASE_ANON_KEY, SUPABASE_URL, get_messages, login_required

# 'main' 블루프린트 생성
# 블루프린트를 사용하면 라우트(URL 핸들러)를 기능별 파일로 분리하여 관리할 수 있습니다.
main_bp = Blueprint("main", __name__)

PRODUCT_IMAGE_OVERRIDES = {
    "11111111-1111-1111-1111-111111111111": "/static/images/basic-crop-tee.jpg",
    "22222222-2222-2222-2222-222222222222": "https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=800&q=80",
    "33333333-3333-3333-3333-333333333333": "https://images.unsplash.com/photo-1551028719-00167b16eac5?w=800&q=80",
    "44444444-4444-4444-4444-444444444444": "https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=800&q=80",
    "55555555-5555-5555-5555-555555555555": "/static/images/minimal-leather-crossbag.jpg",
    "66666666-6666-6666-6666-666666666666": "/static/images/square-toe-chunky-loafer.jpg",
    "77777777-7777-7777-7777-777777777777": "/static/images/two-tone-ballcap.jpg",
    "88888888-8888-8888-8888-888888888888": "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=800&q=80",
    "99999999-9999-9999-9999-999999999999": "https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=800&q=80",
    "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa": "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=800&q=80",
}
FEATURED_FALLBACK = [
    {"id": "11111111-1111-1111-1111-111111111111", "name": "베이직 크롭 티셔츠", "price": 22000, "discount_price": 15900},
    {"id": "22222222-2222-2222-2222-222222222222", "name": "와이드 데님 팬츠", "price": 32000, "discount_price": 25900},
    {"id": "33333333-3333-3333-3333-333333333333", "name": "오버핏 코튼 자켓", "price": 49000, "discount_price": 38900},
    {"id": "44444444-4444-4444-4444-444444444444", "name": "플로럴 미디 원피스", "price": 36000, "discount_price": 28900},
    {"id": "99999999-9999-9999-9999-999999999999", "name": "클래식 캐시미어 블렌드 싱글 코트", "price": 79000, "discount_price": 59900},
    {"id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "name": "미니멀 세미오버 테일러드 블레이저", "price": 59000, "discount_price": 46900},
]

# 앱 기동 시점에 클라이언트를 한 번만 생성 (연결 실패해도 앱은 계속 뜨도록 처리)
try:
    supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY) if SUPABASE_URL and SUPABASE_ANON_KEY else None
except Exception as exc:
    print(f"[Supabase] 클라이언트 생성 실패: {exc}")
    supabase = None


def _format_price(value):
    """숫자 가격을 '19,900원' 형태의 문자열로 변환합니다."""
    try:
        return f"{int(value):,}원"
    except (TypeError, ValueError):
        return "가격 문의"


def _prepare_product(product):
    """상품 이미지 경로와 표시용 가격(할인가 우선)을 채워 넣습니다."""
    image_url = PRODUCT_IMAGE_OVERRIDES.get(str(product.get("id")))
    if image_url:
        product["thumbnail_url"] = image_url
    product["image_url"] = product.get("thumbnail_url")
    product["formatted_price"] = _format_price(product.get("discount_price") or product.get("price"))
    return product


def get_featured_products(limit=8):
    """
    is_active=true 이고 is_featured=true 인 상품을 최대 limit개 조회합니다.
    Supabase 연결/조회 실패 시에도 앱이 죽지 않도록 빈 리스트를 반환합니다.
    """
    if supabase is None:
        print("[Supabase] 클라이언트가 없어 샘플 이달의 상품을 표시합니다.")
        products = [dict(product) for product in FEATURED_FALLBACK[:limit]]
    else:
        try:
            response = (
                supabase.table("products")
                .select("id, name, price, discount_price, thumbnail_url")
                .eq("is_active", True)
                .eq("is_featured", True)
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
            products = response.data or []
        except Exception as exc:
            print(f"[Supabase] products 조회 실패, 샘플 이달의 상품을 표시합니다: {exc}")
            products = [dict(product) for product in FEATURED_FALLBACK[:limit]]

    return [_prepare_product(product) for product in products]


@main_bp.route("/")
def index():
    """
    메인 페이지:
    히어로 배너와 Supabase에서 조회한 '지금 인기 추천 아이템' 목록을 화면에 렌더링합니다.
    """
    products = get_featured_products(limit=6)
    return render_template("index.html", products=products)

@main_bp.route("/mypage", methods=["GET", "POST"])
@login_required
def mypage():
    """
    마이페이지: 로그인한 사용자의 정보 조회 및 수정
    - 탭1: 내 정보 (이름, 이메일, 기본 배송지)
    - 탭2: 주문 내역
    - 탭3: 환불 내역
    """
    user_id = session.get("user_id")
    profile = {}
    default_address = session.get("default_address", "")

    # Supabase 클라이언트 준비 (service key 우선 사용)
    service_key = os.getenv("SUPABASE_SERVICE_KEY") or SUPABASE_ANON_KEY
    db = create_client(SUPABASE_URL, service_key) if SUPABASE_URL and service_key else supabase

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        address = request.form.get("address", "").strip()

        # 세션에 기본 배송지 저장
        session["default_address"] = address

        if db and user_id:
            try:
                db.table("profiles").update({
                    "full_name": full_name,
                    "phone": phone,
                }).eq("id", user_id).execute()
            except Exception as exc:
                print(f"[Supabase] 프로필 수정 실패: {exc}")

        return redirect(url_for("main.mypage", message="profile_updated"))

    # GET 요청: 프로필 조회
    can_change_password = False
    if db and user_id:
        try:
            res = db.table("profiles").select("*").eq("id", user_id).maybe_single().execute()
            if res and res.data:
                profile = res.data
        except Exception as exc:
            print(f"[Supabase] 프로필 조회 실패: {exc}")

        # 이메일/비밀번호 인증 가입자인지 판별 (소셜 로그인 사용자는 비밀번호 변경 섹션 숨김)
        try:
            u_info = db.auth.admin.get_user_by_id(user_id)
            if u_info and u_info.user:
                providers = (u_info.user.app_metadata or {}).get("providers", [])
                # providers 목록에 'email'이 포함되어 있으면 비밀번호 변경 가능
                can_change_password = "email" in providers
        except Exception as exc:
            print(f"[Supabase] 사용자 인증 제공자 조회 실패: {exc}")

    # 기본값 설정
    if not profile:
        profile = {
            "email": session.get("email", ""),
            "full_name": session.get("email", "").split("@")[0] if "@" in session.get("email", "") else "회원",
            "phone": "",
            "grade": "BRONZE",
        }

    return render_template(
        "mypage.html",
        profile=profile,
        email=profile.get("email") or session.get("email"),
        default_address=default_address,
        can_change_password=can_change_password,
        **get_messages()
    )


@main_bp.route("/mypage/change-password", methods=["POST"])
@login_required
def change_password():
    """
    POST /mypage/change-password
    마이페이지 비밀번호 변경 처리:
    1. 필수 입력값 검증 (current_password, new_password, new_password_confirm)
    2. 새 비밀번호 검증 (최소 길이 6자, 확인 일치, 현재 비밀번호와 동일 여부)
    3. 기존 비밀번호 검증 (Supabase sign_in_with_password 시도)
    4. Supabase admin.update_user_by_id()로 비밀번호 갱신
    """
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    new_password_confirm = request.form.get("new_password_confirm", "")

    # 1. 필수 입력값 검증
    if not current_password or not new_password or not new_password_confirm:
        return redirect(url_for("main.mypage", error="missing_fields"))

    # 2. 새 비밀번호 확인 일치 검증
    if new_password != new_password_confirm:
        return redirect(url_for("main.mypage", error="password_mismatch"))

    # 3. 새 비밀번호 최소 길이 검증 (6자 이상)
    if len(new_password) < 6:
        return redirect(url_for("main.mypage", error="weak_password"))

    # 4. 기존 비밀번호와 동일 여부 검증
    if new_password == current_password:
        return redirect(url_for("main.mypage", error="same_password"))

    user_id = session.get("user_id")
    email = session.get("email")

    service_key = os.getenv("SUPABASE_SERVICE_KEY") or SUPABASE_ANON_KEY
    db = create_client(SUPABASE_URL, service_key) if SUPABASE_URL and service_key else supabase

    if not db or not user_id:
        return redirect(url_for("main.mypage", error="server_error"))

    # 사용자의 실제 이메일 조회
    try:
        u_info = db.auth.admin.get_user_by_id(user_id)
        if u_info and u_info.user and u_info.user.email:
            email = u_info.user.email
    except Exception as exc:
        print(f"[Supabase] 이메일 확인 실패: {exc}")

    if not email:
        return redirect(url_for("main.mypage", error="server_error"))

    # 5. 기존 비밀번호 검증 (anon 클라이언트로 sign_in_with_password 시도)
    anon_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    try:
        anon_client.auth.sign_in_with_password({
            "email": email,
            "password": current_password,
        })
    except Exception as exc:
        print(f"[Supabase] 현재 비밀번호 검증 실패: {exc}")
        return redirect(url_for("main.mypage", error="current_password_mismatch"))

    # 6. Supabase update_user_by_id()로 비밀번호 갱신
    try:
        db.auth.admin.update_user_by_id(user_id, {"password": new_password})
    except Exception as exc:
        print(f"[Supabase] 비밀번호 갱신 실패: {exc}")
        return redirect(url_for("main.mypage", error="server_error"))

    return redirect(url_for("main.mypage", message="password_updated"))

@main_bp.route("/products/<product_id>/options")
@main_bp.route("/product/<product_id>/options")
def product_color_options(product_id):
    """
    선택된 색상(color)에 따른 사이즈 및 재고 목록을 비동기 JSON으로 반환하는 API
    - 같은 색상이라도 사이즈별(S/M/L) 재고(stock)가 다름
    - stock이 0이면 is_sold_out=True 처리
    """
    color = request.args.get("color", "").strip()
    if not color:
        return jsonify([])

    sizes = []
    if supabase is not None:
        try:
            res = (
                supabase.table("product_options")
                .select("id, size, stock, additional_price")
                .eq("product_id", product_id)
                .eq("color", color)
                .execute()
            )
            # 사이즈 표시 순서 정렬 (S -> M -> L -> XL)
            size_priority = {"S": 1, "M": 2, "L": 3, "XL": 4, "FREE": 5}
            raw_data = res.data or []
            raw_data.sort(key=lambda x: size_priority.get(x.get("size"), 99))

            for row in raw_data:
                stock_val = row.get("stock", 0) if row.get("stock") is not None else 0
                sizes.append({
                    "id": row.get("id"),
                    "size": row.get("size"),
                    "stock": stock_val,
                    "is_sold_out": stock_val <= 0,
                    "additional_price": row.get("additional_price", 0),
                })
        except Exception as exc:
            print(f"[Supabase] 색상별 사이즈 옵션 조회 실패: {exc}")

    return jsonify(sizes)


@main_bp.route("/products/<product_id>")
@main_bp.route("/product/<product_id>")
def product_detail(product_id):
    """
    상품 상세 페이지:
    1. Supabase에서 product_id로 상품 정보(이름, 가격, 설명, 이미지) 조회
    2. product_options 테이블에서 해당 상품의 색상(color) 목록을 DISTINCT로 조회
    """
    product = None

    if supabase is not None:
        try:
            response = (
                supabase.table("products")
                .select("*, categories(name)")
                .eq("id", product_id)
                .eq("is_active", True)
                .maybe_single()
                .execute()
            )
            product = response.data if response else None
        except Exception as exc:
            print(f"[Supabase] 상품 상세 조회 실패: {exc}")
            product = None

    # Supabase 연결 실패 시 메인에 보이는 샘플 상품은 상세도 보여줌
    if product is None:
        product = next((dict(p) for p in FEATURED_FALLBACK if p["id"] == product_id), None)

    # 일치하는 상품이 없으면 404 에러 반환
    if product is None:
        abort(404)

    _prepare_product(product)
    product["category"] = (product.get("categories") or {}).get("name") or "이달의 상품"
    product["formatted_original_price"] = _format_price(product.get("price"))

    # 할인가격 존재 여부 및 포맷팅
    if product.get("discount_price") and product.get("discount_price") < product.get("price", 0):
        product["formatted_discount_price"] = _format_price(product.get("discount_price"))
        product["has_discount"] = True
    else:
        product["has_discount"] = False

    # 해당 상품의 고유 색상 목록(DISTINCT) 조회
    colors = []
    if supabase is not None:
        try:
            opt_res = (
                supabase.table("product_options")
                .select("color")
                .eq("product_id", product_id)
                .not_.is_("color", "null")
                .execute()
            )
            # 중복 제거 (DISTINCT) 및 정렬
            colors = sorted(list({row["color"] for row in (opt_res.data or []) if row.get("color")}))
        except Exception as exc:
            print(f"[Supabase] 옵션 색상 목록 조회 실패: {exc}")

    return render_template("product_detail.html", product=product, colors=colors)

