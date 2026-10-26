export type ProviderProtocol = "openai-chat";
export type ProviderKind = "deepseek" | "volcengine" | "qwen" | "zhipu" | "siliconflow" | "qianfan" | "hunyuan" | "gemini" | "groq" | "openrouter" | "custom";
export type ModelTask = "analysis" | "report" | "prompt";

export type ProviderCapabilities = {
  contextWindow?: number;
  streaming: boolean;
  reasoning: boolean;
  toolCalling: boolean;
  source: "declared" | "tested";
};

export type ProviderProfile = {
  id: string;
  label: string;
  provider: ProviderKind;
  protocol: ProviderProtocol;
  baseUrl: string;
  model: string;
  capabilities?: ProviderCapabilities;
  verifiedAt?: string;
};

export type StockItem = {
  code: string;
  name: string;
  market: "CN" | "HK" | "US";
  tags: string[];
  position?: number;
  cost?: number;
  priority: "high" | "normal" | "low";
  validation?: {
    status: "pending" | "ready" | "warning";
    coverage?: number;
    historyStart?: string;
    message?: string;
  };
};

export type StockPool = {
  id: string;
  name: string;
  description: string;
  mode: "inference" | "training";
  stocks: StockItem[];
  createdAt: string;
  updatedAt: string;
};

export type FactorMetrics = {
  ic?: number;
  rankIc?: number;
  icir?: number;
  longShortReturn?: number;
  winRate?: number;
  maxDrawdown?: number;
  turnover?: number;
  costAdjustedReturn?: number;
  decayHalfLife?: number;
  missingRate?: number;
  industryExposure?: number;
  sizeExposure?: number;
  regimeStability?: number;
  leakage: "passed" | "warning" | "unknown";
  evaluatedAt: string;
  period: string;
};

export type FactorSelection = {
  id: string;
  enabled: boolean;
  weight: number;
  metrics?: FactorMetrics;
};

export type FactorResearchSummary = {
  correlation: Record<string, Record<string, number | null>>;
  compositeRankIc?: number | null;
  marginalContribution: Record<string, number | null>;
  redundantPairs: Array<{ left: string; right: string; correlation: number }>;
  dataVersion?: string;
  updatedAt: string;
};

export type PromptRevision = {
  version: number;
  system: string;
  user: string;
  outputSchema: string;
  publishedAt: string;
};

export type PromptTemplate = {
  id: string;
  name: string;
  category: "system" | "tx" | "bs" | "factor" | "risk" | "report";
  system: string;
  user: string;
  outputSchema: string;
  version: number;
  status: "draft" | "published";
  assignedProviderId?: string;
  revisions: PromptRevision[];
  updatedAt: string;
};

export type ExecutorProfile = {
  label: string;
  baseUrl: string;
  verifiedAt?: string;
  capabilities?: { inference?: boolean; training?: boolean; backtest?: boolean; customStocks?: boolean; customFactors?: boolean };
};

export type VibeScope = "quote" | "valuation" | "financials" | "news" | "reports";

export type VibeProfile = {
  enabled: boolean;
  baseUrl: string;
  scopes: VibeScope[];
  verifiedAt?: string;
};

export type ExperimentConfig = {
  dateFrom: string;
  dateTo: string;
  labelHorizon: number;
  trainRatio: number;
  validationRatio: number;
  testRatio: number;
  walkForward: boolean;
  feeBps: number;
  slippageBps: number;
  suspensionPolicy: "skip" | "hold";
  models: string[];
};

export type ResearchJob = {
  id: string;
  remoteId?: string;
  mode: "analysis" | "inference" | "training" | "backtest";
  status: "queued" | "running" | "completed" | "failed" | "blocked";
  title: string;
  createdAt: string;
  updatedAt?: string;
  detail: string;
  result?: string;
  progress?: number;
  progressMessage?: string;
  usage?: { promptTokens?: number; completionTokens?: number; totalTokens?: number };
};

export type ResearchWorkspace = {
  schemaVersion: 2;
  name: string;
  stockPools: StockPool[];
  activePoolId: string;
  factors: FactorSelection[];
  factorResearch?: FactorResearchSummary;
  prompts: PromptTemplate[];
  providers: ProviderProfile[];
  taskRouting: Record<ModelTask, string>;
  executor: ExecutorProfile;
  vibe: VibeProfile;
  experiment: ExperimentConfig;
  jobs: ResearchJob[];
  updatedAt: string;
};

export type FactorDefinition = {
  id: string;
  label: string;
  group: string;
  engines: string;
  advantage: string;
  limitation: string;
  dataNeed: string;
};

export type ProviderPreset = Omit<ProviderProfile, "id">;

export const PROVIDER_PRESETS: ProviderPreset[] = [
  { label: "DeepSeek", provider: "deepseek", protocol: "openai-chat", baseUrl: "https://api.deepseek.com/chat/completions", model: "deepseek-v4-pro", capabilities: { contextWindow: 128000, streaming: true, reasoning: true, toolCalling: true, source: "declared" } },
  { label: "火山方舟", provider: "volcengine", protocol: "openai-chat", baseUrl: "https://ark.cn-beijing.volces.com/api/v3/chat/completions", model: "", capabilities: { streaming: true, reasoning: true, toolCalling: true, source: "declared" } },
  { label: "阿里云百炼 / 通义", provider: "qwen", protocol: "openai-chat", baseUrl: "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", model: "qwen-plus", capabilities: { streaming: true, reasoning: false, toolCalling: true, source: "declared" } },
  { label: "智谱开放平台", provider: "zhipu", protocol: "openai-chat", baseUrl: "https://open.bigmodel.cn/api/paas/v4/chat/completions", model: "glm-4-plus", capabilities: { streaming: true, reasoning: false, toolCalling: true, source: "declared" } },
  { label: "硅基流动", provider: "siliconflow", protocol: "openai-chat", baseUrl: "https://api.siliconflow.cn/v1/chat/completions", model: "", capabilities: { streaming: true, reasoning: true, toolCalling: true, source: "declared" } },
  { label: "百度智能云千帆", provider: "qianfan", protocol: "openai-chat", baseUrl: "https://qianfan.baidubce.com/v2/chat/completions", model: "", capabilities: { streaming: true, reasoning: false, toolCalling: true, source: "declared" } },
  { label: "腾讯混元", provider: "hunyuan", protocol: "openai-chat", baseUrl: "https://api.hunyuan.cloud.tencent.com/v1/chat/completions", model: "", capabilities: { streaming: true, reasoning: false, toolCalling: false, source: "declared" } },
  { label: "Google Gemini", provider: "gemini", protocol: "openai-chat", baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", model: "", capabilities: { streaming: true, reasoning: true, toolCalling: true, source: "declared" } },
  { label: "Groq", provider: "groq", protocol: "openai-chat", baseUrl: "https://api.groq.com/openai/v1/chat/completions", model: "", capabilities: { streaming: true, reasoning: true, toolCalling: true, source: "declared" } },
  { label: "OpenRouter", provider: "openrouter", protocol: "openai-chat", baseUrl: "https://openrouter.ai/api/v1/chat/completions", model: "", capabilities: { streaming: true, reasoning: true, toolCalling: true, source: "declared" } },
  { label: "自定义兼容接口", provider: "custom", protocol: "openai-chat", baseUrl: "https://", model: "", capabilities: { streaming: false, reasoning: false, toolCalling: false, source: "declared" } },
];

export const FACTOR_CATALOG: FactorDefinition[] = [
  { id: "Relative_Strength_20", label: "20日相对强弱", group: "动量", engines: "TX / BS", advantage: "剔除大盘方向后识别个股超额趋势", limitation: "震荡反转阶段容易失效", dataNeed: "复权收盘价 + 市场指数" },
  { id: "MACD_Hist_Norm", label: "标准化 MACD 柱", group: "趋势", engines: "TX / BS", advantage: "跨价格区间可比较，适合捕捉趋势加速度", limitation: "本质滞后，拐点确认较慢", dataNeed: "复权收盘价" },
  { id: "Z_Score_20", label: "20日价格 Z-Score", group: "位置", engines: "TX / BS", advantage: "清晰衡量价格偏离短期中枢的程度", limitation: "强趋势中极值会持续钝化", dataNeed: "复权收盘价" },
  { id: "ATR_Ratio_14_60", label: "短长波动率比", group: "风险", engines: "TX / BS", advantage: "识别波动率扩张与风险状态切换", limitation: "不能独立判断方向", dataNeed: "高低收价格" },
  { id: "Return_5", label: "5日收益", group: "动量", engines: "TX / BS", advantage: "反应快，适合短周期事件和趋势", limitation: "噪声和换手率较高", dataNeed: "复权收盘价" },
  { id: "Return_20", label: "20日收益", group: "动量", engines: "TX / BS", advantage: "比短动量稳定，方向解释直观", limitation: "对突发反转反应较慢", dataNeed: "复权收盘价" },
  { id: "Price_EMA_Bias_20", label: "20日 EMA 偏离", group: "趋势", engines: "TX", advantage: "平滑刻画趋势位置，减少单日噪声", limitation: "极端行情可能高位追涨", dataNeed: "复权收盘价" },
  { id: "Williams_R_14", label: "Williams %R", group: "反转", engines: "TX", advantage: "定位短线超买超卖区域", limitation: "趋势行情中容易过早逆势", dataNeed: "高低收价格" },
  { id: "CCI_14", label: "CCI 顺势指标", group: "趋势", engines: "TX", advantage: "同时利用高低收价格定位趋势偏离", limitation: "对窗口长度敏感", dataNeed: "高低收价格" },
  { id: "Candle_Shape", label: "K线下影强度", group: "行为", engines: "TX", advantage: "捕捉日内承接与反转形态", limitation: "单日形态稳定性有限", dataNeed: "高低开收价格" },
  { id: "Vol_Surge_60", label: "60日量能放大", group: "流动性", engines: "BS", advantage: "识别资金参与度和事件放量", limitation: "异常成交会制造尖峰", dataNeed: "成交量" },
  { id: "Price_VWAP_Bias", label: "VWAP 价格偏离", group: "资金", engines: "BS", advantage: "衡量价格相对成交成本中枢的位置", limitation: "成交额口径变化会影响可比性", dataNeed: "成交量 + 成交额" },
  { id: "MFI_14", label: "资金流量指标", group: "资金", engines: "BS", advantage: "融合价格和成交量判断资金强弱", limitation: "低流动性股票容易失真", dataNeed: "高低收 + 成交量" },
  { id: "Amihud_Illiquidity", label: "Amihud 非流动性", group: "流动性", engines: "BS", advantage: "量化价格冲击与流动性风险", limitation: "极小成交额会放大异常值", dataNeed: "涨跌幅 + 成交额" },
];

const now = "2026-07-14T00:00:00.000Z";

function defaultPrompt(id: string, name: string, category: PromptTemplate["category"], system: string, user: string): PromptTemplate {
  return { id, name, category, system, user, outputSchema: "", version: 1, status: "published", revisions: [{ version: 1, system, user, outputSchema: "", publishedAt: now }], updatedAt: now };
}

export function createDefaultWorkspace(): ResearchWorkspace {
  const providers: ProviderProfile[] = PROVIDER_PRESETS.slice(0, 2).map((provider) => ({ ...provider, id: provider.provider }));
  return {
    schemaVersion: 2,
    name: "我的双轨研究工作区",
    stockPools: [{
      id: "my-first-pool",
      name: "我的第一个股票池",
      description: "这是空白个人股票池，请输入自己的股票代码后开始研究",
      mode: "inference",
      stocks: [],
      createdAt: now,
      updatedAt: now,
    }],
    activePoolId: "my-first-pool",
    factors: FACTOR_CATALOG.map((factor, index) => ({ id: factor.id, enabled: index < 6, weight: index < 6 ? [20, 18, 16, 16, 15, 15][index] : 0 })),
    prompts: [
      defaultPrompt("dual-rail-analysis", "双轨研究报告", "report", "你是严谨的量化研究助手。只基于输入的数据和因子配置得出结论；信息不足时明确指出，不得捏造实时行情、财务数据或回测指标。输出包含共识、分歧、风险和待验证事项。", "请分析股票池 {{stocks}}。当前选用因子为 {{factors}}。研究目标：{{objective}}。请区分可由数据支持的结论与模型推断。"),
      defaultPrompt("factor-audit", "因子组合审计", "factor", "你是量化模型审计员。检查因子冗余、方向冲突、数据要求、换手成本和潜在未来函数。没有实证结果时不得给出虚构 IC 或收益率。", "审计以下因子组合：{{factors}}。适用股票池：{{stocks}}。给出新增价值、冗余程度、适用行情、风险点和上线前检查清单。"),
      defaultPrompt("risk-review", "风险审查", "risk", "你是独立风险审查员。优先识别数据泄漏、过拟合、交易成本、市场状态漂移与无法验证的结论。", "审查 {{stocks}} 的研究结果，因子为 {{factors}}。目标：{{objective}}。"),
    ],
    providers,
    taskRouting: { analysis: "deepseek", report: "deepseek", prompt: "deepseek" },
    executor: { label: "TX / BS 研究执行器", baseUrl: "" },
    vibe: { enabled: false, baseUrl: "", scopes: ["quote", "valuation", "financials"] },
    experiment: { dateFrom: "2021-01-01", dateTo: "2026-07-14", labelHorizon: 20, trainRatio: 70, validationRatio: 15, testRatio: 15, walkForward: true, feeBps: 8, slippageBps: 5, suspensionPolicy: "hold", models: ["TX", "BS"] },
    jobs: [],
    updatedAt: now,
  };
}

function normalizeStock(value: unknown): StockItem | null {
  if (!value || typeof value !== "object") return null;
  const stock = value as Partial<StockItem>;
  const code = typeof stock.code === "string" ? stock.code.trim().toUpperCase().slice(0, 12) : "";
  const market = stock.market === "HK" || stock.market === "US" ? stock.market : "CN";
  if (!code) return null;
  return { code, market, name: typeof stock.name === "string" ? stock.name.slice(0, 40) : "", tags: Array.isArray(stock.tags) ? stock.tags.map(String).slice(0, 8) : [], position: typeof stock.position === "number" ? stock.position : undefined, cost: typeof stock.cost === "number" ? stock.cost : undefined, priority: stock.priority === "high" || stock.priority === "low" ? stock.priority : "normal", validation: stock.validation };
}

function normalizePrompt(value: unknown, index: number): PromptTemplate | null {
  if (!value || typeof value !== "object") return null;
  const prompt = value as Partial<PromptTemplate>;
  if (typeof prompt.name !== "string") return null;
  const system = typeof prompt.system === "string" ? prompt.system.slice(0, 12000) : "";
  const user = typeof prompt.user === "string" ? prompt.user.slice(0, 12000) : "";
  const outputSchema = typeof prompt.outputSchema === "string" ? prompt.outputSchema.slice(0, 12000) : "";
  const version = typeof prompt.version === "number" && prompt.version > 0 ? Math.floor(prompt.version) : 1;
  const revisions = Array.isArray(prompt.revisions) ? prompt.revisions.slice(-20) : [{ version, system, user, outputSchema, publishedAt: prompt.updatedAt ?? now }];
  return { id: typeof prompt.id === "string" ? prompt.id : `prompt-${index}`, name: prompt.name.slice(0, 80), category: ["system", "tx", "bs", "factor", "risk", "report"].includes(String(prompt.category)) ? prompt.category as PromptTemplate["category"] : "report", system, user, outputSchema, version, status: prompt.status === "draft" ? "draft" : "published", assignedProviderId: prompt.assignedProviderId, revisions, updatedAt: typeof prompt.updatedAt === "string" ? prompt.updatedAt : now };
}

export function normalizeWorkspace(value: unknown): ResearchWorkspace {
  const fallback = createDefaultWorkspace();
  if (!value || typeof value !== "object") return fallback;
  const item = value as Partial<ResearchWorkspace> & { stocks?: unknown[] };
  let stockPools: StockPool[] = [];
  if (Array.isArray(item.stockPools)) {
    stockPools = item.stockPools.slice(0, 20).map((pool, index) => {
      const candidate = pool as Partial<StockPool>;
      return { id: typeof candidate.id === "string" ? candidate.id : `pool-${index}`, name: typeof candidate.name === "string" ? candidate.name.slice(0, 60) : `股票池 ${index + 1}`, description: typeof candidate.description === "string" ? candidate.description.slice(0, 200) : "", mode: candidate.mode === "training" ? "training" : "inference", stocks: Array.isArray(candidate.stocks) ? candidate.stocks.map(normalizeStock).filter((stock): stock is StockItem => Boolean(stock)).slice(0, 500) : [], createdAt: candidate.createdAt ?? now, updatedAt: candidate.updatedAt ?? now };
    });
  } else if (Array.isArray(item.stocks)) {
    stockPools = [{ ...fallback.stockPools[0], stocks: item.stocks.map(normalizeStock).filter((stock): stock is StockItem => Boolean(stock)).slice(0, 500) }];
  }
  if (!stockPools.length) stockPools = fallback.stockPools;

  const providedFactors = Array.isArray(item.factors) ? item.factors : [];
  const factors = FACTOR_CATALOG.map((definition) => {
    const found = providedFactors.find((candidate) => candidate && typeof candidate === "object" && (candidate as FactorSelection).id === definition.id) as FactorSelection | undefined;
    return found ? { id: definition.id, enabled: Boolean(found.enabled), weight: Math.max(0, Math.min(100, Number(found.weight) || 0)), metrics: found.metrics } : { id: definition.id, enabled: false, weight: 0 };
  });
  const providers = Array.isArray(item.providers) ? item.providers.filter((provider): provider is ProviderProfile => Boolean(provider && typeof provider === "object" && typeof (provider as ProviderProfile).id === "string")).slice(0, 20) : fallback.providers;
  const prompts = Array.isArray(item.prompts) ? item.prompts.map(normalizePrompt).filter((prompt): prompt is PromptTemplate => Boolean(prompt)).slice(0, 50) : fallback.prompts;
  const activePoolId = stockPools.some((pool) => pool.id === item.activePoolId) ? String(item.activePoolId) : stockPools[0].id;
  const routing = item.taskRouting ?? fallback.taskRouting;
  const firstProvider = providers[0]?.id ?? "";
  return {
    schemaVersion: 2,
    name: typeof item.name === "string" && item.name.trim() ? item.name.slice(0, 80) : fallback.name,
    stockPools,
    activePoolId,
    factors,
    factorResearch: item.factorResearch && typeof item.factorResearch === "object" ? item.factorResearch : undefined,
    prompts: prompts.length ? prompts : fallback.prompts,
    providers,
    taskRouting: { analysis: routing.analysis || firstProvider, report: routing.report || firstProvider, prompt: routing.prompt || firstProvider },
    executor: item.executor && typeof item.executor === "object" ? item.executor : fallback.executor,
    vibe: item.vibe && typeof item.vibe === "object" ? {
      enabled: Boolean(item.vibe.enabled),
      baseUrl: typeof item.vibe.baseUrl === "string" ? item.vibe.baseUrl.slice(0, 500) : "",
      scopes: Array.isArray(item.vibe.scopes) ? item.vibe.scopes.filter((scope): scope is VibeScope => ["quote", "valuation", "financials", "news", "reports"].includes(String(scope))).slice(0, 5) : fallback.vibe.scopes,
      verifiedAt: typeof item.vibe.verifiedAt === "string" ? item.vibe.verifiedAt : undefined,
    } : fallback.vibe,
    experiment: item.experiment && typeof item.experiment === "object" ? { ...fallback.experiment, ...item.experiment } : fallback.experiment,
    jobs: Array.isArray(item.jobs) ? item.jobs.slice(0, 50) : [],
    updatedAt: typeof item.updatedAt === "string" ? item.updatedAt : new Date().toISOString(),
  };
}

export function getActivePool(workspace: ResearchWorkspace): StockPool {
  return workspace.stockPools.find((pool) => pool.id === workspace.activePoolId) ?? workspace.stockPools[0];
}
