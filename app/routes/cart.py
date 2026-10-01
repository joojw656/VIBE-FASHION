import os
from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from supabase import create_client

from app.routes.auth import SUPABASE_ANON_KEY, SUPABASE_URL
from app.routes.main import FEATURED_FALLBACK, PRODUCT_IMAGE_OVERRIDES, _format_price, _prepare_product

cart_bp = Blueprint("cart", __name__, url_prefix="/cart")

SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")


def _get_db_client():
    """장바구니 쿼리용 Supabase 클라이언트 반환 (서비스 키 우선 사용)"""
    key = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY
    if not SUPABASE_URL or not key:
        return None
    try:
        return create_client(SUPABASE_URL, key)
    except Exception as exc:
        print(f"[Supabase] 장바구니 클라이언트 생성 실패: {exc}")
        return None


def get_session_cart():
    """비로그인 또는 폴백용 세션 기반 장바구니 목록 반환"""
    return session.get("cart", {})


def save_session_cart(cart):
    """세션 장바구니 저장"""
    session["cart"] = cart
    session.modified = True


def get_cart_count():
    """현재 사용자의 장바구니 총 담긴 수량 반환"""
    user_id = session.get("user_id")
    if user_id:
        db = _get_db_client()
        if db:
            try:
                res = db.table("carts").select("quantity").eq("user_id", user_id).execute()
                return sum(item.get("quantity", 1) for item in (res.data or []))
            except Exception as exc:
                print(f"[Supabase] 장바구니 수량 조회 실패: {exc}")
    # 비로그인 세션 카트
    cart = get_session_cart()
    return sum(item.get("quantity", 1) for item in cart.values())


def _find_product_info(product_id):
    """상품 ID로 상세 정보 조회 (DB 또는 폴백)"""
    db = _get_db_client()
    product = None
    if db:
        try:
            res = (
                db.table("products")
                .select("id, name, price, discount_price, thumbnail_url")
                .eq("id", product_id)
                .maybe_single()
                .execute()
            )
            product = res.data if res else None
        except Exception as exc:
            print(f"[Supabase] 장바구니 상품 정보 조회 실패: {exc}")

    if not product:
        product = next((dict(p) for p in FEATURED_FALLBACK if p["id"] == str(product_id)), None)

    if product:
        _prepare_product(product)
    return product


@cart_bp.route("/")
def view_cart():
    """
    [장바구니 페이지] GET /cart
    - carts + product_options + products JOIN 조회
    - 각 아이템: 상품명, 색상, 사이즈, 수량, 단가, 소계
    - 품절(stock=0) 아이템: "품절됨" 배지 + 수량 변경 버튼 비활성화
    - 전체 합계 + 배송비 (50,000원 미만 3,000원, 이상 무료)
    """
    user_id = session.get("user_id")
    items = []
    total_amount = 0
    has_sold_out_item = False

    if user_id:
        db = _get_db_client()
        if db:
            try:
                res = (
                    db.table("carts")
                    .select("id, product_id, option_id, quantity, products(id, name, price, discount_price, thumbnail_url), product_options(id, color, size, stock, stock_quantity)")
                    .eq("user_id", user_id)
                    .order("created_at", desc=False)
                    .execute()
                )
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

                        # 옵션 정보 및 재고 상태 확인
                        opt_info = row.get("product_options") or {}
                        stock = opt_info.get("stock")
                        if stock is None:
                            stock = opt_info.get("stock_quantity", 0)
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
                print(f"[Supabase] DB 장바구니 조회 실패: {exc}")

    # 비로그인이거나 DB 조회 결과가 없는 경우 세션 카트 확인
    if not items:
        session_cart = get_session_cart()
        for pid, data in session_cart.items():
            prod = _find_product_info(pid)
            if prod:
                unit_price = prod.get("discount_price") or prod.get("price") or 0
                qty = data.get("quantity", 1)
                subtotal = unit_price * qty
                total_amount += subtotal
                items.append({
                    "cart_id": None,
                    "product_id": pid,
                    "product": prod,
                    "quantity": qty,
                    "unit_price": unit_price,
                    "formatted_unit_price": _format_price(unit_price),
                    "subtotal": subtotal,
                    "formatted_subtotal": _format_price(subtotal),
                    "is_sold_out": False,
                    "stock": 999,
                })

    # 배송비 계산 (50,000원 미만 3,000원, 이상 무료)
    shipping_cost = 0 if total_amount >= 50000 else 3000
    final_total = total_amount + shipping_cost

    return render_template(
        "cart.html",
        items=items,
        total_amount=total_amount,
        formatted_total_amount=_format_price(total_amount),
        shipping_cost=shipping_cost,
        formatted_shipping_cost=_format_price(shipping_cost),
        final_total=final_total,
        formatted_final_total=_format_price(final_total),
        item_count=sum(i["quantity"] for i in items),
        has_sold_out_item=has_sold_out_item,
    )


@cart_bp.route("/add", methods=["POST"])
def add_to_cart():
    """
    [장바구니 담기] POST /cart/add
    - 요청: product_option_id (또는 option_id), quantity (JSON 또는 Form 데이터)
    - 로그인 필수: 비로그인 시 /auth/login 으로 리다이렉트 (JSON 요청 시 401 및 redirect_url 반환)
    - product_options.stock 조회 후 요청 수량보다 적으면 에러 반환 (DB 미작성)
    - carts 테이블에 upsert (같은 옵션이면 수량 누적)
    - 누적 후 수량이 재고를 초과하게 되는 경우도 에러 처리
    - 성공 시 JSON: {"success": true, "message": "장바구니에 담겼습니다"}
    """
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json

    # 1. 로그인 여부 확인
    user_id = session.get("user_id")
    if not user_id:
        if is_ajax:
            return jsonify({
                "success": False,
                "error": "login_required",
                "message": "로그인이 필요한 서비스입니다.",
                "redirect_url": url_for("auth.login", error="login_required", next=request.referrer or url_for("cart.view_cart")),
            }), 401
        return redirect(url_for("auth.login", error="login_required", next=request.referrer or url_for("cart.view_cart")))

    # 요청 파라미터 추출 (JSON 또는 Form 모두 지원)
    req_data = request.get_json(silent=True) or request.form
    product_option_id = req_data.get("product_option_id") or req_data.get("option_id")
    product_id = req_data.get("product_id")

    try:
        quantity = int(req_data.get("quantity", 1))
    except (ValueError, TypeError):
        quantity = 1

    if quantity <= 0:
        if is_ajax:
            return jsonify({"success": False, "message": "수량은 1개 이상이어야 합니다."}), 400
        return redirect(request.referrer or url_for("cart.view_cart"))

    db = _get_db_client()
    if not db:
        if is_ajax:
            return jsonify({"success": False, "message": "데이터베이스 연결에 실패했습니다."}), 500
        return redirect(url_for("cart.view_cart"))

    # 2. product_options 정보 및 재고(stock) 확인
    stock = 0
    resolved_product_id = product_id

    if product_option_id:
        try:
            opt_res = (
                db.table("product_options")
                .select("id, product_id, stock, stock_quantity")
                .eq("id", product_option_id)
                .maybe_single()
                .execute()
            )
            if opt_res and opt_res.data:
                resolved_product_id = opt_res.data.get("product_id") or product_id
                # stock 컬럼 우선 사용, 없으면 stock_quantity 사용
                stock = opt_res.data.get("stock")
                if stock is None:
                    stock = opt_res.data.get("stock_quantity", 0)
            else:
                if is_ajax:
                    return jsonify({"success": False, "message": "존재하지 않는 상품 옵션입니다."}), 404
                return redirect(request.referrer or url_for("cart.view_cart"))
        except Exception as exc:
            print(f"[Supabase] 옵션 재고 조회 실패: {exc}")
            if is_ajax:
                return jsonify({"success": False, "message": "옵션 정보를 확인하는 중 오류가 발생했습니다."}), 500
            return redirect(request.referrer or url_for("cart.view_cart"))
    elif product_id:
        # 옵션 ID 없이 상품 ID만 넘어온 경우 상품 자체 재고 확인
        try:
            prod_res = db.table("products").select("stock_quantity").eq("id", product_id).maybe_single().execute()
            stock = (prod_res.data or {}).get("stock_quantity", 0)
        except Exception as exc:
            print(f"[Supabase] 상품 재고 조회 실패: {exc}")
            stock = 0

    # 요청 수량이 현재 재고보다 많은 경우 에러 반환 (DB에 아무것도 쓰지 않음)
    if stock < quantity:
        msg = f"재고가 부족합니다 (현재 {stock}개)"
        if is_ajax:
            return jsonify({"success": False, "message": msg, "stock": stock}), 400
        flash(msg, "danger")
        return redirect(request.referrer or url_for("cart.view_cart"))

    # 3. 기존 장바구니에 담긴 수량 확인 (누적 검증)
    existing_qty = 0
    existing_cart_id = None
    try:
        query = db.table("carts").select("id, quantity").eq("user_id", user_id).eq("product_id", resolved_product_id)
        if product_option_id:
            query = query.eq("option_id", product_option_id)
        else:
            query = query.is_("option_id", "null")
        existing_res = query.maybe_single().execute()

        if existing_res and existing_res.data:
            existing_cart_id = existing_res.data["id"]
            existing_qty = existing_res.data.get("quantity", 0)
    except Exception as exc:
        print(f"[Supabase] 기존 장바구니 조회 실패: {exc}")

    # 4. 누적 후 수량이 재고를 초과하는지 검증
    new_quantity = existing_qty + quantity
    if new_quantity > stock:
        msg = f"장바구니에 담긴 수량({existing_qty}개)을 포함하여 재고를 초과합니다 (현재 {stock}개)"
        if is_ajax:
            return jsonify({"success": False, "message": msg, "stock": stock}), 400
        flash(msg, "danger")
        return redirect(request.referrer or url_for("cart.view_cart"))

    # 5. carts 테이블에 저장 (upsert / update or insert)
    try:
        if existing_cart_id:
            db.table("carts").update({"quantity": new_quantity}).eq("id", existing_cart_id).execute()
        else:
            cart_payload = {
                "user_id": user_id,
                "product_id": resolved_product_id,
                "quantity": quantity,
            }
            if product_option_id:
                cart_payload["option_id"] = product_option_id
            db.table("carts").insert(cart_payload).execute()
    except Exception as exc:
        print(f"[Supabase] 장바구니 저장 실패: {exc}")
        if is_ajax:
            return jsonify({"success": False, "message": "장바구니에 저장하는 중 오류가 발생했습니다."}), 500
        return redirect(request.referrer or url_for("cart.view_cart"))

    # 6. 성공 응답
    if is_ajax:
        return jsonify({
            "success": True,
            "message": "장바구니에 담겼습니다",
            "cart_count": get_cart_count(),
        })

    return redirect(url_for("cart.view_cart"))


@cart_bp.route("/<cart_id>", methods=["PATCH"])
def update_cart_quantity(cart_id):
    """
    [장바구니 수량 변경] PATCH /cart/<cart_id>
    - 요청 body: quantity (JSON 또는 Form)
    - 본인 소유의 장바구니 아이템인지 확인 (다른 사용자 차단)
    - quantity < 1 이면 에러 (400)
    - 옵션의 stock을 초과하면 '재고가 부족합니다(현재 N개)' 에러 (400), DB 미변경
    - 성공 시 UPDATE 후 새 소계(subtotal) 및 합계 반환
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    req_data = request.get_json(silent=True) or request.form
    try:
        quantity = int(req_data.get("quantity"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "수량을 정확히 입력해 주세요."}), 400

    # 1. quantity가 1 미만이면 에러
    if quantity < 1:
        return jsonify({"success": False, "message": "수량은 1개 이상이어야 합니다."}), 400

    db = _get_db_client()
    if not db:
        return jsonify({"success": False, "message": "데이터베이스 연결에 실패했습니다."}), 500

    # 2. 본인 소유 장바구니 아이템인지 확인 & 옵션/상품 정보 조회
    try:
        cart_res = (
            db.table("carts")
            .select("id, user_id, product_id, option_id, quantity, products(id, name, price, discount_price), product_options(id, stock, stock_quantity)")
            .eq("id", cart_id)
            .maybe_single()
            .execute()
        )
    except Exception as exc:
        print(f"[Supabase] 장바구니 아이템 조회 실패: {exc}")
        return jsonify({"success": False, "message": "조회 중 오류가 발생했습니다."}), 500

    cart_item = cart_res.data if cart_res else None
    if not cart_item:
        return jsonify({"success": False, "message": "존재하지 않는 장바구니 항목입니다."}), 404

    # 본인 소유 검증 (타인 접근 차단)
    if str(cart_item.get("user_id")) != str(user_id):
        return jsonify({"success": False, "message": "해당 항목을 수정할 권한이 없습니다."}), 403

    # 3. 재고 확인
    stock = 0
    opt_data = cart_item.get("product_options")
    prod_data = cart_item.get("products") or {}

    if opt_data:
        stock = opt_data.get("stock")
        if stock is None:
            stock = opt_data.get("stock_quantity", 0)
    else:
        # 옵션이 없는 상품의 경우 상품 자체 재고 확인
        try:
            p_res = db.table("products").select("stock_quantity").eq("id", cart_item.get("product_id")).maybe_single().execute()
            stock = (p_res.data or {}).get("stock_quantity", 0)
        except Exception:
            stock = 0

    if quantity > stock:
        return jsonify({
            "success": False,
            "message": f"재고가 부족합니다(현재 {stock}개)",
            "stock": stock
        }), 400

    # 4. carts 테이블 UPDATE
    try:
        db.table("carts").update({"quantity": quantity}).eq("id", cart_id).eq("user_id", user_id).execute()
    except Exception as exc:
        print(f"[Supabase] 수량 변경 실패: {exc}")
        return jsonify({"success": False, "message": "수량 변경에 실패했습니다."}), 500

    # 5. 새 소계(subtotal) 계산
    unit_price = prod_data.get("discount_price") or prod_data.get("price") or 0
    if not unit_price:
        p_info = _find_product_info(cart_item.get("product_id"))
        if p_info:
            unit_price = p_info.get("discount_price") or p_info.get("price") or 0

    subtotal = unit_price * quantity

    # 전체 총 금액 재계산
    total_amount = 0
    try:
        all_items = (
            db.table("carts")
            .select("quantity, products(price, discount_price)")
            .eq("user_id", user_id)
            .execute()
        )
        for row in (all_items.data or []):
            p = row.get("products") or {}
            u = p.get("discount_price") or p.get("price") or 0
            total_amount += u * row.get("quantity", 1)
    except Exception as exc:
        print(f"[Supabase] 총액 계산 실패: {exc}")

    return jsonify({
        "success": True,
        "message": "수량이 변경되었습니다.",
        "quantity": quantity,
        "subtotal": subtotal,
        "formatted_subtotal": _format_price(subtotal),
        "total_amount": total_amount,
        "formatted_total_amount": _format_price(total_amount),
        "cart_count": get_cart_count(),
    })


@cart_bp.route("/<cart_id>", methods=["DELETE"])
def delete_cart_item(cart_id):
    """
    [장바구니 아이템 삭제] DELETE /cart/<cart_id>
    - 본인 소유의 장바구니 아이템인지 확인 후 삭제
    - 성공 시 삭제 완료 메시지, 남은 총액 및 장바구니 품목 수 반환
    """
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"success": False, "message": "로그인이 필요합니다."}), 401

    db = _get_db_client()
    if not db:
        return jsonify({"success": False, "message": "데이터베이스 연결에 실패했습니다."}), 500

    # 1. 본인 소유 장바구니 아이템인지 확인
    try:
        cart_res = db.table("carts").select("id, user_id").eq("id", cart_id).maybe_single().execute()
    except Exception as exc:
        print(f"[Supabase] 장바구니 항목 확인 실패: {exc}")
        return jsonify({"success": False, "message": "확인 중 오류가 발생했습니다."}), 500

    cart_item = cart_res.data if cart_res else None
    if not cart_item:
        return jsonify({"success": False, "message": "존재하지 않는 장바구니 항목입니다."}), 404

    if str(cart_item.get("user_id")) != str(user_id):
        return jsonify({"success": False, "message": "해당 항목을 삭제할 권한이 없습니다."}), 403

    # 2. DELETE 수행
    try:
        db.table("carts").delete().eq("id", cart_id).eq("user_id", user_id).execute()
    except Exception as exc:
        print(f"[Supabase] 장바구니 항목 삭제 실패: {exc}")
        return jsonify({"success": False, "message": "삭제에 실패했습니다."}), 500

    # 3. 삭제 후 남은 총액 및 수량 계산
    total_amount = 0
    remaining_items_count = 0
    total_quantity = 0
    try:
        all_items = (
            db.table("carts")
            .select("quantity, products(price, discount_price)")
            .eq("user_id", user_id)
            .execute()
        )
        data = all_items.data or []
        remaining_items_count = len(data)
        for row in data:
            p = row.get("products") or {}
            u = p.get("discount_price") or p.get("price") or 0
            qty = row.get("quantity", 1)
            total_amount += u * qty
            total_quantity += qty
    except Exception as exc:
        print(f"[Supabase] 총액 재계산 실패: {exc}")

    return jsonify({
        "success": True,
        "message": "장바구니에서 삭제되었습니다.",
        "remaining_count": remaining_items_count,
        "total_quantity": total_quantity,
        "total_amount": total_amount,
        "formatted_total_amount": _format_price(total_amount),
        "cart_count": total_quantity,
    })


@cart_bp.route("/update", methods=["POST"])
def update_cart():
    """수량 변경 (+1 / -1 / 직접 수정)"""
    product_id = request.form.get("product_id")
    quantity = int(request.form.get("quantity", 1))
    user_id = session.get("user_id")

    if not product_id:
        return redirect(url_for("cart.view_cart"))

    if user_id:
        db = _get_db_client()
        if db:
            try:
                if quantity <= 0:
                    db.table("carts").delete().eq("user_id", user_id).eq("product_id", product_id).execute()
                else:
                    db.table("carts").update({"quantity": quantity}).eq("user_id", user_id).eq("product_id", product_id).execute()
            except Exception as exc:
                print(f"[Supabase] DB 장바구니 수량 변경 실패: {exc}")
    else:
        cart = get_session_cart()
        if quantity <= 0:
            cart.pop(product_id, None)
        else:
            if product_id in cart:
                cart[product_id]["quantity"] = quantity
        save_session_cart(cart)

    return redirect(url_for("cart.view_cart"))


@cart_bp.route("/remove", methods=["POST"])
def remove_from_cart():
    """장바구니 항목 개별 삭제"""
    product_id = request.form.get("product_id")
    user_id = session.get("user_id")

    if not product_id:
        return redirect(url_for("cart.view_cart"))

    if user_id:
        db = _get_db_client()
        if db:
            try:
                db.table("carts").delete().eq("user_id", user_id).eq("product_id", product_id).execute()
            except Exception as exc:
                print(f"[Supabase] DB 장바구니 삭제 실패: {exc}")
    else:
        cart = get_session_cart()
        cart.pop(product_id, None)
        save_session_cart(cart)

    return redirect(url_for("cart.view_cart"))


@cart_bp.route("/clear", methods=["POST"])
def clear_cart():
    """장바구니 전체 비우기"""
    user_id = session.get("user_id")
    if user_id:
        db = _get_db_client()
        if db:
            try:
                db.table("carts").delete().eq("user_id", user_id).execute()
            except Exception as exc:
                print(f"[Supabase] DB 장바구니 전체 삭제 실패: {exc}")
    else:
        save_session_cart({})

    return redirect(url_for("cart.view_cart"))
