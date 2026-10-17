export type LeadStatus =
  | "new"
  | "invite_review"
  | "to_invite"
  | "disqualified"
  | "invited"
  | "connected"
  | "messaged"
  | "replied"
  | "interested"
  | "meeting"
  | "not_interested"
  | "no_response"
  | "do_not_contact"
  | "error";

export type Settings = {
  id: number;
  engine_enabled: boolean;
  autopilot: boolean;
  auto_reply: boolean;
  company_name: string;
  company_website: string;
  company_pitch: string;
  value_props: string;
  case_studies: string;
  cta: string;
  sender_name: string;
  sender_role: string;
  icp: string;
  tone: string;
  language: string;
  extra_instructions: string;
  min_score: number;
  daily_invite_limit: number;
  weekly_invite_limit: number;
  daily_message_limit: number;
  working_days: number[];
  work_start_hour: number;
  work_end_hour: number;
  timezone: string;
  li_at: string | null;
  jsessionid: string | null;
  li_proxy: string | null;
  li_session_status: "ok" | "invalid" | "unknown";
  li_session_checked_at: string | null;
  li_profile: { name?: string; public_id?: string; urn_id?: string; headline?: string } | null;
  engagement_enabled: boolean;
  auto_comment: boolean;
  daily_like_limit: number;
  daily_comment_limit: number;
  engagement_topics: string;
  updated_at: string;
};

export type Campaign = {
  id: string;
  name: string;
  status: "draft" | "active" | "paused" | "archived";
  search_keywords: string;
  search_title: string;
  search_company: string;
  search_regions: string[];
  search_industries: string[];
  network_depths: string[];
  search_batch: number;
  search_offset: number;
  pipeline_buffer: number;
  icp_notes: string;
  ai_instructions: string;
  send_connection_note: boolean;
  first_message_delay_hours: number;
  followup_delays_days: number[];
  last_prospected_at: string | null;
  created_at: string;
  updated_at: string;
};

export type Lead = {
  id: string;
  campaign_id: string | null;
  urn_id: string;
  public_id: string | null;
  full_name: string;
  first_name: string;
  headline: string;
  location: string;
  company: string;
  profile_url: string;
  profile_text: string;
  status: LeadStatus;
  score: number | null;
  fit_reason: string;
  ai_summary: string;
  connection_note: string;
  intent: string | null;
  invited_at: string | null;
  connected_at: string | null;
  last_outbound_at: string | null;
  last_inbound_at: string | null;
  followups_sent: number;
  next_action_at: string | null;
  notes: string;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type Message = {
  id: string;
  lead_id: string;
  direction: "out" | "in";
  kind: "first_message" | "followup" | "reply" | "manual" | "inbound";
  body: string;
  status: "draft" | "approved" | "sent" | "failed" | "rejected" | "cancelled" | "received";
  ai_generated: boolean;
  intent: string | null;
  error: string | null;
  sent_at: string | null;
  created_at: string;
};

export type SdrEvent = {
  id: number;
  type: string;
  lead_id: string | null;
  campaign_id: string | null;
  detail: string;
  created_at: string;
};

export type Engagement = {
  id: string;
  lead_id: string | null;
  source: "lead" | "feed";
  post_urn: string;
  post_url: string;
  author_name: string;
  author_headline: string;
  post_text: string;
  post_age: string;
  status: "new" | "ready" | "done" | "skipped" | "failed";
  relevance: number | null;
  reason: string;
  want_like: boolean;
  liked_at: string | null;
  comment: string;
  comment_status: "none" | "draft" | "approved" | "posted" | "rejected" | "failed";
  commented_at: string | null;
  error: string | null;
  created_at: string;
};
