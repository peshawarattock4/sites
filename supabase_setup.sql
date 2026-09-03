-- ==========================================================
--  SHOP  •  Supabase schema + RLS + storage
--  Supabase Dashboard > SQL Editor > New query > Run
-- ==========================================================
create extension if not exists "pgcrypto";

-- ---------------- CATEGORIES ----------------
create table if not exists public.categories (
  id          uuid primary key default gen_random_uuid(),
  name        text not null unique,
  icon        text default '🛍️',
  sort_order  int  default 0,
  is_active   boolean default true,
  created_at  timestamptz default now()
);

-- ---------------- PRODUCTS ----------------
create table if not exists public.products (
  id           uuid primary key default gen_random_uuid(),
  title        text not null,
  description  text default '',
  highlights   jsonb default '[]'::jsonb,   -- ["Pure cotton","Free delivery"]
  images       jsonb default '[]'::jsonb,   -- max 5 public URLs
  price        numeric(12,2) not null default 0,
  sale_price   numeric(12,2),               -- null = koi sale nahi
  stock        int default 0,
  category_id  uuid references public.categories(id) on delete set null,
  offer_text   text,                        -- "Buy 1 Get 1 Free"
  badge        text,                        -- "NEW" / "HOT"
  is_featured  boolean default false,
  is_active    boolean default true,
  created_at   timestamptz default now(),
  updated_at   timestamptz default now()
);

-- ---------------- ORDERS ----------------
create table if not exists public.orders (
  id            uuid primary key default gen_random_uuid(),
  order_no      bigserial unique,
  customer_name text not null,
  phone         text not null,
  whatsapp      text not null,
  address       text not null,
  city          text,
  note          text,
  items         jsonb not null default '[]'::jsonb,
  subtotal      numeric(12,2) not null default 0,
  delivery_fee  numeric(12,2) not null default 0,
  total         numeric(12,2) not null default 0,
  status        text not null default 'new'
                check (status in ('new','confirmed','shipped','delivered','cancelled')),
  created_at    timestamptz default now()
);

-- ---------------- LIVE CHAT ----------------
create table if not exists public.chat_messages (
  id         bigserial primary key,
  session_id text not null,
  sender     text not null check (sender in ('user','admin')),
  name       text,
  whatsapp   text,
  message    text not null,
  is_read    boolean default false,
  created_at timestamptz default now()
);

-- ---------------- CUSTOM BANNERS (optional) ----------------
create table if not exists public.banners (
  id         uuid primary key default gen_random_uuid(),
  title      text,
  subtitle   text,
  image_url  text,
  bg_from    text default '#111827',
  bg_to      text default '#e11d48',
  sort_order int default 0,
  is_active  boolean default true,
  created_at timestamptz default now()
);

-- ---------------- SETTINGS ----------------
create table if not exists public.settings (
  key   text primary key,
  value text
);

insert into public.settings(key, value) values
  ('shop_name',       'Zaiqa Store'),
  ('owner_whatsapp',  '923001234567'),
  ('delivery_fee',    '200'),
  ('free_over',       '5000'),
  ('announcement',    '🚚 Rs 5,000 se upar FREE delivery  •  Cash on Delivery available  •  100% original products')
on conflict (key) do nothing;

-- ---------------- INDEXES ----------------
create index if not exists idx_products_cat     on public.products(category_id);
create index if not exists idx_products_active  on public.products(is_active);
create index if not exists idx_products_sale    on public.products(sale_price);
create index if not exists idx_chat_session     on public.chat_messages(session_id, created_at);
create index if not exists idx_orders_created   on public.orders(created_at desc);

-- ---------------- updated_at trigger ----------------
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin new.updated_at = now(); return new; end $$;

drop trigger if exists trg_products_touch on public.products;
create trigger trg_products_touch before update on public.products
for each row execute function public.touch_updated_at();

-- ---------------- ROW LEVEL SECURITY ----------------
alter table public.categories     enable row level security;
alter table public.products       enable row level security;
alter table public.banners        enable row level security;
alter table public.settings       enable row level security;
alter table public.orders         enable row level security;
alter table public.chat_messages  enable row level security;

-- public sirf active catalog parh sakta hai
drop policy if exists p_read_categories on public.categories;
create policy p_read_categories on public.categories
  for select to anon, authenticated using (is_active);

drop policy if exists p_read_products on public.products;
create policy p_read_products on public.products
  for select to anon, authenticated using (is_active);

drop policy if exists p_read_banners on public.banners;
create policy p_read_banners on public.banners
  for select to anon, authenticated using (is_active);

drop policy if exists p_read_settings on public.settings;
create policy p_read_settings on public.settings
  for select to anon, authenticated using (true);

-- customer order de sakta hai, magar kisi ka order parh nahi sakta
drop policy if exists p_insert_order on public.orders;
create policy p_insert_order on public.orders
  for insert to anon, authenticated with check (true);

-- chat_messages: koi public policy NAHI.
-- ye sirf server-side (service_role) se read/write hota hai -> phone numbers leak nahi honge.

-- ---------------- STORAGE BUCKET ----------------
insert into storage.buckets (id, name, public)
values ('product-images', 'product-images', true)
on conflict (id) do nothing;
