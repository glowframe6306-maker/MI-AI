create table if not exists public.mi_direct_messages (
    id uuid primary key default gen_random_uuid(),
    sender_uid text not null,
    sender_email text not null,
    recipient_email text not null,
    message text not null check (char_length(message) between 1 and 5000),
    is_read boolean not null default false,
    created_at timestamptz not null default now()
);

create index if not exists mi_direct_messages_recipient_created_idx
on public.mi_direct_messages (recipient_email, created_at desc);

create index if not exists mi_direct_messages_sender_created_idx
on public.mi_direct_messages (sender_email, created_at desc);

alter table public.mi_direct_messages enable row level security;

-- Browser access is intentionally blocked.
-- The authenticated Flask backend uses SUPABASE_SERVICE_ROLE_KEY.
revoke all on table public.mi_direct_messages from anon, authenticated;