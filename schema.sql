-- =====================================================================
-- VIBE-FASHION 쇼핑몰 데이터베이스 스키마
-- Supabase SQL Editor에서 실행하세요.
-- =====================================================================

-- ---------------------------------------------------------------------
-- 0. 확장 기능
-- ---------------------------------------------------------------------
create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------
-- 1. ENUM 타입 정의
-- ---------------------------------------------------------------------
do $$
begin
    if not exists (select 1 from pg_type where typname = 'customer_grade') then
        create type customer_grade as enum ('BRONZE', 'SILVER', 'GOLD', 'VIP');
    end if;
    if not exists (select 1 from pg_type where typname = 'product_status') then
        create type product_status as enum ('ON_SALE', 'SOLD_OUT', 'HIDDEN');
    end if;
    if not exists (select 1 from pg_type where typname = 'order_status') then
        create type order_status as enum ('PENDING', 'PAID', 'PREPARING', 'SHIPPED', 'DELIVERED', 'CANCELLED', 'REFUNDED');
    end if;
    if not exists (select 1 from pg_type where typname = 'refund_status') then
        create type refund_status as enum ('REQUESTED', 'APPROVED', 'REJECTED', 'COMPLETED');
    end if;
    if not exists (select 1 from pg_type where typname = 'notification_type') then
        create type notification_type as enum ('ORDER', 'REFUND', 'EVENT', 'SYSTEM');
    end if;
end $$;

-- ---------------------------------------------------------------------
-- 2. profiles : auth.users 와 1:1 연결되는 사용자 프로필
-- ---------------------------------------------------------------------
create table if not exists public.profiles (
    id uuid primary key references auth.users(id) on delete cascade,
    email text,
    full_name text,
    avatar_url text,
    phone text,
    grade customer_grade not null default 'BRONZE',
    total_spent bigint not null default 0,
    is_admin boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 3. categories : 상품 카테고리 (대/중분류 지원을 위한 self reference)
-- ---------------------------------------------------------------------
create table if not exists public.categories (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    slug text not null unique,
    parent_id uuid references public.categories(id) on delete set null,
    sort_order integer not null default 0,
    created_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------
-- 4. products : 상품
-- ---------------------------------------------------------------------
create table if not exists public.products (
    id uuid primary key default gen_random_uuid(),
    category_id uuid references public.categories(id) on delete set null,
    name text not null,
    description text,
    price bigint not null check (price >= 0),
    discount_price bigint check (discount_price >= 0),
    thumbnail_url text,
    status product_status not null default 'ON_SALE',
    stock_quantity integer not null default 0 check (stock_quantity >= 0),
    is_active boolean not null default true,
    is_featured boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_products_category_id on public.products(category_id);
create index if not exists idx_products_status on public.products(status);
create index if not exists idx_products_featured on public.products(is_active, is_featured);

-- ---------------------------------------------------------------------
-- 5. product_options : 상품 옵션 (사이즈, 색상 등)
-- ---------------------------------------------------------------------
create table if not exists public.product_options (
    id uuid primary key default gen_random_uuid(),
    product_id uuid not null references public.products(id) on delete cascade,
    option_name text not null,
    option_value text not null,
    additional_price bigint not null default 0,
    stock_quantity integer not null default 0 check (stock_quantity >= 0),
    created_at timestamptz not null default now()
);

create index if not exists idx_product_options_product_id on public.product_options(product_id);

-- ---------------------------------------------------------------------
-- 6. product_images : 상품 이미지 (다중 이미지)
-- ---------------------------------------------------------------------
create table if not exists public.product_images (
    id uuid primary key default gen_random_uuid(),
    product_id uuid not null references public.products(id) on delete cascade,
    image_url text not null,
    sort_order integer not null default 0,
    created_at timestamptz not null default now()
);

create index if not exists idx_product_images_product_id on public.product_images(product_id);

-- ---------------------------------------------------------------------
-- 7. carts : 장바구니
-- ---------------------------------------------------------------------
create table if not exists public.carts (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    product_id uuid not null references public.products(id) on delete cascade,
    option_id uuid references public.product_options(id) on delete cascade,
    quantity integer not null default 1 check (quantity > 0),
    created_at timestamptz not null default now(),
    unique (user_id, product_id, option_id)
);

create index if not exists idx_carts_user_id on public.carts(user_id);

-- ---------------------------------------------------------------------
-- 8. orders : 주문
-- ---------------------------------------------------------------------
create table if not exists public.orders (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    order_number text not null unique,
    status order_status not null default 'PENDING',
    total_amount bigint not null check (total_amount >= 0),
    receiver_name text not null,
    receiver_phone text not null,
    shipping_address text not null,
    payment_method text,
    ordered_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_orders_user_id on public.orders(user_id);
create index if not exists idx_orders_status on public.orders(status);

-- ---------------------------------------------------------------------
-- 9. order_items : 주문 상세 (구매 시점 정보 스냅샷)
-- ---------------------------------------------------------------------
create table if not exists public.order_items (
    id uuid primary key default gen_random_uuid(),
    order_id uuid not null references public.orders(id) on delete cascade,
    product_id uuid references public.products(id) on delete set null,
    option_id uuid references public.product_options(id) on delete set null,
    product_name text not null,
    option_name text,
    price bigint not null check (price >= 0),
    quantity integer not null check (quantity > 0),
    subtotal bigint not null check (subtotal >= 0),
    created_at timestamptz not null default now()
);

create index if not exists idx_order_items_order_id on public.order_items(order_id);
create index if not exists idx_order_items_product_id on public.order_items(product_id);

-- ---------------------------------------------------------------------
-- 10. refunds : 환불/반품
-- ---------------------------------------------------------------------
create table if not exists public.refunds (
    id uuid primary key default gen_random_uuid(),
    order_id uuid not null references public.orders(id) on delete cascade,
    order_item_id uuid references public.order_items(id) on delete cascade,
    user_id uuid not null references public.profiles(id) on delete cascade,
    reason text not null,
    status refund_status not null default 'REQUESTED',
    refund_amount bigint not null check (refund_amount >= 0),
    requested_at timestamptz not null default now(),
    processed_at timestamptz
);

create index if not exists idx_refunds_order_id on public.refunds(order_id);
create index if not exists idx_refunds_user_id on public.refunds(user_id);

-- ---------------------------------------------------------------------
-- 11. notifications : 알림
-- ---------------------------------------------------------------------
create table if not exists public.notifications (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references public.profiles(id) on delete cascade,
    type notification_type not null default 'SYSTEM',
    title text not null,
    message text,
    is_read boolean not null default false,
    created_at timestamptz not null default now()
);

create index if not exists idx_notifications_user_id on public.notifications(user_id);

-- ---------------------------------------------------------------------
-- 12. reviews : 상품 리뷰
-- ---------------------------------------------------------------------
create table if not exists public.reviews (
    id uuid primary key default gen_random_uuid(),
    product_id uuid not null references public.products(id) on delete cascade,
    user_id uuid not null references public.profiles(id) on delete cascade,
    order_item_id uuid references public.order_items(id) on delete set null,
    rating smallint not null check (rating between 1 and 5),
    content text,
    image_url text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (order_item_id)
);

create index if not exists idx_reviews_product_id on public.reviews(product_id);
create index if not exists idx_reviews_user_id on public.reviews(user_id);

-- =====================================================================
-- 13. 공통 트리거 함수 : updated_at 자동 갱신
-- =====================================================================
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists trg_profiles_updated_at on public.profiles;
create trigger trg_profiles_updated_at
    before update on public.profiles
    for each row execute function public.set_updated_at();

drop trigger if exists trg_products_updated_at on public.products;
create trigger trg_products_updated_at
    before update on public.products
    for each row execute function public.set_updated_at();

drop trigger if exists trg_orders_updated_at on public.orders;
create trigger trg_orders_updated_at
    before update on public.orders
    for each row execute function public.set_updated_at();

drop trigger if exists trg_reviews_updated_at on public.reviews;
create trigger trg_reviews_updated_at
    before update on public.reviews
    for each row execute function public.set_updated_at();

-- =====================================================================
-- 14. handle_new_user : 회원가입(소셜 로그인 포함) 시 profiles 자동 생성
-- =====================================================================
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles (id, email, full_name, avatar_url, phone, grade)
    values (
        new.id,
        new.email,
        coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name'),
        new.raw_user_meta_data ->> 'avatar_url',
        new.raw_user_meta_data ->> 'phone',
        'BRONZE'
    )
    on conflict (id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert on auth.users
    for each row execute function public.handle_new_user();

-- =====================================================================
-- 15. update_customer_grade : 누적 구매 금액 기반 고객 등급 자동 갱신
--     기준(예시) : BRONZE(0~) / SILVER(100,000~) / GOLD(500,000~) / VIP(1,000,000~)
-- =====================================================================
create or replace function public.update_customer_grade(p_user_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
    v_total_spent bigint;
    v_new_grade customer_grade;
begin
    select coalesce(sum(total_amount), 0)
    into v_total_spent
    from public.orders
    where user_id = p_user_id
      and status in ('PAID', 'PREPARING', 'SHIPPED', 'DELIVERED');

    if v_total_spent >= 1000000 then
        v_new_grade := 'VIP';
    elsif v_total_spent >= 500000 then
        v_new_grade := 'GOLD';
    elsif v_total_spent >= 100000 then
        v_new_grade := 'SILVER';
    else
        v_new_grade := 'BRONZE';
    end if;

    update public.profiles
    set total_spent = v_total_spent,
        grade = v_new_grade
    where id = p_user_id
      and (total_spent is distinct from v_total_spent or grade is distinct from v_new_grade);
end;
$$;

-- 주문 상태가 변경될 때마다 고객 등급을 재계산하는 트리거
create or replace function public.trg_orders_grade_update()
returns trigger
language plpgsql
as $$
begin
    perform public.update_customer_grade(new.user_id);
    return new;
end;
$$;

drop trigger if exists on_orders_change_update_grade on public.orders;
create trigger on_orders_change_update_grade
    after insert or update of status on public.orders
    for each row execute function public.trg_orders_grade_update();

-- =====================================================================
-- 16. Row Level Security (RLS) 설정
-- =====================================================================
alter table public.profiles enable row level security;
alter table public.categories enable row level security;
alter table public.products enable row level security;
alter table public.product_options enable row level security;
alter table public.product_images enable row level security;
alter table public.carts enable row level security;
alter table public.orders enable row level security;
alter table public.order_items enable row level security;
alter table public.refunds enable row level security;
alter table public.notifications enable row level security;
alter table public.reviews enable row level security;

-- profiles : 본인만 조회/수정 가능
drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own" on public.profiles
    for select using (auth.uid() = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own" on public.profiles
    for update using (auth.uid() = id);

-- categories / products / product_options / product_images : 누구나 조회 가능
drop policy if exists "categories_select_all" on public.categories;
create policy "categories_select_all" on public.categories for select using (true);

drop policy if exists "products_select_all" on public.products;
create policy "products_select_all" on public.products for select using (true);

drop policy if exists "product_options_select_all" on public.product_options;
create policy "product_options_select_all" on public.product_options for select using (true);

drop policy if exists "product_images_select_all" on public.product_images;
create policy "product_images_select_all" on public.product_images for select using (true);

-- carts : 본인 데이터만 CRUD 가능
drop policy if exists "carts_owner_all" on public.carts;

drop policy if exists "본인 장바구니 조회" on public.carts;
create policy "본인 장바구니 조회" on public.carts
    for select using (auth.uid() = user_id);

drop policy if exists "본인 장바구니 추가" on public.carts;
create policy "본인 장바구니 추가" on public.carts
    for insert with check (auth.uid() = user_id);

drop policy if exists "본인 장바구니 수정" on public.carts;
create policy "본인 장바구니 수정" on public.carts
    for update using (auth.uid() = user_id) with check (auth.uid() = user_id);

drop policy if exists "본인 장바구니 삭제" on public.carts;
create policy "본인 장바구니 삭제" on public.carts
    for delete using (auth.uid() = user_id);

-- orders : 본인 주문만 조회/생성
drop policy if exists "orders_select_own" on public.orders;
create policy "orders_select_own" on public.orders
    for select using (auth.uid() = user_id);

drop policy if exists "orders_insert_own" on public.orders;
create policy "orders_insert_own" on public.orders
    for insert with check (auth.uid() = user_id);

-- order_items : 본인 주문의 상세만 조회 가능
drop policy if exists "order_items_select_own" on public.order_items;
create policy "order_items_select_own" on public.order_items
    for select using (
        exists (
            select 1 from public.orders o
            where o.id = order_items.order_id and o.user_id = auth.uid()
        )
    );

-- refunds : 본인 환불건만 조회/생성
drop policy if exists "refunds_select_own" on public.refunds;
create policy "refunds_select_own" on public.refunds
    for select using (auth.uid() = user_id);

drop policy if exists "refunds_insert_own" on public.refunds;
create policy "refunds_insert_own" on public.refunds
    for insert with check (auth.uid() = user_id);

-- notifications : 본인 알림만 조회/수정(읽음 처리)
drop policy if exists "notifications_select_own" on public.notifications;
create policy "notifications_select_own" on public.notifications
    for select using (auth.uid() = user_id);

drop policy if exists "notifications_update_own" on public.notifications;
create policy "notifications_update_own" on public.notifications
    for update using (auth.uid() = user_id);

-- reviews : 누구나 조회 가능, 본인만 작성/수정/삭제 가능
drop policy if exists "reviews_select_all" on public.reviews;
create policy "reviews_select_all" on public.reviews for select using (true);

drop policy if exists "reviews_owner_write" on public.reviews;
create policy "reviews_owner_write" on public.reviews
    for insert with check (auth.uid() = user_id);

drop policy if exists "reviews_owner_update" on public.reviews;
create policy "reviews_owner_update" on public.reviews
    for update using (auth.uid() = user_id);

drop policy if exists "reviews_owner_delete" on public.reviews;
create policy "reviews_owner_delete" on public.reviews
    for delete using (auth.uid() = user_id);
