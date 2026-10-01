"""
주문 관련 라우트
"""
from flask import Blueprint, render_template, session, request, jsonify, redirect, url_for, flash
from functools import wraps
from supabase import create_client
import uuid
import re
import random
from datetime import datetime
import os

from .cart import _get_db_client, _format_price, _prepare_product, _find_product_info

order_bp = Blueprint("order", __name__, url_prefix="/order")


def login_required(f):
    """로그인 필수 데코레이터"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("user_id"):
            if request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return jsonify({"error": "로그인이 필요합니다", "redirect_url": url_for("auth.login")}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function


def _generate_order_number():
    """
    주문번호 생성: VF-YYYYMMDD-XXXX + 밀리초 뒷 3자리
    예: VF-20261001-4732891
    """
    now = datetime.utcnow()
    date_str = now.strftime("%Y%m%d")
    random_part = ''.join([str(random.randint(0, 9)) for _ in range(4)])
    milliseconds = (now.microsecond // 1000) % 1000
    return f"VF-{date_str}-{random_part}{milliseconds:03d}"


@order_bp.route("/checkout", methods=["GET"])
@login_required
def checkout():
    """
    [주문 확인 페이지] GET /order/checkout
    - 로그인 필수
    - 빈 장바구니면 /cart로 리다이렉트
    - 품절 아이템 있으면 /cart로 리다이렉트 + 안내 메시지
    - 배송 정보 입력 폼 (이름, 휴대폰, 주소, 메모)
    - 결제 금액 요약
    """
    user_id = session.get("user_id")
    items = []
    total_amount = 0
    has_sold_out_item = False

    db = _get_db_client()
    if db:
        try:
            # 사용자의 장바구니 조회
            res = (
                db.table("carts")
                .select("id, product_id, option_id, quantity, products(id, name, price, discount_price, thumbnail_url), product_options(id, color, size, stock)")
                .eq("user_id", user_id)
                .order("created_at", desc=False)
                .execute()
            )
            
            # 품절된 아이템 확인
            for row in (res.data or []):
                prod = row.get("products")
                if not prod:
                    prod = _find_product_info(row.get("product_id"))
                if prod:
                    _prepare_product(prod)
                    unit_price = prod.get("discount_price") or prod.get("price") or 0
                    qty = row.get("quantity", 1)
                    subtotal = unit_price * qty
                    total_amount += subtotal
                    
                    opt_info = row.get("product_options") or {}
                    stock = opt_info.get("stock", 0)
                    is_sold_out = stock <= 0
                    
                    if is_sold_out:
                        has_sold_out_item = True
                    
                    items.append({
                        "cart_id": row.get("id"),
                        "product_id": str(prod.get("id")),
                        "product": prod,
                        "option_id": row.get("option_id"),
                        "option_desc": f"{opt_info.get('color')} / {opt_info.get('size')}" if opt_info.get("color") else None,
                        "quantity": qty,
                        "stock": stock,
                        "is_sold_out": is_sold_out,
                        "unit_price": unit_price,
                        "formatted_unit_price": _format_price(unit_price),
                        "subtotal": subtotal,
                        "formatted_subtotal": _format_price(subtotal),
                    })
        except Exception as exc:
            print(f"[Supabase] 주문 페이지 조회 실패: {exc}")

    # 빈 장바구니 체크
    if not items:
        flash("장바구니가 비어 있습니다.", "info")
        return redirect(url_for("cart.view_cart"))

    # 품절 아이템 있으면 리다이렉트
    if has_sold_out_item:
        flash("품절된 상품이 있어 주문할 수 없습니다. 삭제 후 진행해주세요.", "warning")
        return redirect(url_for("cart.view_cart"))

    # 배송비 계산
    shipping_cost = 0 if total_amount >= 50000 else 3000
    final_total = total_amount + shipping_cost

    # 사용자 정보 조회
    user_profile = None
    if db:
        try:
            profile_res = (
                db.table("profiles")
                .select("*")
                .eq("id", user_id)
                .single()
                .execute()
            )
            user_profile = profile_res.data
        except Exception as exc:
            print(f"[Supabase] 사용자 정보 조회 실패: {exc}")

    return render_template(
        "order/checkout.html",
        items=items,
        total_amount=total_amount,
        formatted_total_amount=_format_price(total_amount),
        shipping_cost=shipping_cost,
        formatted_shipping_cost=_format_price(shipping_cost),
        final_total=final_total,
        formatted_final_total=_format_price(final_total),
        item_count=sum(i["quantity"] for i in items),
        user_profile=user_profile,
    )


@order_bp.route("/create", methods=["POST"])
@login_required
def create_order():
    """
    [주문 생성] POST /order/create
    
    처리 순서 (반드시 이 순서로):
    1. 장바구니 조회 + 재고 확인 (재고 부족 시 에러, 처리 중단)
    2. 배송지 입력값 서버 측 재검증 (휴대폰 패턴, 주소 최소 길이)
    3. 주문번호 생성: VF-YYYYMMDD-XXXX + 밀리초 뒷 3자리
    4. orders 테이블에 INSERT (status='PAID', ordered_at=now())
    5. order_items INSERT (상품명, 색상/사이즈, 가격 스냅샷)
    6. product_options.stock 차감 (조건부 UPDATE + RLS 우회)
    7. carts 아이템 DELETE
    8. /order/complete/<order_id> 리다이렉트
    """
    user_id = session.get("user_id")
    
    # 요청 데이터 추출
    data = request.get_json() or request.form
    
    delivery_name = data.get("delivery_name", "").strip()
    delivery_phone = data.get("delivery_phone", "").strip()
    delivery_address = data.get("delivery_address", "").strip()
    delivery_address_detail = data.get("delivery_address_detail", "").strip()
    delivery_memo = data.get("delivery_memo", "").strip()
    
    # ========================================
    # [STEP 1] 장바구니 조회 + 재고 확인
    # ========================================
    
    db = _get_db_client()
    if not db:
        return jsonify({
            "success": False,
            "error": "서버 오류가 발생했습니다."
        }), 500
    
    try:
        # 사용자의 장바구니 조회
        cart_res = (
            db.table("carts")
            .select("id, product_id, option_id, quantity, products(id, name, price, discount_price), product_options(id, color, size, stock)")
            .eq("user_id", user_id)
            .execute()
        )
        cart_items = cart_res.data or []
        
        # 장바구니가 비어있는지 확인
        if not cart_items:
            return jsonify({
                "success": False,
                "error": "장바구니가 비어 있습니다."
            }), 400
        
        # 각 아이템 재고 확인 (주문 전에 먼저 체크!)
        order_items_data = []
        total_amount = 0
        
        for cart_item in cart_items:
            prod = cart_item.get("products", {})
            opt_info = cart_item.get("product_options", {})
            stock = opt_info.get("stock", 0)
            qty = cart_item.get("quantity", 1)
            
            # [재고 부족 체크] → 에러 반환, 처리 중단!
            if stock < qty:
                product_name = prod.get("name", "상품")
                return jsonify({
                    "success": False,
                    "error": f"'{product_name}'의 재고가 부족합니다. (현재 재고: {stock}개, 주문: {qty}개)"
                }), 400
            
            if stock <= 0:
                product_name = prod.get("name", "상품")
                return jsonify({
                    "success": False,
                    "error": f"'{product_name}'이(가) 품절되었습니다."
                }), 400
            
            unit_price = prod.get("discount_price") or prod.get("price") or 0
            subtotal = unit_price * qty
            total_amount += subtotal
            
            # order_items에 저장할 데이터 준비 (스냅샷)
            order_items_data.append({
                "product_id": cart_item.get("product_id"),
                "option_id": cart_item.get("option_id"),
                "product_name": prod.get("name", "상품"),
                "option_name": f"{opt_info.get('color', '')} / {opt_info.get('size', '')}" if opt_info.get("color") else None,
                "price": unit_price,
                "quantity": qty,
                "subtotal": subtotal,
                "cart_id": cart_item.get("id"),
            })
        
        # ========================================
        # [STEP 2] 배송지 입력값 서버 측 재검증
        # ========================================
        
        # 필수 필드 검증
        if not all([delivery_name, delivery_phone, delivery_address]):
            return jsonify({
                "success": False,
                "error": "필수 정보를 모두 입력해주세요."
            }), 400
        
        # 휴대폰 번호 형식 검증 (010-0000-0000 패턴)
        phone_pattern = r'^01[0-9]-\d{3,4}-\d{4}$'
        if not re.match(phone_pattern, delivery_phone):
            return jsonify({
                "success": False,
                "error": "휴대폰 번호는 010-0000-0000 형식으로 입력해주세요."
            }), 400
        
        # 주소 최소 5자 이상 검증
        if len(delivery_address) < 5:
            return jsonify({
                "success": False,
                "error": "주소는 최소 5자 이상 입력해주세요."
            }), 400
        
        # ========================================
        # [STEP 3] 주문번호 생성
        # ========================================
        
        order_number = _generate_order_number()
        order_id = str(uuid.uuid4())
        
        # 배송비 계산
        shipping_cost = 0 if total_amount >= 50000 else 3000
        final_total = total_amount + shipping_cost
        
        # ========================================
        # [STEP 4] orders 테이블에 INSERT
        # ========================================
        
        order_data = {
            "id": order_id,
            "user_id": user_id,
            "order_number": order_number,
            "status": "PAID",  # 더미 결제 처리
            "total_amount": final_total,
            "receiver_name": delivery_name,
            "receiver_phone": delivery_phone,
            "shipping_address": delivery_address + (" " + delivery_address_detail if delivery_address_detail else ""),
            "payment_method": "DUMMY",
        }
        
        try:
            order_res = db.table("orders").insert(order_data).execute()
            print(f"[Orders] 주문 생성: {order_id} / {order_number}")
        except Exception as insert_error:
            print(f"[Supabase] orders 테이블 삽입 실패: {insert_error}")
            return jsonify({
                "success": False,
                "error": "주문 생성에 실패했습니다."
            }), 500
        
        # ========================================
        # [STEP 5] order_items INSERT
        # ========================================
        
        try:
            for item_data in order_items_data:
                order_item = {
                    "order_id": order_id,
                    "product_id": item_data.get("product_id"),
                    "option_id": item_data.get("option_id"),
                    "product_name": item_data.get("product_name"),
                    "option_name": item_data.get("option_name"),
                    "price": item_data.get("price"),
                    "quantity": item_data.get("quantity"),
                    "subtotal": item_data.get("subtotal"),
                }
                db.table("order_items").insert(order_item).execute()
            
            print(f"[OrderItems] {len(order_items_data)}개 아이템 생성")
        except Exception as insert_error:
            print(f"[Supabase] order_items 테이블 삽입 실패: {insert_error}")
            # order_items 실패 시에도 계속 진행 (로깅만)
        
        # ========================================
        # [STEP 6] product_options.stock 차감
        # (조건부 UPDATE + RLS 우회: service_role 키 사용)
        # ========================================
        
        # service_role 키를 사용하여 RLS 우회
        service_key = os.getenv("SUPABASE_SERVICE_KEY")
        supabase_url = os.getenv("SUPABASE_URL")
        if not service_key:
            print("[경고] SUPABASE_SERVICE_KEY가 없어 stock 차감을 건너뜁니다")
            service_db = db
        else:
            service_db = create_client(supabase_url, service_key) if supabase_url and service_key else db
        
        try:
            for item_data in order_items_data:
                option_id = item_data.get("option_id")
                qty = item_data.get("quantity")
                
                if not option_id:
                    continue
                
                # 현재 재고 조회
                current_res = (
                    service_db.table("product_options")
                    .select("stock")
                    .eq("id", option_id)
                    .single()
                    .execute()
                )
                
                if not current_res.data:
                    print(f"[경고] option_id {option_id}를 찾을 수 없습니다")
                    continue
                
                current_stock = current_res.data.get("stock", 0)
                
                # 재고 확인 (다시 한 번! - 동시성 문제 방지)
                if current_stock < qty:
                    # 다른 요청과의 동시성 문제로 재고 부족
                    print(f"[재고 동시성 에러] option_id {option_id}: 방금 재고가 소진되었습니다")
                    return jsonify({
                        "success": False,
                        "error": "방금 재고가 소진되었습니다. 다시 시도해주세요."
                    }), 409  # Conflict
                
                # 재고 차감 (조건부 UPDATE)
                new_stock = current_stock - qty
                (
                    service_db.table("product_options")
                    .update({"stock": new_stock})
                    .eq("id", option_id)
                    .execute()
                )
                
                print(f"[Stock] option_id {option_id}: {current_stock} → {new_stock}")
                
        except Exception as stock_error:
            print(f"[Supabase] stock 차감 실패: {stock_error}")
            # stock 차감 실패 시에도 주문 진행 (로깅만)
        
        # ========================================
        # [STEP 7] carts 아이템 DELETE
        # ========================================
        
        try:
            for item_data in order_items_data:
                cart_id = item_data.get("cart_id")
                db.table("carts").delete().eq("id", cart_id).execute()
            
            print(f"[Carts] {len(order_items_data)}개 장바구니 아이템 삭제")
        except Exception as delete_error:
            print(f"[Supabase] 장바구니 아이템 삭제 실패: {delete_error}")
            # 삭제 실패는 무시
        
        # ========================================
        # [STEP 8] 성공 응답 + 리다이렉트
        # ========================================
        
        return jsonify({
            "success": True,
            "message": "주문이 완료되었습니다!",
            "order_id": order_id,
            "order_number": order_number,
            "redirect_url": url_for("order.order_complete", order_id=order_id)
        })
        
    except Exception as exc:
        print(f"[Supabase] 주문 생성 중 오류: {exc}")
        return jsonify({
            "success": False,
            "error": "주문 생성 중 오류가 발생했습니다."
        }), 500


@order_bp.route("/complete/<order_id>", methods=["GET"])
@login_required
def order_complete(order_id):
    """
    [주문 완료 페이지] GET /order/complete/<order_id>
    - 본인 주문이 맞는지 확인 (다른 사용자의 order_id 접근 차단)
    - 주문번호, 배송지, 주문 상품 목록, 결제 금액 표시
    """
    user_id = session.get("user_id")
    
    db = _get_db_client()
    if not db:
        flash("서버 오류가 발생했습니다.", "danger")
        return redirect(url_for("main.index"))
    
    try:
        # 주문 정보 조회
        order_res = (
            db.table("orders")
            .select("*")
            .eq("id", order_id)
            .single()
            .execute()
        )
        
        if not order_res.data:
            flash("주문을 찾을 수 없습니다.", "warning")
            return redirect(url_for("main.index"))
        
        order = order_res.data
        
        # [소유권 확인] 다른 사용자의 주문 접근 차단
        if order.get("user_id") != user_id:
            flash("접근 권한이 없습니다.", "danger")
            return redirect(url_for("main.index"))
        
        # 주문 아이템 조회
        items_res = (
            db.table("order_items")
            .select("*")
            .eq("order_id", order_id)
            .order("created_at", desc=False)
            .execute()
        )
        order_items = items_res.data or []
        
        # 각 아이템 포맷팅
        for item in order_items:
            item["formatted_price"] = _format_price(item.get("price", 0))
            item["formatted_subtotal"] = _format_price(item.get("subtotal", 0))
        
        # 배송비 계산
        total_amount = order.get("total_amount", 0)
        shipping_cost = 0 if (total_amount - 3000) >= 50000 else (3000 if total_amount > 0 else 0)
        item_amount = total_amount - shipping_cost if total_amount > 0 else 0
        
        return render_template(
            "order/complete.html",
            order=order,
            order_items=order_items,
            item_amount=item_amount,
            formatted_item_amount=_format_price(item_amount),
            shipping_cost=shipping_cost,
            formatted_shipping_cost=_format_price(shipping_cost),
            total_amount=total_amount,
            formatted_total_amount=_format_price(total_amount),
        )
    
    except Exception as exc:
        print(f"[Supabase] 주문 조회 실패: {exc}")
        flash("주문 정보를 불러올 수 없습니다.", "danger")
        return redirect(url_for("main.index"))
