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
  /** IANA timezone for shown dates; empty follows the site timezone. */
  timezone?: string;
  /** Companies in the sidebar, in order; null or absent: the four most active. */
  drawer_companies?: string[] | null;
};
export type Claim = { statement: string; quote: string; kind: string };
export type Action = { request_id: string; kind: string; at: string; version: string };
export type Entry = {
  content_kind?: string;
  version: string;
  title: string;
  summary: string;
  source: string;
  source_id?: string;
  role: string;
  url: string;
  published_at: string | null;
  captured_at?: string;
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
  /** In an earlier briefing's focus or radar, seen there and not opened, with no news since. */
  carried?: boolean;
  /** Found while it was news. Late finds and undated reports are archived, not "today". */
  timely?: boolean;
  stale_reason?: "late" | "undated" | null;
  /** Independent outlets reporting within 48 h, each once, halving daily. */
  heat?: number;
  heat_trend?: "rising" | null;
  /** Rule-written line on where the evidence comes from (who states it, who tested, sources). */
  standing?: string;
  /** Companies that act in this story; official: one of its reports is the company's own. */
  companies?: { id: string; official: boolean; products: string[] }[];
  /** Companies only mentioned (a customer, a lawsuit, someone else's test). */
  mentions?: string[];
  lenses?: ("company" | "community" | "research" | "policy")[];
  first_captured_at?: string;
  latest_captured_at?: string;
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
  /** zone: what this reader sees dates in; site: schedule, quotas and digest dates. */
  timezone?: { zone: string; site: string; options: { id: string; label: string }[] };
  last_visit?: string | null;
  /** When the reader last came before this sitting (visits under 30 minutes apart are one). */
  previous_visit?: string | null;
  /** GitHub rankings from the latest update (open source and community). */
  rankings?: Ranking[];
  /** The editable company table: companies and their product groups, in display order. */
  companies?: { id: string; name: string; products: { id: string; name: string }[] }[];
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
  | "trends"
  | "discover"
  | "following"
  | "saved"
  | "library"
  | "story";
export type RepoRow = {
  name: string;
  url: string;
  description: string;
  /** One Chinese sentence the model wrote from the description; absent without a model. */
  summary_zh?: string;
  language: string;
  stars: number;
  forks: number;
  /** Stars gained in the Trending period; null on search lists. */
  gained: number | null;
  created_at?: string | null;
  topics: string[];
  /** "collection": a list or tutorial collection; "few_forks": stars far ahead of forks. */
  flags: string[];
};
export type Ranking = {
  id: string;
  name: string;
  kind: string;
  url: string;
  description: string;
  status?: string;
  error?: string | null;
  /** When this list was fetched; it stays shown, with this time, if a later fetch fails. */
  at?: string | null;
  rows: RepoRow[];
};
