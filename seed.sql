-- =====================================================================
-- VIBE-FASHION 초기 데이터 (Seed)
-- schema.sql 실행 후 Supabase SQL Editor에서 실행하세요.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 1. 카테고리 7개
-- ---------------------------------------------------------------------
insert into public.categories (name, slug, sort_order)
values
    ('상의', 'top', 1),
    ('하의', 'bottom', 2),
    ('아우터', 'outer', 3),
    ('원피스/세트', 'dress', 4),
    ('액세서리', 'acc', 5),
    ('가방', 'bag', 6),
    ('신발', 'shoes', 7)
on conflict (slug) do nothing;

-- ---------------------------------------------------------------------
-- 2. 샘플 상품 4개
--    * 베이직 크롭 티셔츠는 정가 29,900원에서 19,900원으로 할인 판매
-- ---------------------------------------------------------------------
insert into public.products (id, category_id, name, description, price, discount_price, thumbnail_url, status, stock_quantity, is_active, is_featured)
values
    (
        '11111111-1111-1111-1111-111111111111',
        (select id from public.categories where slug = 'top'),
        '베이직 크롭 티셔츠',
        '데일리로 매치하기 좋은 편안한 핏의 크롭 기장 티셔츠입니다.',
        22000,
        15900,
        '/static/images/basic-crop-tee.jpg',
        'ON_SALE',
        100,
        true,
        true
    ),
    (
        '22222222-2222-2222-2222-222222222222',
        (select id from public.categories where slug = 'bottom'),
        '와이드 데님 팬츠',
        '여유로운 실루엣의 와이드 핏 데님 팬츠입니다.',
        32000,
        25900,
        'https://images.unsplash.com/photo-1541099649105-f69ad21f3246?w=800&q=80',
        'ON_SALE',
        80,
        true,
        true
    ),
    (
        '33333333-3333-3333-3333-333333333333',
        (select id from public.categories where slug = 'outer'),
        '오버핏 코튼 자켓',
        '가볍게 걸치기 좋은 오버핏 코튼 자켓입니다.',
        49000,
        38900,
        'https://images.unsplash.com/photo-1551028719-00167b16eac5?w=800&q=80',
        'ON_SALE',
        60,
        true,
        true
    ),
    (
        '44444444-4444-4444-4444-444444444444',
        (select id from public.categories where slug = 'dress'),
        '플로럴 미디 원피스',
        '은은한 플로럴 패턴의 여성스러운 미디 기장 원피스입니다.',
        36000,
        28900,
        'https://images.unsplash.com/photo-1496747611176-843222e1e57c?w=800&q=80',
        'ON_SALE',
        50,
        true,
        true
    )
on conflict (id) do nothing;

-- ---------------------------------------------------------------------
-- 2-1. 추가 상품 (가방/신발/액세서리/상의/아우터)
-- ---------------------------------------------------------------------
insert into public.products (id, category_id, name, description, price, discount_price, thumbnail_url, status, stock_quantity, is_active, is_featured)
values
    (
        '55555555-5555-5555-5555-555555555555',
        (select id from public.categories where slug = 'bag'),
        '미니멀 레더 크로스백',
        '군더더기 없는 실루엣의 데일리 레더 크로스백입니다.',
        39000,
        29900,
        '/static/images/minimal-leather-crossbag.jpg',
        'ON_SALE',
        40,
        true,
        true
    ),
    (
        '66666666-6666-6666-6666-666666666666',
        (select id from public.categories where slug = 'shoes'),
        '스퀘어토 청키 로퍼',
        '이번 시즌 트렌드인 스퀘어토 디자인의 청키 로퍼입니다.',
        45000,
        35900,
        '/static/images/square-toe-chunky-loafer.jpg',
        'ON_SALE',
        35,
        true,
        true
    ),
    (
        '77777777-7777-7777-7777-777777777777',
        (select id from public.categories where slug = 'acc'),
        '투톤 볼캡',
        '어떤 룩에도 포인트를 더해주는 투톤 컬러 볼캡입니다.',
        19000,
        14900,
        '/static/images/two-tone-ballcap.jpg',
        'ON_SALE',
        70,
        true,
        true
    ),
    (
        '88888888-8888-8888-8888-888888888888',
        (select id from public.categories where slug = 'top'),
        '하이넥 케이블 니트',
        '포근한 촉감의 케이블 패턴 하이넥 니트입니다.',
        35000,
        27900,
        'https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=800&q=80',
        'ON_SALE',
        55,
        true,
        true
    ),
    (
        '99999999-9999-9999-9999-999999999999',
        (select id from public.categories where slug = 'outer'),
        '클래식 캐시미어 블렌드 싱글 코트',
        '정교한 테일러링과 고급스러운 캐시미어 혼방 소재로 제작된 프리미엄 싱글 코트입니다.',
        79000,
        59900,
        'https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=800&q=80',
        'ON_SALE',
        30,
        true,
        true
    ),
    (
        'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
        (select id from public.categories where slug = 'outer'),
        '미니멀 세미오버 테일러드 블레이저',
        '어깨 라인이 자연스럽게 떨어지는 세미오버 실루엣의 시즌 베스트셀러 블레이저입니다.',
        59000,
        46900,
        'https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=800&q=80',
        'ON_SALE',
        45,
        true,
        true
    )
on conflict (id) do nothing;
        30,
        true,
        true
    )
on conflict (id) do nothing;

-- 이미 등록된 상품도 최신 썸네일로 갱신 (재실행 대비)
update public.products
set thumbnail_url = case id
    when '11111111-1111-1111-1111-111111111111' then '/static/images/basic-crop-tee.jpg'
    when '22222222-2222-2222-2222-222222222222' then 'https://plus.unsplash.com/premium_photo-1674828601362-afb73c907ebe?w=600&q=80'
    when '33333333-3333-3333-3333-333333333333' then 'https://images.unsplash.com/photo-1551028719-00167b16eac5?w=600&q=80'
    when '44444444-4444-4444-4444-444444444444' then 'https://images.unsplash.com/photo-1572804013309-59a88b7e92f1?w=600&q=80'
    when '55555555-5555-5555-5555-555555555555' then '/static/images/minimal-leather-crossbag.jpg'
    when '66666666-6666-6666-6666-666666666666' then '/static/images/square-toe-chunky-loafer.jpg'
    when '77777777-7777-7777-7777-777777777777' then '/static/images/two-tone-ballcap.jpg'
    when '88888888-8888-8888-8888-888888888888' then 'https://images.unsplash.com/photo-1583743814966-8936f5b7be1a?w=600&q=80'
    when '99999999-9999-9999-9999-999999999999' then 'https://images.unsplash.com/photo-1591047139829-d91aecb6caea?w=800&q=80'
end
where id in (
    '11111111-1111-1111-1111-111111111111',
    '22222222-2222-2222-2222-222222222222',
    '33333333-3333-3333-3333-333333333333',
    '44444444-4444-4444-4444-444444444444',
    '55555555-5555-5555-5555-555555555555',
    '66666666-6666-6666-6666-666666666666',
    '77777777-7777-7777-7777-777777777777',
    '88888888-8888-8888-8888-888888888888'
);

-- ---------------------------------------------------------------------
-- 3. 상품 이미지 (썸네일 외 추가 이미지 1장씩)
-- ---------------------------------------------------------------------
insert into public.product_images (product_id, image_url, sort_order)
values
    ('11111111-1111-1111-1111-111111111111', 'https://picsum.photos/seed/vibe-crop-tee/600/700', 0),
    ('11111111-1111-1111-1111-111111111111', 'https://picsum.photos/seed/vibe-crop-tee-2/600/700', 1),
    ('22222222-2222-2222-2222-222222222222', 'https://picsum.photos/seed/vibe-wide-denim/600/700', 0),
    ('22222222-2222-2222-2222-222222222222', 'https://picsum.photos/seed/vibe-wide-denim-2/600/700', 1),
    ('33333333-3333-3333-3333-333333333333', 'https://picsum.photos/seed/vibe-cotton-jacket/600/700', 0),
    ('33333333-3333-3333-3333-333333333333', 'https://picsum.photos/seed/vibe-cotton-jacket-2/600/700', 1),
    ('44444444-4444-4444-4444-444444444444', 'https://picsum.photos/seed/vibe-floral-dress/600/700', 0),
    ('44444444-4444-4444-4444-444444444444', 'https://picsum.photos/seed/vibe-floral-dress-2/600/700', 1);

-- ---------------------------------------------------------------------
-- 4. 첫 번째 상품(베이직 크롭 티셔츠) 옵션 9개 : 색상(블랙/화이트/베이지) x 사이즈(S/M/L)
-- ---------------------------------------------------------------------
insert into public.product_options (product_id, option_name, option_value, additional_price, stock_quantity)
select
    '11111111-1111-1111-1111-111111111111',
    '컬러/사이즈',
    color || ' / ' || size,
    0,
    20
from
    (values ('블랙'), ('화이트'), ('베이지')) as colors(color),
    (values ('S'), ('M'), ('L')) as sizes(size);
