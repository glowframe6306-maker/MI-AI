-- Supabase schema and RLS policies for chat persistence, users, admins, and analytics

create extension if not exists "pgcrypto";

-- Users table
create table if not exists users (
  id text primary key,
  email text unique,
  full_name text,
  age int,
  is_admin boolean default false,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Admin table for dashboard management
create table if not exists admins (
  id uuid primary key default gen_random_uuid(),
  user_id text references users(id) on delete set null,
  email text unique not null,
  role text default 'admin',
  active boolean default true,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Conversation persistence
create table if not exists conversations (
  id text primary key,
  session_id text not null,
  user_id text references users(id) on delete set null,
  user_email text,
  status text default 'active',
  title text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Chat messages
create table if not exists messages (
  id uuid primary key default gen_random_uuid(),
  conversation_id text not null references conversations(id) on delete cascade,
  session_id text not null,
  user_id text references users(id) on delete set null,
  user_email text,
  role text not null,
  content text not null,
  model text,
  token_usage int,
  ip_address text,
  user_agent text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- Analytics events log
create table if not exists analytics_events (
  id uuid primary key default gen_random_uuid(),
  event_type text not null,
  user_id text references users(id) on delete set null,
  conversation_id text references conversations(id) on delete set null,
  message_id uuid references messages(id) on delete set null,
  metadata jsonb,
  created_at timestamptz default now()
);

-- Views for admin queries
create view if not exists conversation_stats as
select
  c.id,
  c.session_id,
  c.user_id,
  c.user_email,
  c.status,
  c.title,
  c.created_at,
  c.updated_at,
  count(m.id) as messages_count
from conversations c
left join messages m on m.conversation_id = c.id
group by c.id;

create view if not exists user_stats as
select
  u.id,
  u.email,
  u.is_admin,
  u.created_at,
  u.updated_at,
  count(distinct c.id) as conversations_count,
  count(m.id) as messages_count
from users u
left join conversations c on c.user_id = u.id
left join messages m on m.user_id = u.id
group by u.id;

create view if not exists analytics_overview as
select
  (select count(*) from conversations) as total_conversations,
  (select count(*) from messages) as total_messages,
  (select count(*) from messages where created_at >= now() - interval '1 day') as messages_today,
  (select count(*) from messages where created_at >= now() - interval '7 day') as messages_this_week,
  (select count(*) from messages where created_at >= now() - interval '30 day') as messages_this_month,
  (select count(*) from admins) as total_admins,
  (select count(*) from users) as total_users;

-- RLS policies
alter table users enable row level security;
create policy "Users can select their own user record" on users for select using (
  auth.uid() = id or auth.role() = 'service_role'
);
create policy "Service role can insert users" on users for insert using (
  auth.role() = 'service_role'
);
create policy "Service role can update users" on users for update using (
  auth.role() = 'service_role'
);

alter table conversations enable row level security;
create policy "Conversation owners can select their records" on conversations for select using (
  auth.uid() = user_id or auth.role() = 'service_role'
);
create policy "Service role can insert conversations" on conversations for insert using (
  auth.role() = 'service_role'
);
create policy "Service role can update conversations" on conversations for update using (
  auth.role() = 'service_role'
);

alter table messages enable row level security;
create policy "Message owners can select their records" on messages for select using (
  auth.uid() = user_id or auth.role() = 'service_role'
);
create policy "Service role can insert messages" on messages for insert using (
  auth.role() = 'service_role'
);
create policy "Service role can update messages" on messages for update using (
  auth.role() = 'service_role'
);

alter table admins enable row level security;
create policy "Admins can select admin data" on admins for select using (
  auth.role() = 'service_role'
);
create policy "Service role can insert admins" on admins for insert using (
  auth.role() = 'service_role'
);
create policy "Service role can update admins" on admins for update using (
  auth.role() = 'service_role'
);

alter table analytics_events enable row level security;
create policy "Service role can insert analytics" on analytics_events for insert using (
  auth.role() = 'service_role'
);
create policy "Service role can select analytics" on analytics_events for select using (
  auth.role() = 'service_role'
);
