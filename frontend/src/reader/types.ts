// Shapes returned by /api/reader. Keep in sync with backend/northing_signal/briefing.
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
  /** Update at 00:00 and 12:00 while the service runs. */
  auto_refresh: boolean;
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
  /** First captured in the latest update. */
  new?: boolean;
  /** An older event that got a new report in the latest update. */
  updated?: boolean;
  /** Found while it was news. Late finds and undated reports are archived, not "today". */
  timely?: boolean;
  stale_reason?: "late" | "undated" | null;
  /** Known before the latest update: it has left the focus. Marked since: only greyed. */
  known_earlier?: boolean;
  score?: number;
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
export type Refresh = {
  id: string;
  trigger: "manual" | "scheduled";
  state: string;
  started_at: string;
  finished_at: string | null;
};
export type Snapshot = {
  id: string;
  created_at: string;
  kind?: string | null;
  trigger?: string | null;
  headlines?: string[];
  count?: number | null;
};
export type WeeklyReport = {
  title: string;
  filename: string;
  markdown: string;
  count: number;
  start: string;
  end: string;
};
export type View = {
  as_of: string;
  last_refresh?: Refresh | null;
  schedule?: { enabled: boolean; hours: number[]; next: string };
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
    /** Stories first captured in the latest update. */
    new?: number;
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
  /** The signed-in account (absent on snapshots of past briefings). */
  account?: import("../auth").Account;
};
export type Page =
  | "briefing"
  | "discover"
  | "following"
  | "saved"
  | "library"
  | "story";
