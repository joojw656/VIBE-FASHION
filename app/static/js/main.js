/**
 * VIBE-FASHION 프론트엔드 인터랙션 스크립트
 */

// 장바구니 담긴 개수 카운터
let cartCount = 0;

/**
 * 토스트 알림을 띄우는 함수
 * @param {string} message - 토스트에 표시할 안내 메시지
 */
function showToast(message) {
    const toastElement = document.getElementById('actionToast');
    const toastMessage = document.getElementById('toastMessage');

    if (toastElement && toastMessage) {
        toastMessage.textContent = message;
        const toast = new bootstrap.Toast(toastElement, { delay: 2500 });
        toast.show();
    }
}

/**
 * 장바구니 담기 버튼 클릭 시 호출되는 함수
 * @param {string} productName - 담은 상품명
 */
function addToCart(productName) {
    cartCount += 1;

    // 네비게이션 바의 장바구니 배지 숫자 갱신
    const cartBadge = document.getElementById('cart-badge');
    if (cartBadge) {
        cartBadge.textContent = cartCount;
    }

    // 사용자 알림 토스트 출력
    showToast(`'${productName}' 상품을 장바구니에 담았습니다!`);
}
