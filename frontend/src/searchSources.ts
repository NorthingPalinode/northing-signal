export type SearchSource =
  | "web"
  | "arxiv"
  | "github"
  | "huggingface"
  | "openalex"
  | "hackernews"
  | "x"
  | "douyin"
  | "xiaohongshu";
export const searchSources: Record<SearchSource, string> = {
  web: "网页搜索",
  arxiv: "arXiv",
  github: "GitHub",
  huggingface: "Hugging Face",
  openalex: "OpenAlex",
  hackernews: "Hacker News",
  x: "X / Twitter",
  douyin: "抖音",
  xiaohongshu: "小红书",
};
export const sourceName = (source: string) =>
  searchSources[source as SearchSource] || source;
