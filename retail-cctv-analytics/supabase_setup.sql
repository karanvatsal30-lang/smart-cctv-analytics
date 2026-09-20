-- ======================================================================
-- Smart CCTV Analytics — Production Supabase Schema & Row-Level Security
-- ======================================================================
-- Run this script in your Supabase Dashboard: SQL Editor -> New Query -> Run
-- ======================================================================

-- 1. PROFILES TABLE (Stores user identity and role)
create table if not exists public.profiles (
  id uuid references auth.users(id) on delete cascade primary key,
  email text,
  display_name text,
  station_role text default 'Store Operator',
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Enable Row-Level Security
alter table public.profiles enable row level security;

-- RLS Policies for profiles
create policy "Users can view own profile"
  on public.profiles for select
  using (auth.uid() = id);

create policy "Users can update own profile"
  on public.profiles for update
  using (auth.uid() = id);

-- 2. CAMERAS TABLE (Stores per-user CCTV camera configurations)
create table if not exists public.cameras (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  name text not null default 'Store CCTV Feed',
  source_type text not null default 'benchmark', -- 'benchmark', 'webcam', 'rtsp', 'file'
  config_data jsonb default '{}'::jsonb,
  active boolean default true,
  created_at timestamptz default now()
);

-- Enable Row-Level Security
alter table public.cameras enable row level security;

-- RLS Policies for cameras (strictly per user)
create policy "Users can view own cameras"
  on public.cameras for select
  using (auth.uid() = user_id);

create policy "Users can insert own cameras"
  on public.cameras for insert
  with check (auth.uid() = user_id);

create policy "Users can update own cameras"
  on public.cameras for update
  using (auth.uid() = user_id);

create policy "Users can delete own cameras"
  on public.cameras for delete
  using (auth.uid() = user_id);

-- 3. MONITORING REGIONS TABLE (Stores per-user checkout & shelf polygons)
create table if not exists public.monitoring_regions (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references auth.users(id) on delete cascade not null unique,
  checkout_name text default 'Main Checkout',
  checkout_polygon jsonb default '[]'::jsonb,
  shelf_name text default 'Shelf 1',
  shelf_polygon jsonb default '[]'::jsonb,
  updated_at timestamptz default now()
);

-- Enable Row-Level Security
alter table public.monitoring_regions enable row level security;

-- RLS Policies for monitoring_regions (strictly per user)
create policy "Users can view own monitoring regions"
  on public.monitoring_regions for select
  using (auth.uid() = user_id);

create policy "Users can insert own monitoring regions"
  on public.monitoring_regions for insert
  with check (auth.uid() = user_id);

create policy "Users can update own monitoring regions"
  on public.monitoring_regions for update
  using (auth.uid() = user_id);

-- 4. AUTOMATIC PROFILE CREATION TRIGGER
-- Whenever an authorized user is created in auth.users, create their profile row
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, email, display_name)
  values (
    new.id,
    new.email,
    coalesce(new.raw_user_meta_data->>'display_name', split_part(new.email, '@', 1))
  );
  return new;
end;
$$ language plpgsql security definer;

-- Drop trigger if exists, then recreate
drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();
