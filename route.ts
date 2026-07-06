import { NextResponse } from 'next/server';
import { getSupabaseAdmin } from '@/lib/supabase-server';

async function resolveUserFromRequest(req: Request) {
  const authHeader = req.headers.get('authorization') || '';
  const match = authHeader.match(/^Bearer\s+(.+)$/i);
  const token = match ? match[1] : null;

  if (!token) {
    return null;
  }

  const supabase = getSupabaseAdmin();
  if (!supabase) {
    return null;
  }

  try {
    const { data, error } = await supabase.auth.getUser(token as any);
    if (!error && data?.user) {
      return data.user;
    }
  } catch {
    // invalid or expired token
  }

  return null;
}

export async function GET(request: Request) {
  try {
    const body = await request.clone().json().catch(() => null);
    const user = await resolveUserFromRequest(request);
    if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

    const supabase = getSupabaseAdmin();
    if (!supabase) return NextResponse.json({ error: 'Server misconfigured' }, { status: 500 });

    const { data, error } = await supabase
      .from('conversations')
      .select('*')
      .eq('user_id', user.id)
      .order('updated_at', { ascending: false });
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });

    return NextResponse.json({ conversations: data });
  } catch {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.clone().json().catch(() => null);
    const user = await resolveUserFromRequest(request);
    if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

    const title = String(body?.title ?? '');
    const session_id = String(body?.session_id ?? '');
    const id = body?.id ?? `chat_${Date.now()}`;

    const supabase = getSupabaseAdmin();
    if (!supabase) return NextResponse.json({ error: 'Server misconfigured' }, { status: 500 });

    const payload = {
      id: String(id),
      session_id,
      user_id: user.id,
      user_email: user.email ?? null,
      title,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };

    const { error } = await supabase.from('conversations').insert(payload);
    if (error) return NextResponse.json({ error: error.message }, { status: 500 });

    return NextResponse.json({ ok: true, conversation: payload });
  } catch {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
