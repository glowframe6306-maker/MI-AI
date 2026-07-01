export type Conversation = {
  id: string;
  session_id: string;
  user_id: string | null;
  user_email: string | null;
  status: string;
  title: string | null;
  messages_count: number;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  conversation_id: string;
  session_id: string;
  user_id: string | null;
  user_email: string | null;
  role: 'user' | 'assistant' | 'system';
  content: string;
  model: string;
  token_usage: number | null;
  ip_address: string | null;
  user_agent: string | null;
  created_at: string;
  updated_at: string;
};

export type UserRow = {
  id: string;
  email: string;
  is_admin: boolean;
  conversations_count: number;
  messages_count: number;
  created_at: string;
  updated_at: string;
};

export type AdminRow = {
  id: string;
  user_id: string | null;
  email: string;
  role: string;
  active: boolean;
  created_at: string;
  updated_at: string;
};

export type AnalyticsStats = {
  total_conversations: number;
  total_messages: number;
  messages_today: number;
  messages_this_week: number;
  messages_this_month: number;
  total_admins: number;
  total_users: number;
};
