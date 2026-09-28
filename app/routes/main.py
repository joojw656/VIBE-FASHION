import os
from flask import Blueprint, render_template, abort
from dotenv import load_dotenv
from supabase import create_client

# .env 파일에서 SUPABASE_URL, SUPABASE_ANON_KEY 등의 환경 변수를 로드합니다.
load_dotenv()

# 'main' 블루프린트 생성
# 블루프린트를 사용하면 라우트(URL 핸들러)를 기능별 파일로 분리하여 관리할 수 있습니다.
main_bp = Blueprint("main", __name__)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")

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


def get_featured_products(limit=4):
    """
    is_active=true 이고 is_featured=true 인 상품을 최대 limit개 조회합니다.
    Supabase 연결/조회 실패 시에도 앱이 죽지 않도록 빈 리스트를 반환합니다.
    """
    if supabase is None:
        print("[Supabase] 클라이언트가 초기화되지 않아 빈 상품 목록을 반환합니다.")
        return []

    try:
        response = (
            supabase.table("products")
            .select("id, name, price, discount_price, thumbnail_url")
            .eq("is_active", True)
            .eq("is_featured", True)
            .limit(limit)
            .execute()
        )
        products = response.data or []
    except Exception as exc:
        print(f"[Supabase] products 조회 실패: {exc}")
        return []

    for product in products:
        display_price = product.get("discount_price") or product.get("price")
        product["formatted_price"] = _format_price(display_price)

    return products


def get_new_arrivals(limit=4):
    """
    is_active=true 인 상품 중 최근 등록순(created_at desc)으로 최대 limit개를 조회합니다.
    Supabase 연결/조회 실패 시에도 앱이 죽지 않도록 빈 리스트를 반환합니다.
    """
    if supabase is None:
        print("[Supabase] 클라이언트가 초기화되지 않아 빈 신상품 목록을 반환합니다.")
        return []

    try:
        response = (
            supabase.table("products")
            .select("id, name, price, discount_price, thumbnail_url")
            .eq("is_active", True)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        products = response.data or []
    except Exception as exc:
        print(f"[Supabase] 신상품 조회 실패: {exc}")
        return []

    for product in products:
        display_price = product.get("discount_price") or product.get("price")
        product["formatted_price"] = _format_price(display_price)

    return products

@main_bp.route("/")
def index():
    """
    메인 페이지:
    히어로 배너, Supabase에서 조회한 '이달의 상품'과 '신상품' 목록을 화면에 렌더링합니다.
    """
    products = get_featured_products(limit=4)
    new_arrivals = get_new_arrivals(limit=4)
    return render_template("index.html", products=products, new_arrivals=new_arrivals)

@main_bp.route("/product/<product_id>")
def product_detail(product_id):
    """
    상품 상세 페이지:
    전달받은 product_id(uuid)에 해당하는 상품을 Supabase에서 조회해 렌더링합니다.
    """
    product = None

    if supabase is not None:
        try:
            response = (
                supabase.table("products")
                .select("*")
                .eq("id", product_id)
                .maybe_single()
                .execute()
            )
            product = response.data if response else None
        except Exception as exc:
            print(f"[Supabase] 상품 상세 조회 실패: {exc}")
            product = None

    # 일치하는 상품이 없으면 404 에러 반환
    if product is None:
        abort(404)

    product["formatted_price"] = _format_price(product.get("discount_price") or product.get("price"))
    return render_template("product_detail.html", product=product)

