// Shapes returned by /api/reader. Keep in sync with backend/cfaw_news/briefing.
import type { TrackingPlan } from "../FollowIntentForm";

export type Topic =
  | "models"
  | "agents"
  | "research"
  | "engineering"
  | "products"
  | "industry";
export type Prefs = {
  topics: Topic[];
  depth: "balanced" | "technical" | "overview";
  budget_minutes: 3 | 7 | 15;
  exploration: boolean;
};
export type Claim = { statement: string; quote: string; kind: string };
export type Action = { request_id: string; kind: string; at: string; version: string };
export type Entry = {
  content_kind?: string;
  version: string;
  title: string;
  summary: string;
  source: string;
  role: string;
  url: string;
  published_at: string | null;
  action: string;
  evidence: string;
  claims: Claim[];
  conditions: string[];
  limitations: string[];
};
export type Story = {
  content_kind?: string;
  id: string;
  version: string;
  title: string;
  summary: string;
  reason: string;
  topic: Topic;
  topic_label: string;
  action: string;
  evidence: string;
  conditions: string[];
  limitations: string[];
  source: string;
  source_role: string;
  url: string;
  published_at: string | null;
  captured_at: string;
  source_count: number;
  report_count: number;
  qualified: boolean;
  protected: boolean;
  known: boolean;
  dismissed: boolean;
  saved: boolean;
  relevant: boolean;
  claims: Claim[];
  timeline: Entry[];
  reading_seconds: number;
  actions: Action[];
  subject?: string;
  object?: string;
  /** Judged under an older policy epoch; waiting to be re-judged. */
  policy_stale?: boolean;
};
export type Follow = {
  id: string;
  name: string;
  query: string;
  active: boolean;
  last_checked: string | null;
  last_status: string;
  last_errors?: string[];
  event_ids: string[];
  unread_ids: string[];
  material_versions: string[];
  description?: string;
  intent_plan?: TrackingPlan;
  reasons?: Record<string, string>;
};
export type Source = {
  id: string;
  description?: string;
  priority?: number;
  name: string;
  role: string;
  url: string;
  kind: string;
  state: {
    status: string;
    at?: string;
    last_success?: string;
    count?: number;
    added?: number;
    with_text?: number;
    http_status?: number;
    error?: string;
  };
};
export type Run = {
  id: string;
  /** queued | running | completed | cancelled | failed */
  state: string;
  stage: string;
  sources_done: number;
  analyzed: number;
  total?: number;
  failed: number;
  errors: string[];
  kind?: string;
  query?: string;
  follow_name?: string;
  found?: number;
  result_versions?: string[];
  follow_id?: string;
};
export type Archive = {
  content_kind?: string;
  id: string;
  version: string;
  title: string;
  source: string;
  url: string;
  published_at: string | null;
  captured_at?: string;
  summary?: string;
  /** pending | retrying | failed | ai | unrelated | uncertain | time_uncertain */
  status: string;
  failure?: { code: string; attempts: number; retry_at: string | null };
};
export type View = {
  as_of: string;
  last_visit?: string | null;
  events: Story[];
  focus: string[];
  radar: string[];
  archive: Archive[];
  budget_seconds: number;
  estimated_seconds: number;
  counts: {
    materials: number;
    events: number;
    eligible: number;
    pending: number;
    unrelated: number;
    failed?: number;
  };
  preferences: Prefs;
  sources: Source[];
  model_configured: boolean;
  usage?: {
    requests_today: number;
    tokens_today: number;
    request_limit: number | null;
    token_limit: number | null;
  };
  run: Run | null;
  queue?: Run[];
  follows?: Follow[];
  saved_events?: Story[];
  confirmed_follow_id?: string;
};
export type Page = "briefing" | "discover" | "following" | "saved" | "library";
