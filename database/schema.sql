-- MandiMate schema + seed data. Run in Supabase -> SQL Editor.
create extension if not exists "pgcrypto";

create table products (
  id uuid primary key default gen_random_uuid(),
  name text unique not null,
  unit text not null default 'kg',
  price numeric not null,
  stock numeric not null check (stock >= 0),
  aliases text[] not null default '{}'
);
create table vendors (
  id uuid primary key default gen_random_uuid(),
  name text unique not null,
  phone text,
  language text not null default 'en',
  aliases text[] not null default '{}',
  balance_due numeric not null default 0
);
create table orders (
  id uuid primary key default gen_random_uuid(),
  vendor_id uuid references vendors(id),
  status text not null default 'draft' check (status in ('draft','confirmed','cancelled')),
  total numeric not null default 0,
  idempotency_key text unique,
  source_text text,
  language text,
  created_at timestamptz not null default now()
);
create table order_items (
  id uuid primary key default gen_random_uuid(),
  order_id uuid references orders(id) on delete cascade,
  product_id uuid references products(id),
  quantity numeric not null check (quantity > 0),
  unit_price numeric not null
);
create table notifications (
  id uuid primary key default gen_random_uuid(),
  order_id uuid references orders(id),
  vendor_id uuid references vendors(id),
  channel text not null,
  body text not null,
  status text not null,
  created_at timestamptz not null default now()
);
create table audit_log (
  id bigserial primary key,
  actor text not null,
  action text not null,
  detail jsonb,
  created_at timestamptz not null default now()
);

-- Atomic helpers: stock can never go negative, orders can only be confirmed once.
create or replace function reserve_stock(p_product_id uuid, p_qty numeric)
returns boolean language plpgsql as $$
declare n int;
begin
  update products set stock = stock - p_qty where id = p_product_id and stock >= p_qty;
  get diagnostics n = row_count;
  return n > 0;
end $$;

create or replace function release_stock(p_product_id uuid, p_qty numeric)
returns void language sql as $$
  update products set stock = stock + p_qty where id = p_product_id;
$$;

create or replace function confirm_order_tx(p_order_id uuid)
returns boolean language plpgsql as $$
declare v_vendor uuid; v_total numeric;
begin
  update orders set status = 'confirmed'
    where id = p_order_id and status = 'draft'
    returning vendor_id, total into v_vendor, v_total;
  if not found then return false; end if;
  update vendors set balance_due = balance_due + v_total where id = v_vendor;
  return true;
end $$;

-- Seed data
insert into products (name, unit, price, stock, aliases) values
 ('Tomato',  'kg', 30, 500, '{ಟೊಮೇಟೊ,தக்காளி,टमाटर,tamatar,thakkali}'),
 ('Onion',   'kg', 40, 800, '{ಈರುಳ್ಳಿ,வெங்காயம்,प्याज,pyaz,eerulli}'),
 ('Potato',  'kg', 35, 700, '{ಆಲೂಗಡ್ಡೆ,உருளைக்கிழங்கு,आलू,aloo}'),
 ('Carrot',  'kg', 50, 200, '{ಕ್ಯಾರೆಟ್,கேரட்,गाजर,gajar}'),
 ('Beans',   'kg', 70, 150, '{ಬೀನ್ಸ್,பீன்ஸ்,बीन्स,फलियां}'),
 ('Cabbage', 'kg', 25, 300, '{ಎಲೆಕೋಸು,முட்டைகோஸ்,पत्ता गोभी,patta gobhi}');

insert into vendors (name, phone, language, aliases) values
 ('Ramesh Stores',      '+910000000001', 'kn', '{ರಮೇಶ್ ಸ್ಟೋರ್ಸ್,Ramesh}'),
 ('Lakshmi Vegetables', '+910000000002', 'ta', '{லட்சுமி வெஜிடபிள்ஸ்,Lakshmi}'),
 ('Sharma Traders',     '+910000000003', 'hi', '{शर्मा ट्रेडर्स,Sharma}'),
 ('Fresh Basket',       '+910000000004', 'en', '{Basket}');
