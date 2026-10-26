"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  PROVIDER_PRESETS,
  normalizeWorkspace,
  type ProviderKind,
  type ProviderProfile,
  type ResearchWorkspace,
  type StockItem,
} from "../../lib/workspace";
import styles from "./LocalWorkbench.module.css";

type View = "market" | "desk" | "research" | "reference";
type ResearchTab = "signals" | "dual" | "factors" | "backtest" | "models";
type Quote = {
  code: string;
  name: string;
  market: string;
  assetType: string;
  original?: boolean;
  price: number | null;
  changePercent: number | null;
  marketTime?: string;
  currency?: string;
  turnoverAmount?: number | null;
  delayLabel?: string | null;
};
type DimensionDetail = {
  heat?: number | null;
  coverage?: number;
  autoDone?: number;
  autoTotal?: number;
  manualDone?: number;
  manualTotal?: number;
  missing?: string[];
  indicators?: {
    key: string;
    name: string;
    value?: number | null;
    heat?: number | null;
    weight: number;
    manual: boolean;
    source?: string | null;
    available: boolean;
  }[];
};
type MarketStats = {
  total?: number | null;
  up?: number | null;
  down?: number | null;
  flat?: number | null;
  advancingRatio?: number | null;
  limitUp?: number | null;
  limitDown?: number | null;
  limitUpEstimate?: number | null;
  limitDownEstimate?: number | null;
  brokenLimit?: number | null;
  sealRate?: number | null;
  limitMethod?: string;
  preciseCommercialPoolAvailable?: boolean;
};
type Dashboard = {
  schemaVersion: string;
  system: { name: string; portfolioMode: string; timezone: string };
  market: {
    indices: Quote[];
    temperature: {
      score?: number | null;
      raw?: number | null;
      state?: string;
      coverage?: number;
      formula?: string;
      components?: Record<string, number | null>;
    };
    breadth?: number | null;
    marketStats?: {
      data?: MarketStats;
      meta?: { source?: string; freshness?: string };
      cacheState?: string;
    };
    trend?: { score?: number | null; state?: string; timeframe?: string };
    technical?: Record<string, unknown>[];
    valuation?: {
      data?: Record<string, unknown>[];
      alerts?: {
        high?: Record<string, unknown>[];
        low?: Record<string, unknown>[];
      };
    };
    sixDimensions?: {
      name: string;
      value?: number | null;
      signal: string;
      summary: string;
    }[];
    topObserver: {
      score: number | null;
      coverage: number;
      note: string;
      conclusionLabel?: string;
      dangerCount?: number;
      dimensions?: Record<string, number | null>;
      dimensionDetails?: Record<string, DimensionDetail>;
    };
  };
  watchlist: Quote[];
  universe: Quote[];
  portfolio: { enabled: boolean; mode: string; items: unknown[] };
  extensions: {
    vibe: { enabled: boolean; mode: string };
    dualTrack: { enabled: boolean; frequency: string };
  };
  dataStatus: {
    quotes?: {
      source?: string;
      fetched_at?: string;
      market_time?: string;
      freshness?: string;
    };
    cacheState?: string;
    analysisCacheState?: string;
    dashboardCacheState?: string;
    bundleFingerprint?: string;
    builtAt?: string;
    clock?: {
      nextRefreshSeconds?: number;
      cn?: { state?: string };
      calendarConfidence?: string;
      calendarNote?: string;
    };
  };
};
type WorkspaceEnvelope = {
  workspace?: ResearchWorkspace;
  viewer?: { name?: string };
};
type KlineRow = {
  date: string;
  open: number;
  close: number;
  high: number;
  low: number;
  volume: number;
};
type KlinePackage = {
  data: KlineRow[];
  indicators?: {
    ma5?: (number | null)[];
    ma10?: (number | null)[];
    ma20?: (number | null)[];
    ma60?: (number | null)[];
    macd?: { dif: number[]; dea: number[]; histogram: number[] };
  };
  meta?: { source?: string; market_time?: string };
  cacheState?: string;
};
type IntradayPackage = {
  data: { time: string; price: number; volume?: number }[];
  average?: number[];
  meta?: { source?: string; market_time?: string };
  cacheState?: string;
};

const originalUniverse = [
  ["300308", "中际旭创"],
  ["300502", "新易盛"],
  ["300857", "协创数据"],
  ["688008", "澜起科技"],
  ["688257", "新锐股份"],
  ["688313", "仕佳光子"],
  ["301297", "富乐德"],
  ["600522", "中天科技"],
  ["002335", "科华数据"],
  ["000657", "中钨高新"],
  ["601899", "紫金矿业"],
] as const;
const navigation: { id: View; en: string; zh: string; mark: string }[] = [
  { id: "market", en: "MARKET", zh: "市场", mark: "01" },
  { id: "desk", en: "MY DESK", zh: "我的", mark: "02" },
  { id: "research", en: "RESEARCH", zh: "研究", mark: "03" },
  { id: "reference", en: "REFERENCE", zh: "资料", mark: "04" },
];
const researchTabs: { id: ResearchTab; label: string; note: string }[] = [
  { id: "signals", label: "市场研判", note: "趋势与条件" },
  {
    id: "dual",
    label: "个人因子组合",
    note: "腾讯财经趋势 / BaoStock量价",
  },
  { id: "factors", label: "因子实验室", note: "设计与分析" },
  { id: "backtest", label: "训练回测", note: "真实实验" },
  { id: "models", label: "模型与报告", note: "版本归档" },
];
const API_BASE =
  process.env.NEXT_PUBLIC_RESEARCH_API_URL?.trim().replace(/\/$/, "") ?? "";
const DASHBOARD_LKG_KEY = "motto-dashboard-lkg-v3";

type IconName =
  | "market"
  | "desk"
  | "research"
  | "reference"
  | "menu"
  | "settings"
  | "refresh"
  | "close"
  | "chevron"
  | "search"
  | "bell"
  | "chart"
  | "filter"
  | "clock"
  | "database"
  | "shield"
  | "expand";
const iconPaths: Record<IconName, string[]> = {
  market: ["M4 19V9m5 10V5m5 14v-7m5 7V3"],
  desk: ["M4 5h16v14H4z", "M8 9h8M8 13h5"],
  research: ["M5 19l4-5 4 2 6-9", "M5 5v14h14"],
  reference: ["M6 3h9l3 3v15H6z", "M9 10h6m-6 4h6"],
  menu: ["M4 7h16M4 12h16M4 17h16"],
  settings: [
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8",
    "M4 12h2m12 0h2M12 4v2m0 12v2",
  ],
  refresh: ["M19 7v5h-5", "M18 12a6 6 0 1 0-2 4.5"],
  close: ["M6 6l12 12M18 6 6 18"],
  chevron: ["m9 6 6 6-6 6"],
  search: ["M11 18a7 7 0 1 1 0-14 7 7 0 0 1 0 14m5-2 4 4"],
  bell: ["M6 16h12l-2-3V9a4 4 0 0 0-8 0v4z", "M10 20h4"],
  chart: ["M4 18l5-6 4 3 7-9"],
  filter: ["M4 5h16l-6 7v6l-4 2v-8z"],
  clock: ["M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16", "M12 8v5l3 2"],
  database: [
    "M5 6c0-2 14-2 14 0s-14 2-14 0",
    "M5 6v12c0 2 14 2 14 0V6M5 12c0 2 14 2 14 0",
  ],
  shield: ["M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6z"],
  expand: ["M8 4H4v4m12-4h4v4M8 20H4v-4m12 4h4v-4"],
};
function Icon({ name }: { name: IconName }) {
  return (
    <svg
      width="24"
      height="24"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {iconPaths[name].map((path, index) => (
        <path key={index} d={path} />
      ))}
    </svg>
  );
}
function MiniSparkline({
  rows,
  positive,
  id,
}: {
  rows?: IntradayPackage["data"];
  positive: boolean;
  id: string;
}) {
  const values = (rows ?? [])
    .map((row) => row.price)
    .filter(Number.isFinite)
    .slice(-80);
  if (values.length < 2)
    return <span className={styles.sparkEmpty}>分时待载入</span>;
  const low = Math.min(...values),
    high = Math.max(...values),
    span = high - low || 1;
  const points = values
    .map(
      (value, index) =>
        `${(index / (values.length - 1)) * 132},${32 - ((value - low) / span) * 28}`,
    )
    .join(" ");
  const fillPoints = `0,34 ${points} 132,34`;
  const gradientId = `spark-${id.replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <svg
      className={styles.miniSparkline}
      viewBox="0 0 132 34"
      preserveAspectRatio="none"
      aria-label="真实分时缩略图"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop
            offset="0"
            stopColor={positive ? "#ff5c6b" : "#22d3ee"}
            stopOpacity=".28"
          />
          <stop
            offset="1"
            stopColor={positive ? "#ff5c6b" : "#22d3ee"}
            stopOpacity="0"
          />
        </linearGradient>
      </defs>
      <polygon points={fillPoints} fill={`url(#${gradientId})`} />
      <polyline
        points={points}
        fill="none"
        stroke={positive ? "#ff5c6b" : "#22d3ee"}
        strokeWidth="1.8"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function dialPoint(angle: number, radius: number) {
  const radians = (angle * Math.PI) / 180;
  return {
    x: 77 + radius * Math.cos(radians),
    y: 62 + radius * Math.sin(radians),
  };
}

function dialArc(startAngle: number, endAngle: number, radius = 51) {
  const start = dialPoint(startAngle, radius);
  const end = dialPoint(endAngle, radius);
  return `M ${start.x.toFixed(3)} ${start.y.toFixed(3)} A ${radius} ${radius} 0 ${
    endAngle - startAngle > 180 ? 1 : 0
  } 1 ${end.x.toFixed(3)} ${end.y.toFixed(3)}`;
}

function MarketTemperatureDial({
  score,
  coverage,
  state,
}: {
  score: number | null;
  coverage?: number;
  state?: string;
}) {
  const safeScore = Math.max(0, Math.min(100, score ?? 0));
  const pointerAngle = 135 + safeScore * 2.7;
  const pointer = dialPoint(pointerAngle, 51);
  return (
    <div className={styles.pdfDial}>
      <svg
        viewBox="0 0 154 118"
        role="img"
        aria-label={`市场温度 ${score == null ? "数据不足" : `${safeScore.toFixed(0)}分`}`}
      >
        <title>市场强弱 270 度指针盘</title>
        <defs>
          <filter id="dial-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="2.2" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <linearGradient id="dial-weak" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#22d3ee" />
            <stop offset="1" stopColor="#67e8f9" />
          </linearGradient>
          <linearGradient id="dial-flat" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#67e8f9" />
            <stop offset=".52" stopColor="#ffb454" />
            <stop offset="1" stopColor="#ff8f5c" />
          </linearGradient>
          <linearGradient id="dial-bull" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#ff8f5c" />
            <stop offset="1" stopColor="#ff5c6b" />
          </linearGradient>
        </defs>
        <path className={styles.dialBase} d={dialArc(135, 405)} />
        <path className={styles.dialWeak} d={dialArc(135, 228.5)} />
        <path className={styles.dialFlat} d={dialArc(231, 296)} />
        <path className={styles.dialBull} d={dialArc(298.5, 405)} />
        <circle className={styles.dialMarkerGlow} cx={pointer.x} cy={pointer.y} r="6" />
        <circle className={styles.dialMarker} cx={pointer.x} cy={pointer.y} r="3.2" />
        <text className={styles.dialScore} x="77" y="62" textAnchor="middle">
          {score == null ? "—" : safeScore.toFixed(0)}
        </text>
        <text className={styles.dialUnit} x="91" y="61">%</text>
        <text className={styles.dialState} x="77" y="77" textAnchor="middle">{state ?? "数据不足"}</text>
        <text className={styles.dialLabel} x="14" y="110">0 弱势</text>
        <text className={styles.dialLabel} x="140" y="110" textAnchor="end">强势 100</text>
      </svg>
      <small>覆盖 {Math.round((coverage ?? 0) * 100)}%</small>
    </div>
  );
}

function TweenNumber({
  value,
  decimals = 0,
}: {
  value: number | null | undefined;
  decimals?: number;
}) {
  const [shown, setShown] = useState(value ?? 0);
  const shownRef = useRef(value ?? 0);
  useEffect(() => {
    if (typeof value !== "number" || !Number.isFinite(value)) return;
    const start = shownRef.current;
    const started = performance.now();
    let frame = 0;
    const draw = (now: number) => {
      const progress = Math.min(1, (now - started) / 160);
      const eased = 1 - (1 - progress) ** 3;
      const next = start + (value - start) * eased;
      shownRef.current = next;
      setShown(next);
      if (progress < 1) frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return (
    <>
      {typeof value === "number" && Number.isFinite(value)
        ? shown.toFixed(decimals)
        : "—"}
    </>
  );
}

function EvidencePopover({
  title,
  asOf,
  source,
  method,
  note,
}: {
  title: string;
  asOf?: string;
  source?: string;
  method?: string;
  note?: string;
}) {
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        button.current?.focus();
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);
  return (
    <span className={styles.evidenceWrap}>
      <button
        ref={button}
        className={styles.evidenceButton}
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-label={`查看${title}证据`}
      >
        <Icon name="database" />
      </button>
      {open && (
        <span className={styles.evidencePopover} role="dialog">
          <b>{title}</b>
          <small>截至：{asOf || "未提供"}</small>
          <small>来源：{source || "未提供"}</small>
          <small>方法：{method || "原子数据直接计算"}</small>
          <em>{note || "缺失字段保持为空，不用代理值冒充。"}</em>
        </span>
      )}
    </span>
  );
}

function ChartDialog({
  quote,
  query,
  onClose,
  onResearch,
}: {
  quote: Quote | null;
  query: (
    path: string,
    params?: Record<string, string | number>,
    payload?: Record<string, unknown>,
  ) => Promise<unknown>;
  onClose: () => void;
  onResearch: (code: string) => void;
}) {
  const [period, setPeriod] = useState<"minute" | "day" | "week" | "month">(
    "day",
  );
  const [chart, setChart] = useState<KlinePackage | IntradayPackage | null>(
    null,
  );
  const [state, setState] = useState("读取中");
  const layers = { ma5: true, ma10: true, ma20: true, ma60: true, macd: true };
  useEffect(() => {
    if (!quote) return;
    let active = true;
    const job =
      period === "minute"
        ? query("/api/intraday", { code: quote.code })
        : query("/api/kline", { code: quote.code, period, limit: 160 });
    job
      .then((data) => {
        if (!active) return;
        const result = data as KlinePackage | IntradayPackage;
        setChart(result);
        setState(
          `${result.data?.length ?? 0} 条 · ${result.meta?.source ?? "来源未知"}`,
        );
      })
      .catch((error) => {
        if (active) {
          setChart(null);
          setState(error instanceof Error ? error.message : "读取失败");
        }
      });
    return () => {
      active = false;
    };
  }, [period, query, quote]);
  useEffect(() => {
    if (!quote) return;
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose, quote]);
  if (!quote) return null;
  return (
    <div
      className={styles.fullscreenLayer}
      role="dialog"
      aria-modal="true"
      aria-label={`${quote.name}指数深度图`}
    >
      <header>
        <div>
          <span className={styles.eyebrow}>INDEX DEPTH · {quote.code}</span>
          <h2>{quote.name}</h2>
        </div>
        <div>
          <button onClick={() => onResearch(quote.code)}>进入资料页</button>
          <button onClick={onClose} aria-label="关闭">
            <Icon name="close" />
          </button>
        </div>
      </header>
      <div className={styles.fullscreenToolbar}>
        {(["minute", "day", "week", "month"] as const).map((value) => (
          <button
            key={value}
            className={period === value ? styles.chartActive : ""}
            onClick={() => {
              setState("读取中");
              setPeriod(value);
            }}
          >
            {value === "minute"
              ? "分时"
              : value === "day"
                ? "日线"
                : value === "week"
                  ? "周线"
                  : "月线"}
          </button>
        ))}
        <span>{state}</span>
      </div>
      <div className={styles.fullscreenChart}>
        <MarketCanvas
          packageData={chart}
          mode={period === "minute" ? "minute" : "kline"}
          layers={layers}
        />
      </div>
      <footer>鼠标/触控查看十字线 · Esc 返回最新状态</footer>
    </div>
  );
}

function price(value: number | null | undefined, currency = "CNY") {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${currency === "USD" ? "$" : currency === "HKD" ? "HK$" : "¥"}${value.toFixed(2)}`;
}
function change(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "等待行情";
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}
function tone(value: number | null | undefined) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "";
  return value > 0 ? styles.up : value < 0 ? styles.down : "";
}
function sourceMetaTime(dashboard: Dashboard | null) {
  return (
    dashboard?.dataStatus.quotes?.market_time ??
    dashboard?.dataStatus.builtAt ??
    ""
  );
}

function maskApiKey(value: string) {
  if (!value) return "未载入";
  return value.length > 8
    ? `${value.slice(0, 3)}••••${value.slice(-4)}`
    : "••••••••";
}

export function LocalWorkbench() {
  const [view, setView] = useState<View>("market");
  const [researchTab, setResearchTab] = useState<ResearchTab>("signals");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [workspace, setWorkspace] = useState<ResearchWorkspace | null>(null);
  const [viewerName, setViewerName] = useState("MO");
  const [executorBase, setExecutorBase] = useState(API_BASE);
  const [executorKey, setExecutorKey] = useState("");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsPanel, setSettingsPanel] = useState<"data" | "models">(
    "data",
  );
  const [providerKeys, setProviderKeys] = useState<Record<string, string>>({});
  const [presetProvider, setPresetProvider] =
    useState<ProviderKind>("deepseek");
  const [providerTesting, setProviderTesting] = useState("");
  const [providerNotice, setProviderNotice] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [lastRefresh, setLastRefresh] = useState("");
  const [selectedCode, setSelectedCode] = useState("300308");
  const [refreshCountdown, setRefreshCountdown] = useState(0);
  const [navOpen, setNavOpen] = useState(false);
  const [activeScrollSection, setActiveScrollSection] = useState("");
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/api/cloud/workspace", { cache: "no-store" })
      .then((response) => response.json())
      .then((data: WorkspaceEnvelope) => {
        if (data.workspace) {
          const normalized = normalizeWorkspace(data.workspace);
          setWorkspace(normalized);
          const executor = normalized.executor;
          if (!API_BASE && executor?.baseUrl) setExecutorBase(executor.baseUrl);
        }
        if (data.viewer?.name)
          setViewerName(data.viewer.name.slice(0, 2).toUpperCase());
      })
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    if ("serviceWorker" in navigator)
      navigator.serviceWorker.register("/sw.js").catch(() => undefined);
  }, []);
  useEffect(() => {
    queueMicrotask(() => {
      try {
        const raw = window.localStorage.getItem(DASHBOARD_LKG_KEY);
        if (raw) {
          const cached = JSON.parse(raw) as {
            dashboard?: Dashboard;
            savedAt?: string;
          };
          if (cached.dashboard?.schemaVersion) {
            setDashboard(cached.dashboard);
            setLastRefresh(cached.savedAt ?? "");
          }
        }
      } catch {
        /* corrupted device cache is ignored */
      }
    });
  }, []);

  const query = useCallback(
    async (
      path: string,
      params?: Record<string, string | number>,
      payload?: Record<string, unknown>,
    ) => {
      const method = payload ? "POST" : "GET";
      if (API_BASE) {
        const url = new URL(`${API_BASE}${path}`);
        for (const [key, value] of Object.entries(params ?? {}))
          url.searchParams.set(key, String(value));
        const response = await fetch(url, {
          method,
          headers: {
            ...(executorKey ? { Authorization: `Bearer ${executorKey}` } : {}),
            ...(payload ? { "Content-Type": "application/json" } : {}),
          },
          body: payload ? JSON.stringify(payload) : undefined,
          cache: "no-store",
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok)
          throw new Error(
            typeof data.detail === "string"
              ? data.detail
              : `HTTP ${response.status}`,
          );
        return data;
      }
      if (!executorBase)
        throw new Error(
          "尚未连接 本地研究服务；页面不会用示例行情填充空位",
        );
      const response = await fetch("/api/cloud/rich/context", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          baseUrl: executorBase,
          apiKey: executorKey,
          path,
          params,
          method,
          payload,
        }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.ok)
        throw new Error(data.error || "数据读取失败");
      return data.result;
    },
    [executorBase, executorKey],
  );

  const refreshAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = (await query("/api/all")) as Dashboard;
      const savedAt = new Date().toISOString();
      setDashboard(data);
      setLastRefresh(savedAt);
      try {
        window.localStorage.setItem(
          DASHBOARD_LKG_KEY,
          JSON.stringify({ dashboard: data, savedAt }),
        );
      } catch {
        /* live package remains usable when storage quota is unavailable */
      }
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "数据读取失败；已保留本机最后可用完整数据包",
      );
    } finally {
      setLoading(false);
    }
  }, [query]);
  useEffect(() => {
    if (API_BASE || executorBase) queueMicrotask(() => void refreshAll());
  }, [executorBase, refreshAll]);
  useEffect(() => {
    if (!dashboard || (!API_BASE && !executorBase)) return;
    let cancelled = false;
    let timer = 0;
    let ticker = 0;
    const schedule = () => {
      const delay = Math.max(
        5,
        dashboard.dataStatus.clock?.nextRefreshSeconds ?? 15,
      );
      setRefreshCountdown(delay);
      ticker = window.setInterval(
        () => setRefreshCountdown((value) => Math.max(0, value - 1)),
        1000,
      );
      timer = window.setTimeout(async () => {
        window.clearInterval(ticker);
        try {
          const patch = (await query("/api/realtime")) as {
            data?: Quote[];
            meta?: Dashboard["dataStatus"]["quotes"];
            cacheState?: string;
            marketStats?: {
              data?: MarketStats;
              meta?: { source?: string; freshness?: string };
              cacheState?: string;
            };
            clock?: Dashboard["dataStatus"]["clock"];
          };
          const rows = patch.data;
          if (!rows || cancelled) return;
          setDashboard((current) =>
            current
              ? {
                  ...current,
                  universe: rows,
                  watchlist: rows.filter((item) => item.original),
                  market: {
                    ...current.market,
                    indices: rows.filter((item) => item.assetType === "index"),
                    marketStats:
                      patch.marketStats ?? current.market.marketStats,
                  },
                  dataStatus: {
                    ...current.dataStatus,
                    quotes: patch.meta,
                    cacheState: patch.cacheState,
                    clock: patch.clock ?? current.dataStatus.clock,
                  },
                }
              : current,
          );
          setLastRefresh(new Date().toISOString());
        } catch {
          /* preserve last-known-good */
        }
        if (!cancelled) schedule();
      }, delay * 1000);
    };
    schedule();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      window.clearInterval(ticker);
    };
  }, [dashboard, executorBase, query]);
  useEffect(() => {
    const root = contentRef.current;
    if (!root || !("IntersectionObserver" in window)) return;
    const nodes = Array.from(
      root.querySelectorAll<HTMLElement>("[data-section]"),
    );
    if (!nodes.length) {
      setActiveScrollSection("");
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible)
          setActiveScrollSection(
            (visible.target as HTMLElement).dataset.section ?? "",
          );
      },
      { rootMargin: "-18% 0px -62% 0px", threshold: [0, 0.25, 0.55] },
    );
    nodes.forEach((node) => observer.observe(node));
    return () => observer.disconnect();
  }, [view, researchTab, dashboard]);

  const quotes = dashboard?.watchlist?.length
    ? dashboard.watchlist
    : originalUniverse.map(([code, name]) => ({
        code,
        name,
        market: "CN",
        assetType: "equity",
        original: true,
        price: null,
        changePercent: null,
      }));
  const personalStockItems = useMemo(() => {
    const active = workspace?.stockPools.find(
      (pool) => pool.id === workspace.activePoolId,
    );
    return active?.stocks ?? [];
  }, [workspace]);
  const personalQuotes = useMemo(
    () =>
      personalStockItems.map((stock) => {
        const live = dashboard?.universe?.find(
          (item) => item.code === stock.code,
        );
        return (
          live ?? {
            code: stock.code,
            name: stock.name || stock.code,
            market: stock.market,
            assetType: "equity",
            price: null,
            changePercent: null,
          }
        );
      }),
    [dashboard, personalStockItems],
  );
  const selectableQuotes = useMemo(() => {
    const rows = [
      ...personalQuotes,
      ...(dashboard?.universe?.length ? dashboard.universe : quotes),
    ];
    return [...new Map(rows.map((item) => [item.code, item])).values()];
  }, [dashboard, personalQuotes, quotes]);
  const selected = useMemo(
    () =>
      selectableQuotes.find((item) => item.code === selectedCode) ??
      selectableQuotes[0],
    [selectableQuotes, selectedCode],
  );
  const sourceMeta = dashboard?.dataStatus.quotes;
  const currentTitle =
    view === "market"
      ? "今日市场全景"
      : view === "desk"
        ? "我的观察桌面"
        : view === "research"
          ? "研究与模型实验室"
          : "市场资料中心";

  function updateProvider(id: string, patch: Partial<ProviderProfile>) {
    setWorkspace((current) =>
      current
        ? {
            ...current,
            providers: current.providers.map((provider) =>
              provider.id === id ? { ...provider, ...patch } : provider,
            ),
            updatedAt: new Date().toISOString(),
          }
        : current,
    );
  }

  function addProvider() {
    const preset = PROVIDER_PRESETS.find(
      (item) => item.provider === presetProvider,
    );
    if (!preset) return;
    const id = `${preset.provider}-${crypto.randomUUID().slice(0, 8)}`;
    setWorkspace((current) =>
      current
        ? {
            ...current,
            providers: [...current.providers, { ...preset, id }],
            taskRouting: {
              ...current.taskRouting,
              analysis: current.taskRouting.analysis || id,
            },
            updatedAt: new Date().toISOString(),
          }
        : current,
    );
    setProviderNotice(`${preset.label} 已加入；填写 Key 后测试连接。`);
  }

  function removeProvider(id: string) {
    setWorkspace((current) => {
      if (!current || current.providers.length <= 1) return current;
      const providers = current.providers.filter((provider) => provider.id !== id);
      const fallback = providers[0]?.id ?? "";
      return {
        ...current,
        providers,
        taskRouting: {
          analysis:
            current.taskRouting.analysis === id
              ? fallback
              : current.taskRouting.analysis,
          report:
            current.taskRouting.report === id
              ? fallback
              : current.taskRouting.report,
          prompt:
            current.taskRouting.prompt === id
              ? fallback
              : current.taskRouting.prompt,
        },
        updatedAt: new Date().toISOString(),
      };
    });
    setProviderKeys((current) => {
      const next = { ...current };
      delete next[id];
      return next;
    });
  }

  async function testProvider(provider: ProviderProfile) {
    setProviderTesting(provider.id);
    setProviderNotice("");
    try {
      const response = await fetch("/api/cloud/provider/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...provider,
          apiKey: providerKeys[provider.id] ?? "",
        }),
      });
      const result = (await response.json().catch(() => ({}))) as Record<
        string,
        unknown
      >;
      if (!response.ok || !result.ok)
        throw new Error(String(result.error ?? "连接测试失败"));
      updateProvider(provider.id, { verifiedAt: new Date().toISOString() });
      setProviderNotice(
        `${provider.label} 连接成功 · ${String(result.latencyMs ?? "—")} ms`,
      );
    } catch (reason) {
      setProviderNotice(
        reason instanceof Error ? reason.message : "连接测试失败",
      );
    } finally {
      setProviderTesting("");
    }
  }

  async function analyzeStockWithProvider(
    code: string,
    providerId: string,
    technical: Record<string, unknown>,
  ) {
    const provider = workspace?.providers.find((item) => item.id === providerId);
    if (!provider) throw new Error("请先在设置 → 模型连接中选择分析模型");
    const apiKey = providerKeys[provider.id] ?? "";
    if (!apiKey) {
      if (provider.provider === "deepseek" || provider.provider === "volcengine")
        return (await query("/api/llm/stock-analysis", undefined, {
          code,
          provider: provider.provider,
        })) as Record<string, unknown>;
      throw new Error(
        `请在设置 → 模型连接中为 ${provider.label} 填写当前会话 API Key`,
      );
    }
    const quote = dashboard?.universe?.find((item) => item.code === code);
    const response = await fetch("/api/cloud/analysis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...provider,
        apiKey,
        system:
          "你是个人投资工作台的证据解释层。只能解释输入的行情与技术条件；信息不足必须直说。禁止捏造新闻、财务、目标价、买卖指令、仓位或收益承诺。按当前结论、支持证据、冲突与风险、后续观察条件、数据边界五段输出。",
        user: JSON.stringify({
          code,
          name: quote?.name,
          quote: {
            price: quote?.price,
            changePercent: quote?.changePercent,
            marketTime: quote?.marketTime,
          },
          technical,
        }),
      }),
    });
    const result = (await response.json().catch(() => ({}))) as Record<
      string,
      unknown
    >;
    if (!response.ok || !result.ok)
      throw new Error(String(result.error ?? "模型分析失败"));
    return {
      analysis: result.report,
      provider: provider.label,
      model: provider.model,
      evidence: { marketTime: quote?.marketTime ?? sourceMetaTime(dashboard) },
      riskNotice: "模型仅解释当前结构化证据，不构成买卖或仓位指令。",
    };
  }

  async function saveConnection() {
    if (!workspace) {
      setError("工作区尚未载入");
      return;
    }
    const next = {
      ...workspace,
      executor: {
        ...workspace.executor,
        label: "本地研究服务",
        baseUrl: executorBase,
      },
      updatedAt: new Date().toISOString(),
    };
    const response = await fetch("/api/cloud/workspace", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace: next }),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      setError(data.error || "保存失败");
      return;
    }
    setWorkspace(next);
    setSettingsOpen(false);
    void refreshAll();
  }

  async function saveResearchWorkspace(next: ResearchWorkspace) {
    const response = await fetch("/api/cloud/workspace", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace: next }),
    });
    const data = (await response.json().catch(() => ({}))) as WorkspaceEnvelope & {
      error?: string;
    };
    if (!response.ok) throw new Error(data.error || "个人工作区保存失败");
    setWorkspace(normalizeWorkspace(data.workspace ?? next));
  }

  return (
    <main className={styles.shell}>
      <aside
        className={`${styles.sidebar} ${navOpen ? styles.sidebarOpen : ""}`}
      >
        <button
          className={styles.brand}
          onClick={() => {
            setView("market");
            setNavOpen(false);
          }}
          aria-label="返回市场总览"
        >
          <span className={styles.brandMark}>研</span>
          <span>
            <b>股票因子工作台</b>
            <small>LOCAL RESEARCH</small>
          </span>
        </button>
        <nav className={styles.nav} aria-label="主导航">
          {navigation.map((item) => (
            <button
              key={item.id}
              className={view === item.id ? styles.active : ""}
              onClick={() => {
                setView(item.id);
                setNavOpen(false);
              }}
              aria-current={view === item.id ? "page" : undefined}
            >
              <i>
                <Icon name={item.id} />
              </i>
              <span>
                <b>{item.en}</b>
                <small>{item.zh}</small>
              </span>
            </button>
          ))}
        </nav>
        <div className={styles.sideStatus}>
          <span>
            <i className={dashboard ? styles.ok : ""} />
            {dashboard ? "核心服务已连接" : "核心服务待连接"}
          </span>
          <small>持仓模式 A · 接口保留</small>
        </div>
      </aside>
      {navOpen && (
        <button
          className={styles.navScrim}
          onClick={() => setNavOpen(false)}
          aria-label="关闭导航"
        />
      )}
      <section className={styles.workspace}>
        <header className={styles.topbar}>
          <button
            className={styles.menuButton}
            onClick={() => setNavOpen(true)}
            aria-label="打开导航"
          >
            <Icon name="menu" />
          </button>
          <div>
            <span className={styles.eyebrow}>
              PERSONAL INVESTMENT WORKSTATION
            </span>
            <h1>{currentTitle}</h1>
          </div>
          <div className={styles.topActions}>
            <span className={styles.dataBadge}>
              <i className={dashboard ? styles.ok : ""} />
              {dashboard
                ? (sourceMeta?.freshness ?? "已连接")
                : "数据链路未连接"}
            </span>
            <button onClick={() => setSettingsOpen(true)}>
              <Icon name="settings" />
              设置
            </button>
            <span className={styles.avatar}>{viewerName || "MO"}</span>
          </div>
        </header>
        <div
          ref={contentRef}
          className={styles.content}
          data-scroll-active={activeScrollSection}
        >
          <section className={styles.statusStrip} aria-label="数据状态">
            <div>
              <span>市场状态</span>
              <b>
                {dashboard?.dataStatus.clock?.cn?.state ??
                  (dashboard ? "数据包可用" : "等待真实数据")}
              </b>
            </div>
            <div>
              <span>行情截至</span>
              <b>{sourceMeta?.market_time || "—"}</b>
            </div>
            <div>
              <span>页面刷新于</span>
              <b>
                {lastRefresh
                  ? new Date(lastRefresh).toLocaleTimeString("zh-CN", {
                      hour12: false,
                    })
                  : "—"}
              </b>
            </div>
            <div>
              <span>来源 / 完整包</span>
              <b title={dashboard?.dataStatus.bundleFingerprint}>
                {sourceMeta?.source
                  ? `${sourceMeta.source} · ${dashboard?.dataStatus.dashboardCacheState ?? dashboard?.dataStatus.cacheState} · ${refreshCountdown}s`
                  : "Rich Core · 未连接"}
              </b>
            </div>
            <button onClick={() => void refreshAll()} disabled={loading}>
              {loading ? (
                <span className={styles.loadingDots} aria-label="正在刷新">
                  <i />
                  <i />
                  <i />
                </span>
              ) : (
                "刷新状态"
              )}
            </button>
          </section>
          {error && (
            <div className={styles.alertBar}>
              <b>数据状态</b>
              <span>{error}</span>
              <button onClick={() => setSettingsOpen(true)}>连接设置</button>
            </div>
          )}
          {view === "market" && (
            <MarketView
              dashboard={dashboard}
              query={query}
              onOpenDesk={() => setView("desk")}
              onSelect={(code) => {
                setSelectedCode(code);
                setView("reference");
              }}
            />
          )}
          {view === "desk" && (
            <DeskViewEnhanced
              quotes={quotes}
              universe={selectableQuotes}
              workspace={workspace}
              query={query}
              llmProviders={workspace?.providers ?? []}
              defaultLlmProvider={workspace?.taskRouting.analysis ?? ""}
              onAnalyze={analyzeStockWithProvider}
              onOpenModelSettings={() => {
                setSettingsPanel("models");
                setSettingsOpen(true);
              }}
              onWorkspaceChange={saveResearchWorkspace}
              onSelect={(code) => {
                setSelectedCode(code);
                setView("reference");
              }}
            />
          )}
          {view === "research" && (
            <ResearchView
              tab={researchTab}
              setTab={setResearchTab}
              query={query}
              selected={selected}
              dashboard={dashboard}
            />
          )}
          {view === "reference" && (
            <ReferenceView
              quotes={selectableQuotes}
              selected={selected}
              selectedCode={selectedCode}
              setSelectedCode={setSelectedCode}
              query={query}
            />
          )}
        </div>
      </section>
      {settingsOpen && (
        <div className={styles.drawerLayer} role="dialog" aria-modal="true">
          <button
            className={styles.scrim}
            onClick={() => setSettingsOpen(false)}
            aria-label="关闭设置"
          />
          <aside className={styles.drawer}>
            <header>
              <div>
                <span className={styles.eyebrow}>CONNECTION CENTER</span>
                <h2>数据与模型连接</h2>
              </div>
              <button
                onClick={() => setSettingsOpen(false)}
                aria-label="关闭设置"
              >
                <Icon name="close" />
              </button>
            </header>
            <nav className={styles.settingsTabs} aria-label="连接设置分类">
              <button
                className={settingsPanel === "data" ? styles.settingsTabActive : ""}
                onClick={() => setSettingsPanel("data")}
              >
                数据核心
              </button>
              <button
                className={settingsPanel === "models" ? styles.settingsTabActive : ""}
                onClick={() => setSettingsPanel("models")}
              >
                模型连接
                <small>{workspace?.providers.length ?? 0}</small>
              </button>
            </nav>
            {settingsPanel === "data" ? (
              <div className={styles.settingsPane}>
                <p>
                  本机版默认连接本地 Research Core；托管页面必须使用经过认证的
                  HTTPS 地址。Bearer Key 只保存在当前页面内存。
                </p>
                <label>
                  <span>研究执行器地址</span>
                  <input
                    value={executorBase}
                    onChange={(event) => setExecutorBase(event.target.value)}
                    placeholder="http://127.0.0.1:8910"
                  />
                </label>
                <label>
                  <span>Research Core Bearer Key · 不保存</span>
                  <input
                    type="password"
                    value={executorKey}
                    onChange={(event) => setExecutorKey(event.target.value)}
                    autoComplete="new-password"
                    placeholder="本机未启用认证时可留空"
                  />
                </label>
                <div className={styles.capabilityRows}>
                  <span>
                    <b>持仓</b>
                    <small>A 模式，接口保留但关闭</small>
                  </span>
                  <span>
                    <b>Vibe-Research</b>
                    <small>默认关闭，可选补充 / 回退 / 对照</small>
                  </span>
                </div>
              </div>
            ) : (
              <div className={styles.settingsPane}>
                <p>
                  可同时配置多个 OpenAI-compatible 模型。连接参数会保存到本人工作区；API
                  Key 只保留在本页内存，刷新后需要重新填写。
                </p>
                <div className={styles.providerAdder}>
                  <select
                    value={presetProvider}
                    onChange={(event) =>
                      setPresetProvider(event.target.value as ProviderKind)
                    }
                  >
                    {PROVIDER_PRESETS.map((preset) => (
                      <option key={preset.provider} value={preset.provider}>
                        {preset.label}
                      </option>
                    ))}
                  </select>
                  <button onClick={addProvider}>添加连接</button>
                </div>
                <div className={styles.modelConnections}>
                  {(workspace?.providers ?? []).map((provider) => (
                    <article key={provider.id}>
                      <header>
                        <span>{provider.provider.slice(0, 3).toUpperCase()}</span>
                        <label>
                          <small>连接名称</small>
                          <input
                            value={provider.label}
                            onChange={(event) =>
                              updateProvider(provider.id, {
                                label: event.target.value,
                              })
                            }
                          />
                        </label>
                        <button
                          onClick={() => removeProvider(provider.id)}
                          disabled={(workspace?.providers.length ?? 0) <= 1}
                          aria-label={`删除${provider.label}`}
                        >
                          删除
                        </button>
                      </header>
                      <label>
                        <span>API Key · 当前会话</span>
                        <input
                          type="password"
                          autoComplete="new-password"
                          value={providerKeys[provider.id] ?? ""}
                          onChange={(event) =>
                            setProviderKeys((current) => ({
                              ...current,
                              [provider.id]: event.target.value,
                            }))
                          }
                          placeholder="输入本人 API Key"
                        />
                        <small>{maskApiKey(providerKeys[provider.id] ?? "")}</small>
                      </label>
                      <label>
                        <span>Base URL</span>
                        <input
                          value={provider.baseUrl}
                          onChange={(event) =>
                            updateProvider(provider.id, {
                              baseUrl: event.target.value,
                            })
                          }
                        />
                      </label>
                      <label>
                        <span>Model / Endpoint ID</span>
                        <input
                          value={provider.model}
                          onChange={(event) =>
                            updateProvider(provider.id, {
                              model: event.target.value,
                            })
                          }
                          placeholder={
                            provider.provider === "volcengine"
                              ? "ep-xxxxxxxx"
                              : "模型名称"
                          }
                        />
                      </label>
                      <footer>
                        <label>
                          <input
                            type="radio"
                            name="analysis-provider"
                            checked={
                              workspace?.taskRouting.analysis === provider.id
                            }
                            onChange={() =>
                              setWorkspace((current) =>
                                current
                                  ? {
                                      ...current,
                                      taskRouting: {
                                        ...current.taskRouting,
                                        analysis: provider.id,
                                      },
                                    }
                                  : current,
                              )
                            }
                          />
                          个股分析默认
                        </label>
                        <button
                          onClick={() => void testProvider(provider)}
                          disabled={providerTesting === provider.id}
                        >
                          {providerTesting === provider.id
                            ? "测试中…"
                            : "测试连接"}
                        </button>
                      </footer>
                    </article>
                  ))}
                </div>
                {providerNotice && (
                  <div className={styles.providerNotice}>{providerNotice}</div>
                )}
                <small className={styles.envFallback}>
                  DeepSeek / 火山方舟未填写会话 Key 时，会继续尝试本机 Research Core
                  的环境变量配置。
                </small>
              </div>
            )}
            <button
              className={styles.primaryButton}
              onClick={() => void saveConnection()}
            >
              保存连接配置
            </button>
            <small className={styles.drawerFootnote}>
              设置 → 模型连接，就是当前 API Key、Base URL 和模型名称的配置入口。
            </small>
          </aside>
        </div>
      )}
    </main>
  );
}

function MarketView({
  dashboard,
  query,
  onOpenDesk,
  onSelect,
}: {
  dashboard: Dashboard | null;
  query: (
    path: string,
    params?: Record<string, string | number>,
    payload?: Record<string, unknown>,
  ) => Promise<unknown>;
  onOpenDesk: () => void;
  onSelect: (code: string) => void;
}) {
  const indices = useMemo(() => dashboard?.market.indices ?? [], [dashboard]);
  const universe = dashboard?.universe ?? [];
  const [intraday, setIntraday] = useState<IntradayPackage | null>(null);
  const [sparklines, setSparklines] = useState<
    Record<string, IntradayPackage["data"]>
  >({});
  const [flows, setFlows] = useState<Record<string, unknown>[]>([]);
  const [flowKind, setFlowKind] = useState<"industry" | "concept" | "etf">(
    "industry",
  );
  const [news, setNews] = useState<Record<string, unknown>[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    top: false,
    flow: false,
    news: false,
  });
  const [depthQuote, setDepthQuote] = useState<Quote | null>(null);
  const [chartCode, setChartCode] = useState("");
  const firstIndex = indices[0]?.code;
  const activeChartCode = chartCode || firstIndex;
  useEffect(() => {
    if (!dashboard || !activeChartCode) return;
    let active = true;
    Promise.allSettled([
      query("/api/intraday", { code: activeChartCode }),
      query("/api/market-flows", { kind: "industry" }),
      query("/api/news", { limit: 30 }),
    ]).then((results) => {
      if (!active) return;
      if (results[0].status === "fulfilled")
        setIntraday(results[0].value as IntradayPackage);
      if (results[1].status === "fulfilled")
        setFlows(
          (results[1].value as { data?: Record<string, unknown>[] }).data ?? [],
        );
      if (results[2].status === "fulfilled")
        setNews(
          (results[2].value as { data?: Record<string, unknown>[] }).data ?? [],
        );
    });
    return () => {
      active = false;
    };
  }, [activeChartCode, dashboard, query]);
  useEffect(() => {
    if (!dashboard || !indices.length) return;
    let active = true;
    Promise.allSettled(
      indices
        .slice(0, 9)
        .map((item) => query("/api/intraday", { code: item.code })),
    ).then((results) => {
      if (!active) return;
      const next: Record<string, IntradayPackage["data"]> = {};
      results.forEach((result, index) => {
        if (result.status === "fulfilled")
          next[indices[index].code] =
            (result.value as IntradayPackage).data ?? [];
      });
      setSparklines(next);
    });
    return () => {
      active = false;
    };
  }, [dashboard, indices, query]);
  async function changeFlowKind(kind: "industry" | "concept" | "etf") {
    setFlowKind(kind);
    if (kind === "etf") return;
    const result = (await query("/api/market-flows", { kind })) as {
      data?: Record<string, unknown>[];
    };
    setFlows(result.data ?? []);
  }
  const temperature = dashboard?.market.temperature;
  const temperatureScore =
    typeof temperature?.score === "number" ? temperature.score : null;
  const sortedChange = [...flows]
    .filter((row) => typeof row.changePercent === "number")
    .sort(
      (left, right) => Number(right.changePercent) - Number(left.changePercent),
    );
  const sortedMoney = [...flows]
    .filter((row) => typeof row.mainNetInflow === "number")
    .sort(
      (left, right) => Number(right.mainNetInflow) - Number(left.mainNetInflow),
    );
  const upSectors = sortedChange.filter(
    (row) => Number(row.changePercent) > 0,
  ).length;
  const downSectors = sortedChange.filter(
    (row) => Number(row.changePercent) < 0,
  ).length;
  const marketAmount = indices
    .filter((row) => ["000001", "399001"].includes(row.code))
    .reduce((sum, row) => sum + (row.turnoverAmount ?? 0), 0);
  const breadth = dashboard?.market.marketStats?.data;
  const observer = dashboard?.market.topObserver;
  const activeChartQuote =
    indices.find((item) => item.code === activeChartCode) ?? indices[0];
  const marketVerdict =
    temperatureScore == null
      ? "数据不足"
      : temperatureScore >= 65
        ? "普涨"
        : temperatureScore >= 50
          ? "偏强"
          : temperatureScore >= 35
            ? "结构分化"
            : "普跌";
  const marketVerdictTone =
    temperatureScore == null
      ? "flat"
      : temperatureScore >= 50
        ? "up"
        : temperatureScore < 35
          ? "down"
          : "flat";
  const portfolioCount = dashboard?.portfolio.items?.length ?? 0;
  const portfolioReady = Boolean(
    dashboard?.portfolio.enabled && portfolioCount > 0,
  );
  const portfolioActionState = portfolioReady
    ? observer?.score != null && observer.score >= 70
      ? "风险升温，收盘复核"
      : temperatureScore != null && temperatureScore < 35
        ? "弱势环境，降低动作频率"
        : "维持计划，等待日线确认"
    : "未接入持仓";
  const portfolioActionNote = portfolioReady
    ? "盘中只触发风险预警；个股加减仓必须在日线收盘后结合 M60、RSI、MACD 与量价重新确认。"
    : "当前为 A 模式空持仓，系统不会把关注清单冒充持仓，也不会生成个股加仓、减仓或卖出建议。";
  const dimensionLabels: Record<string, string> = {
    valuation: "估值",
    sentiment: "情绪换手",
    momentum: "技术动能",
    breadth: "宽度结构",
    volatility: "波动率",
  };
  const etfs = universe.filter((row) => row.assetType === "etf");
  const displayFlows =
    flowKind === "etf"
      ? etfs.map((row) => ({
          code: row.code,
          name: row.name,
          changePercent: row.changePercent,
          mainNetInflow: null,
        }))
      : flows;
  const focusTiles = sortedChange.slice(0, 3).map((item) => ({
    code: String(item.code),
    name: String(item.name),
    market: "CN",
    assetType: "sector",
    price: null,
    changePercent: Number(item.changePercent),
    original: false,
  })) as Quote[];
  const overviewTiles = [...indices.slice(0, 9), ...focusTiles].slice(0, 12);
  const toggle = (key: string) =>
    setExpanded((current) => ({ ...current, [key]: !current[key] }));
  return (
    <div className={styles.marketStory}>
      <section className={styles.openingTitle} data-section="market-temperature">
        <span>01</span>
        <h2>开屏 · 市场涨跌速览</h2>
        <small>指数 &amp; 板块涨跌 · 一眼看清全盘</small>
        <em>{sourceMetaTime(dashboard) || "等待行情时间"}</em>
      </section>
      <section
        className={`${styles.glass} ${styles.marketOverviewHero}`}
        data-tone={marketVerdictTone}
      >
        <div className={styles.heroGaugeBlock}>
          <MarketTemperatureDial
            score={temperatureScore}
            coverage={temperature?.coverage}
            state={temperature?.state}
          />
        </div>
        <div className={styles.heroVerdict}>
          <small>今日盘面结论 · 板块广度 × 主要指数</small>
          <h2 className={tone(temperatureScore == null ? null : temperatureScore - 50)}>
            {marketVerdict}
          </h2>
          <p>
            {typeof breadth?.up === "number"
              ? `参与统计 ${breadth.total ?? "—"} 只 · 上涨 ${breadth.up} / 下跌 ${breadth.down ?? "—"} / 平盘 ${breadth.flat ?? "—"}`
              : "全市场原子行情尚未形成完整宽度，不补造涨跌家数。"}
          </p>
          <div className={styles.breadthRail}>
            <i
              className={styles.breadthUp}
              style={{ width: `${breadth?.advancingRatio ?? 0}%` }}
            />
            <i
              className={styles.breadthDown}
              style={{
                width: `${typeof breadth?.down === "number" && breadth.total ? (breadth.down / breadth.total) * 100 : 0}%`,
              }}
            />
          </div>
          <div className={styles.heroEvidenceLine}>
            <span>
              涨停 {breadth?.limitUp ?? breadth?.limitUpEstimate ?? "—"} ·{" "}
              {breadth?.preciseCommercialPoolAvailable ? "精确池" : "行情估算"}
            </span>
            <span>炸板 {breadth?.brokenLimit ?? "—"}</span>
            <span>封板率 {breadth?.sealRate ?? "—"}%</span>
            <span>板块 {upSectors || "—"}↑ / {downSectors || "—"}↓</span>
          </div>
        </div>
        <div className={styles.heroTurnover}>
          <small>两市成交额 · 实时累计</small>
          <strong>
            {marketAmount ? `${(marketAmount / 1e8).toFixed(2)}万亿` : "—"}
          </strong>
          <span>{temperature?.state ?? "盘面状态待计算"}</span>
          <em>{dashboard?.market.marketStats?.meta?.source ?? "数据源待连接"}</em>
        </div>
        <aside className={styles.portfolioAdvice}>
          <header>
            <span>
              <small>PERSONAL HOLDING ACTION</small>
              <b>个人持仓操作建议</b>
            </span>
            <em>{portfolioReady ? `${portfolioCount} 项` : "MODE A"}</em>
          </header>
          <strong data-ready={portfolioReady}>{portfolioActionState}</strong>
          <p>{portfolioActionNote}</p>
          <footer>
            <span>建议周期 · 日线级</span>
            <button onClick={onOpenDesk}>
              {portfolioReady ? "查看持仓条件" : "前往我的观察"}
            </button>
          </footer>
        </aside>
      </section>
      <section
        className={`${styles.glass} ${styles.indexPanel}`}
        data-section="core-indices"
      >
        <div className={styles.panelTitle}>
          <span>
            <small>CORE INDICES</small>
            <b>宽基 / 行业 / 主题涨跌</b>
          </span>
          <em>{overviewTiles.length} 项</em>
        </div>
        <div className={styles.overviewIndexGrid}>
          {overviewTiles.map((item, index) => (
            <button
              key={`${item.assetType}-${item.code}`}
              className={`${styles.indexTile} ${
                (item.changePercent ?? 0) > 0
                  ? styles.indexTileUp
                  : (item.changePercent ?? 0) < 0
                    ? styles.indexTileDown
                    : styles.indexTileFlat
              } ${index === 0 || index === 6 ? styles.indexGroupStart : ""}`}
              onClick={() =>
                item.assetType === "index" ? setDepthQuote(item) : undefined
              }
              aria-label={
                item.assetType === "index"
                  ? `打开${item.name}全屏指数深度`
                  : `${item.name}重点板块行情锚`
              }
            >
              <span className={styles.indexTileHead}>
                <span>
                  <small>{item.assetType === "index" ? "宽基" : "主题"}</small>
                  <b>{item.name}</b>
                </span>
                <svg viewBox="0 0 12 12" aria-hidden>
                  <path d="M6 2 10 8H2Z" />
                </svg>
              </span>
              <span className={styles.indexTileValue}>
                <strong>
                  {typeof item.price === "number" ? item.price.toFixed(2) : "重点观察"}
                </strong>
                <b>{change(item.changePercent)}</b>
              </span>
              {item.assetType === "index" ? (
                <MiniSparkline
                  id={item.code}
                  rows={sparklines[item.code]}
                  positive={(item.changePercent ?? 0) >= 0}
                />
              ) : (
                <span className={styles.focusTileRail}>
                  <i
                    style={{
                      width: `${Math.min(100, Math.max(8, Math.abs(item.changePercent ?? 0) * 20))}%`,
                    }}
                  />
                </span>
              )}
            </button>
          ))}
        </div>
      </section>
      <section className={styles.marketPrimaryGrid}>
        <article className={`${styles.glass} ${styles.marketChartPanel}`}>
          <div className={styles.panelTitle}>
            <span>
              <small>INTRADAY TIMELINE</small>
              <b>指数分时与技术副图</b>
            </span>
            <em>{intraday?.meta?.market_time ?? "等待分时"}</em>
          </div>
          <div className={styles.chartToolbar}>
            {indices.slice(0, 6).map((item) => (
              <button
                key={item.code}
                className={activeChartCode === item.code ? styles.chartActive : ""}
                onClick={() => setChartCode(item.code)}
              >
                {item.name}
              </button>
            ))}
            <span>分时</span>
          </div>
          <div className={styles.chartHeadline}>
            <span>{activeChartQuote?.name ?? "主要指数"}</span>
            <strong>
              {typeof activeChartQuote?.price === "number"
                ? activeChartQuote.price.toFixed(2)
                : "—"}
            </strong>
            <b className={tone(activeChartQuote?.changePercent)}>
              {change(activeChartQuote?.changePercent)}
            </b>
          </div>
          <div className={styles.chartInset}>
            <MarketCanvas
              packageData={intraday}
              mode="minute"
              layers={{
                ma5: false,
                ma10: false,
                ma20: false,
                ma60: false,
                macd: false,
              }}
            />
          </div>
        </article>
        <article className={`${styles.glass} ${styles.marketLivePanel}`}>
          <div className={styles.panelTitle}>
            <span>
              <small>MARKET LIVE</small>
              <b>今日盘面雷达</b>
            </span>
            <em>{news.length} 条</em>
          </div>
          <div className={styles.liveNewsList}>
            {news.slice(0, 8).map((item, index) => (
              <details key={`${String(item.time)}-${index}`} open={index === 0}>
                <summary>
                  <i />
                  <small>{String(item.time ?? "")}</small>
                  <b>{String(item.title)}</b>
                </summary>
                <p>
                  {String(item.summary ?? "上游未提供摘要，保留标题与时间证据。")}
                </p>
              </details>
            ))}
            {!news.length && <p className={styles.honestEmpty}>新闻上游暂无可用数据</p>}
          </div>
        </article>
      </section>
      <section className={`${styles.glass} ${styles.rankingPanel}`}>
        <div className={styles.panelTitle}>
          <span>
            <small>SECTOR RANKING</small>
            <b>板块领涨 / 领跌与资金验证</b>
          </span>
          <em>Top 10 · 涨跌仅用于涨跌语义</em>
        </div>
        <div className={styles.rankColumns}>
          {[
            ["领涨", sortedChange.slice(0, 10)],
            ["领跌", sortedChange.slice(-10).reverse()],
          ].map(([title, rows]) => (
            <div key={String(title)}>
              <h3>{String(title)}</h3>
              {(rows as Record<string, unknown>[]).map((row, index) => (
                <span key={String(row.code)}>
                  <i>{String(index + 1).padStart(2, "0")}</i>
                  <b>{String(row.name)}</b>
                  <em className={tone(Number(row.changePercent))}>
                    {Number(row.changePercent).toFixed(2)}%
                  </em>
                  <small>
                    <i
                      style={{
                        width: `${Math.max(4, (Math.abs(Number(row.changePercent)) / Math.max(...sortedChange.map((item) => Math.abs(Number(item.changePercent))), 1)) * 100)}%`,
                      }}
                    />
                  </small>
                </span>
              ))}
            </div>
          ))}
        </div>
      </section>
      <article
        className={`${styles.glass} ${styles.topCard}`}
        data-section="top-observer"
      >
        <button
          className={styles.collapsibleTitle}
          onClick={() => toggle("top")}
          aria-expanded={expanded.top}
        >
          <span>
            <small>BULL TOP OBSERVER</small>
            <b>系统性顶部观察</b>
          </span>
          <em>
            {observer?.conclusionLabel ?? "数据不足"} ·{" "}
            {observer ? `${Math.round(observer.coverage * 100)}%` : "—"}
          </em>
          <i className={expanded.top ? styles.chevronOpen : ""}>
            <Icon name="chevron" />
          </i>
        </button>
        <div className={styles.topObserverBody}>
          <div className={styles.topObserverScore}>
            <small>综合热度</small>
            <strong>
              <TweenNumber value={observer?.score} />
            </strong>
            <span>/ 100</span>
          </div>
          <div className={styles.topScale}>
            <header>
              <b>五维加权风险区间</b>
              <em>{observer?.conclusionLabel ?? "数据不足"}</em>
            </header>
            <span>
              <i
                className={styles.scaleMarker}
                style={{ left: `${observer?.score ?? 0}%` }}
              />
              <i className={styles.scaleTick50} />
              <i className={styles.scaleTick70} />
            </span>
            <div className={styles.topScaleLegend}>
              <small>0 安全</small>
              <small>50 警惕</small>
              <small>70 危险</small>
              <small>100</small>
            </div>
          </div>
        </div>
        <p className={styles.topObserverNote}>
          <span>{observer?.dangerCount ?? 0} 个危险维度</span>
          {observer?.note ?? "单一维度极端不会直接形成顶部结论"}
        </p>
        {expanded.top && (
          <div className={styles.dimensionDetails}>
            {Object.entries(observer?.dimensionDetails ?? {}).map(
              ([key, detail]) => (
                <div key={key}>
                  <header>
                    <b>{dimensionLabels[key] ?? key}</b>
                    <em>
                      {detail.heat == null ? "数据不足" : detail.heat.toFixed(1)}
                    </em>
                  </header>
                  <span className={styles.heatBar}>
                    <i style={{ width: `${detail.heat ?? 0}%` }} />
                  </span>
                  <small>
                    自动 {detail.autoDone ?? 0}/{detail.autoTotal ?? 0} · 手动{" "}
                    {detail.manualDone ?? 0}/{detail.manualTotal ?? 0}
                    {detail.missing?.length
                      ? ` · 缺 ${detail.missing.join("、")}`
                      : ""}
                  </small>
                </div>
              ),
            )}
          </div>
        )}
      </article>
      <section className={styles.threeGrid}>
        <article className={styles.glass}>
          <div className={styles.panelTitle}>
            <span>
              <small>GLOBAL SIGNALS</small>
              <b>六维全局信号</b>
            </span>
            <em>{dashboard?.market.trend?.state ?? "数据不足"}</em>
          </div>
          <div className={styles.compactList}>
            {(dashboard?.market.sixDimensions ?? []).map((item) => (
              <div key={item.name}>
                <b>{item.name}</b>
                <span>{item.summary}</span>
                <small>{item.signal}</small>
                <EvidencePopover
                  title={`${item.name}信号`}
                  asOf={sourceMetaTime(dashboard)}
                  source={dashboard?.dataStatus.quotes?.source}
                  method="六维状态归一化"
                  note={item.summary}
                />
              </div>
            ))}
          </div>
        </article>
        <article className={styles.glass}>
          <button
            className={styles.collapsibleTitle}
            onClick={() => toggle("flow")}
            aria-expanded={expanded.flow}
          >
            <span>
              <small>CAPITAL FLOW</small>
              <b>资金代理三榜</b>
            </span>
            <em>{displayFlows.length} 项</em>
            <i className={expanded.flow ? styles.chevronOpen : ""}>
              <Icon name="chevron" />
            </i>
          </button>
          <div className={styles.tabRow}>
            {(["industry", "concept", "etf"] as const).map((kind) => (
              <button
                key={kind}
                className={flowKind === kind ? styles.chartActive : ""}
                onClick={() => void changeFlowKind(kind)}
              >
                {kind === "industry"
                  ? "行业"
                  : kind === "concept"
                    ? "概念"
                    : "ETF"}
              </button>
            ))}
          </div>
          <div className={styles.summaryLine}>
            {flowKind === "etf"
              ? "ETF按行情涨跌观察，不冒充资金净流入"
              : sortedMoney[0]
                ? `净流入居前：${String(sortedMoney[0].name)}`
                : "资金数据不足"}
          </div>
          {expanded.flow && (
            <div className={styles.compactList}>
              {displayFlows.slice(0, 12).map((item) => (
                <div key={String(item.code)}>
                  <b>{String(item.name)}</b>
                  <span>
                    {typeof item.mainNetInflow === "number"
                      ? `${(item.mainNetInflow / 1e8).toFixed(2)} 亿`
                      : "行情代理"}
                  </span>
                  <small>
                    {typeof item.changePercent === "number"
                      ? `${item.changePercent > 0 ? "+" : ""}${item.changePercent.toFixed(2)}%`
                      : "—"}
                  </small>
                </div>
              ))}
            </div>
          )}
        </article>
        <article className={styles.glass}>
          <button
            className={styles.collapsibleTitle}
            onClick={() => toggle("news")}
            aria-expanded={expanded.news}
          >
            <span>
              <small>MARKET NEWS</small>
              <b>7×24 快讯</b>
            </span>
            <em>{news.length} 条</em>
            <i className={expanded.news ? styles.chevronOpen : ""}>
              <Icon name="chevron" />
            </i>
          </button>
          <div className={styles.summaryLine}>
            {news[0] ? String(news[0].title) : "新闻上游暂不可用"}
          </div>
          {expanded.news && (
            <div className={styles.compactList}>
              {news.slice(0, 12).map((item, index) => (
                <details
                  className={styles.newsItem}
                  key={`${String(item.time)}-${index}`}
                >
                  <summary>
                    <b>{String(item.title)}</b>
                    <span>{String(item.time ?? "")}</span>
                  </summary>
                  <small>
                    {Array.isArray(item.tags)
                      ? item.tags.join(" · ")
                      : "未分类"}
                  </small>
                  <p>
                    {String(
                      item.summary ?? "原文摘要未提供；保留标题与来源时间。",
                    )}
                  </p>
                </details>
              ))}
            </div>
          )}
        </article>
      </section>
      <ChartDialog
        quote={depthQuote}
        query={query}
        onClose={() => setDepthQuote(null)}
        onResearch={(code) => {
          setDepthQuote(null);
          onSelect(code);
        }}
      />
    </div>
  );
}

export function MarketViewLegacy({
  dashboard,
  quotes,
  query,
  onSelect,
}: {
  dashboard: Dashboard | null;
  quotes: Quote[];
  query: (
    path: string,
    params?: Record<string, string | number>,
    payload?: Record<string, unknown>,
  ) => Promise<unknown>;
  onSelect: (code: string) => void;
}) {
  const indices =
    dashboard?.market.indices ??
    ["上证指数", "深证成指", "创业板指", "科创50"].map((name, index) => ({
      code: String(index),
      name,
      market: "CN",
      assetType: "index",
      price: null,
      changePercent: null,
    }));
  const [intraday, setIntraday] = useState<IntradayPackage | null>(null);
  const [flows, setFlows] = useState<Record<string, unknown>[]>([]);
  const [news, setNews] = useState<Record<string, unknown>[]>([]);
  const [auxState, setAuxState] = useState("数据不足");
  useEffect(() => {
    if (!dashboard || !indices[0]?.code) return;
    let active = true;
    Promise.allSettled([
      query("/api/intraday", { code: indices[0].code }),
      query("/api/market-flows", { kind: "industry" }),
      query("/api/news", { limit: 12 }),
    ]).then((results) => {
      if (!active) return;
      if (results[0].status === "fulfilled")
        setIntraday(results[0].value as IntradayPackage);
      if (results[1].status === "fulfilled")
        setFlows(
          (
            (results[1].value as { data?: Record<string, unknown>[] }).data ??
            []
          ).slice(0, 8),
        );
      if (results[2].status === "fulfilled")
        setNews(
          (
            (results[2].value as { data?: Record<string, unknown>[] }).data ??
            []
          ).slice(0, 6),
        );
      setAuxState(
        results.some((item) => item.status === "fulfilled")
          ? "按源更新"
          : "上游不可用",
      );
    });
    return () => {
      active = false;
    };
  }, [dashboard, indices, query]);
  const observerDimensions = dashboard?.market.topObserver.dimensions ?? {};
  const observerRows = [
    ["估值", observerDimensions.valuation],
    ["情绪", observerDimensions.sentiment],
    ["动量", observerDimensions.momentum],
    ["宽度", observerDimensions.breadth],
    ["波动", observerDimensions.volatility],
  ] as const;
  // @ts-expect-error Legacy rollback renderer predates the structured temperature payload.
  return (
    <>
      <section className={styles.heroGrid}>
        <article className={`${styles.glass} ${styles.marketPulse}`}>
          <div className={styles.panelTitle}>
            <span>
              <small>MARKET TEMPERATURE</small>
              <b>市场温度</b>
            </span>
            <em>
              {dashboard?.market.topObserver.conclusionLabel ?? "数据不足"}
            </em>
          </div>
          <div className={styles.gauge}>
            <div>
              <strong>{dashboard?.market.temperature ?? "—"}</strong>
              <small>估值 · 情绪 · 技术 · 宽度 · 波动</small>
            </div>
          </div>
          <p>五维覆盖透明；任何单一极端指标都不会直接形成顶部结论。</p>
        </article>
        <article className={`${styles.glass} ${styles.indices}`}>
          <div className={styles.panelTitle}>
            <span>
              <small>CORE INDICES</small>
              <b>主要指数</b>
            </span>
            <em>{indices.length} 项</em>
          </div>
          <div className={styles.indexGrid}>
            {indices.slice(0, 12).map((item) => (
              <div key={item.code}>
                <span>{item.name}</span>
                <strong>{price(item.price)}</strong>
                <small className={tone(item.changePercent)}>
                  {change(item.changePercent)}
                </small>
              </div>
            ))}
          </div>
        </article>
        <article className={`${styles.glass} ${styles.riskCard}`}>
          <div className={styles.panelTitle}>
            <span>
              <small>BULL TOP OBSERVER</small>
              <b>顶部观察</b>
            </span>
            <em>v2</em>
          </div>
          <div className={styles.observerScore}>
            <strong>{dashboard?.market.topObserver.score ?? "—"}</strong>
            <span>
              {dashboard?.market.topObserver.conclusionLabel ?? "数据不足"} ·
              覆盖率{" "}
              {dashboard
                ? `${Math.round((dashboard.market.topObserver.coverage ?? 0) * 100)}%`
                : "—"}
            </span>
          </div>
          <div className={styles.miniBars}>
            {observerRows.map(([name, value]) => (
              <span key={name}>
                <i
                  style={{
                    width: `${typeof value === "number" ? Math.max(2, Math.min(100, value)) : 0}%`,
                  }}
                />
                <small>
                  {name} {typeof value === "number" ? value.toFixed(0) : "—"}
                </small>
              </span>
            ))}
          </div>
          <p>
            {dashboard?.market.topObserver.note ?? "数据不足时不输出顶部判断。"}
          </p>
        </article>
      </section>
      <section className={styles.lowerGrid}>
        <article className={`${styles.glass} ${styles.timeline}`}>
          <div className={styles.panelTitle}>
            <span>
              <small>INTRADAY TIMELINE</small>
              <b>{indices[0]?.name} 分时</b>
            </span>
            <em>{intraday?.meta?.market_time ?? "分时"}</em>
          </div>
          <div className={styles.chartInset}>
            <MarketCanvas
              packageData={intraday}
              mode="minute"
              layers={{
                ma5: false,
                ma10: false,
                ma20: false,
                ma60: false,
                macd: false,
              }}
            />
          </div>
        </article>
        <article className={`${styles.glass} ${styles.watchlist}`}>
          <div className={styles.panelTitle}>
            <span>
              <small>ORIGINAL UNIVERSE</small>
              <b>原有选股</b>
            </span>
            <em>{quotes.length} 只</em>
          </div>
          <div className={styles.stockList}>
            {quotes.slice(0, 7).map((item) => (
              <button key={item.code} onClick={() => onSelect(item.code)}>
                <span>
                  <b>{item.name}</b>
                  <small>
                    {item.code} · {item.market}
                  </small>
                </span>
                <em>
                  <b>{price(item.price, item.currency)}</b>
                  <small className={tone(item.changePercent)}>
                    {change(item.changePercent)}
                  </small>
                </em>
              </button>
            ))}
          </div>
        </article>
      </section>
      <section className={styles.threeGrid}>
        <article className={styles.glass}>
          <div className={styles.panelTitle}>
            <span>
              <small>05 / MARKET</small>
              <b>六维全局信号</b>
            </span>
            <em>{dashboard?.market.trend?.state ?? "数据不足"}</em>
          </div>
          <div className={styles.compactList}>
            {(dashboard?.market.sixDimensions ?? []).map((item) => (
              <div key={item.name}>
                <b>{item.name}</b>
                <span>{item.summary}</span>
                <small>{item.signal}</small>
              </div>
            ))}
          </div>
        </article>
        <article className={styles.glass}>
          <div className={styles.panelTitle}>
            <span>
              <small>06 / MARKET</small>
              <b>行业资金流</b>
            </span>
            <em>{auxState}</em>
          </div>
          <div className={styles.compactList}>
            {flows.map((item) => (
              <div key={String(item.code)}>
                <b>{String(item.name)}</b>
                <span>
                  {typeof item.mainNetInflow === "number"
                    ? `${(item.mainNetInflow / 1e8).toFixed(2)} 亿`
                    : "数据不足"}
                </span>
                <small>
                  {typeof item.changePercent === "number"
                    ? `${item.changePercent > 0 ? "+" : ""}${item.changePercent.toFixed(2)}%`
                    : "—"}
                </small>
              </div>
            ))}
          </div>
        </article>
        <article className={styles.glass}>
          <div className={styles.panelTitle}>
            <span>
              <small>07 / REFERENCE</small>
              <b>7×24 快讯</b>
            </span>
            <em>{auxState}</em>
          </div>
          <div className={styles.compactList}>
            {news.map((item, index) => (
              <div key={`${String(item.time)}-${index}`}>
                <b>{String(item.title)}</b>
                <span>{String(item.time ?? "")}</span>
                <small>
                  {Array.isArray(item.tags) ? item.tags.join(" · ") : ""}
                </small>
              </div>
            ))}
          </div>
        </article>
      </section>
    </>
  );
}

export function DeskView({
  quotes,
  onSelect,
}: {
  quotes: Quote[];
  onSelect: (code: string) => void;
}) {
  return (
    <div className={styles.viewStack}>
      <section className={styles.deskHero}>
        <article className={styles.glass}>
          <span className={styles.eyebrow}>PORTFOLIO MODE A</span>
          <h2>不接入持仓</h2>
          <p>
            不会创建私有持仓文件、展示示例金额或执行基金穿透；接入接口保留，未来可在本人确认后切换。
          </p>
          <span className={styles.goodChip}>空持仓已确认</span>
        </article>
        <article className={styles.glass}>
          <span className={styles.eyebrow}>CONDITION WATCH</span>
          <h2>条件观察</h2>
          <p>
            M60、RSI、MACD、缩量回调与估值区间只展示证据、状态和变化条件，不输出动作金额或比例。
          </p>
          <span className={styles.purpleChip}>状态翻转待数据</span>
        </article>
      </section>
      <section className={`${styles.glass} ${styles.fullTable}`}>
        <div className={styles.panelTitle}>
          <span>
            <small>MY FOCUS</small>
            <b>原有关注清单</b>
          </span>
          <em>{quotes.length} 只</em>
        </div>
        <div className={styles.tableHead}>
          <span>标的</span>
          <span>市场</span>
          <span>实时价</span>
          <span>涨跌</span>
          <span>条件</span>
        </div>
        {quotes.map((item) => (
          <button
            className={styles.tableRow}
            key={item.code}
            onClick={() => onSelect(item.code)}
          >
            <span>
              <b>{item.name}</b>
              <small>{item.code}</small>
            </span>
            <span>{item.market}</span>
            <span>{price(item.price, item.currency)}</span>
            <span className={tone(item.changePercent)}>
              {change(item.changePercent)}
            </span>
            <span>待计算</span>
          </button>
        ))}
      </section>
    </div>
  );
}

function DeskViewEnhanced({
  quotes,
  universe,
  workspace,
  query,
  llmProviders,
  defaultLlmProvider,
  onAnalyze,
  onOpenModelSettings,
  onWorkspaceChange,
  onSelect,
}: {
  quotes: Quote[];
  universe: Quote[];
  workspace: ResearchWorkspace | null;
  query: (
    path: string,
    params?: Record<string, string | number>,
    payload?: Record<string, unknown>,
  ) => Promise<unknown>;
  llmProviders: ProviderProfile[];
  defaultLlmProvider: string;
  onAnalyze: (
    code: string,
    providerId: string,
    technical: Record<string, unknown>,
  ) => Promise<Record<string, unknown>>;
  onOpenModelSettings: () => void;
  onWorkspaceChange: (workspace: ResearchWorkspace) => Promise<void>;
  onSelect: (code: string) => void;
}) {
  const [conditions, setConditions] = useState<
    Record<string, Record<string, unknown>>
  >({});
  const [status, setStatus] = useState("尚未计算");
  const [llmProvider, setLlmProvider] = useState(defaultLlmProvider);
  const [llmAnalyses, setLlmAnalyses] = useState<
    Record<string, Record<string, unknown>>
  >({});
  const [llmLoading, setLlmLoading] = useState("");
  const [stockSearch, setStockSearch] = useState("");
  const [stockSearchResults, setStockSearchResults] = useState<Quote[]>([]);
  const [stockManagerStatus, setStockManagerStatus] = useState("");
  const [stockManagerBusy, setStockManagerBusy] = useState(false);
  const activePool = workspace?.stockPools.find(
    (pool) => pool.id === workspace.activePoolId,
  );
  const personalStocks = activePool?.stocks ?? [];
  const personalQuotes = personalStocks.map((stock) => {
    const live = universe.find((item) => item.code === stock.code);
    return (
      live ?? {
        code: stock.code,
        name: stock.name || stock.code,
        market: stock.market,
        assetType: "equity",
        price: null,
        changePercent: null,
      }
    );
  });
  const analysisQuotes = personalQuotes.length ? personalQuotes : quotes;
  const quoteKey = analysisQuotes.map((item) => item.code).join(",");
  useEffect(() => {
    if (
      defaultLlmProvider &&
      (!llmProvider || !llmProviders.some((item) => item.id === llmProvider))
    )
      setLlmProvider(defaultLlmProvider);
  }, [defaultLlmProvider, llmProvider, llmProviders]);
  async function searchStocks() {
    const needle = stockSearch.trim();
    if (!needle) {
      setStockManagerStatus("请输入股票代码或名称");
      return;
    }
    setStockManagerBusy(true);
    setStockManagerStatus("搜索中");
    try {
      const data = (await query("/api/instruments/search", {
        q: needle,
        limit: 8,
      })) as { data?: Quote[]; meta?: { source?: string; note?: string } };
      setStockSearchResults(data.data ?? []);
      setStockManagerStatus(
        data.data?.length
          ? `找到 ${data.data.length} 项 · ${data.meta?.source ?? "代码目录"}`
          : "没有匹配结果，请核对代码或名称",
      );
    } catch (error) {
      setStockSearchResults([]);
      setStockManagerStatus(
        error instanceof Error ? error.message : "股票搜索失败",
      );
    } finally {
      setStockManagerBusy(false);
    }
  }
  async function commitPersonalStocks(stocks: StockItem[]) {
    if (!workspace || !activePool) throw new Error("个人工作区尚未载入");
    const now = new Date().toISOString();
    const next: ResearchWorkspace = {
      ...workspace,
      stockPools: workspace.stockPools.map((pool) =>
        pool.id === activePool.id ? { ...pool, stocks, updatedAt: now } : pool,
      ),
      updatedAt: now,
    };
    await onWorkspaceChange(next);
  }
  async function addPersonalStock(item: Quote) {
    if (personalStocks.some((stock) => stock.code === item.code)) {
      setStockManagerStatus(`${item.name} 已在个人自选中`);
      return;
    }
    setStockManagerBusy(true);
    try {
      await commitPersonalStocks([
        ...personalStocks,
        {
          code: item.code,
          name: item.name || item.code,
          market:
            item.market === "HK" || item.market === "US" ? item.market : "CN",
          tags: ["个人自选"],
          priority: "normal",
        },
      ]);
      setStockManagerStatus(`已把 ${item.name || item.code} 加入个人自选`);
    } catch (error) {
      setStockManagerStatus(
        error instanceof Error ? error.message : "个人自选保存失败",
      );
    } finally {
      setStockManagerBusy(false);
    }
  }
  async function removePersonalStock(code: string) {
    setStockManagerBusy(true);
    try {
      await commitPersonalStocks(
        personalStocks.filter((stock) => stock.code !== code),
      );
      setStockManagerStatus(`已从个人自选移除 ${code}`);
    } catch (error) {
      setStockManagerStatus(
        error instanceof Error ? error.message : "个人自选保存失败",
      );
    } finally {
      setStockManagerBusy(false);
    }
  }
  async function calculateAll() {
    setStatus("计算中");
    const results = await Promise.allSettled(
      analysisQuotes.map((item) =>
        query("/api/rsi-margin", { code: item.code }),
      ),
    );
    const next: Record<string, Record<string, unknown>> = {};
    results.forEach((result, index) => {
      if (result.status === "fulfilled")
        next[analysisQuotes[index].code] = result.value as Record<
          string,
          unknown
        >;
    });
    setConditions(next);
    setStatus(`已完成 ${Object.keys(next).length}/${analysisQuotes.length}`);
  }
  useEffect(() => {
    if (!quoteKey) return;
    void calculateAll();
    // The code list is stable while realtime quote values refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [quoteKey, query]);
  async function analyzeWithLlm(code: string) {
    setLlmLoading(code);
    try {
      const technical = conditions[code];
      if (!technical) throw new Error("请等待该标的技术条件计算完成");
      if (!llmProvider)
        throw new Error("请先在设置 → 模型连接中配置分析模型");
      const result = await onAnalyze(code, llmProvider, technical);
      setLlmAnalyses((current) => ({ ...current, [code]: result }));
    } catch (error) {
      setLlmAnalyses((current) => ({
        ...current,
        [code]: {
          error: error instanceof Error ? error.message : "LLM 解读失败",
        },
      }));
    } finally {
      setLlmLoading("");
    }
  }
  const fourStates = Object.values(conditions).reduce(
    (summary, record) => {
      const matrix = record.conditions as
        | Record<string, unknown>
        | undefined;
      const verdict = String(matrix?.verdict ?? "").toLowerCase();
      if (
        !verdict ||
        verdict.includes("insufficient") ||
        verdict.includes("数据不足")
      )
        summary.missing += 1;
      else if (
        ["bull", "above", "golden", "积极", "满足"].some((key) =>
          verdict.includes(key),
        )
      )
        summary.positive += 1;
      else if (
        ["bear", "below", "dead", "风险", "转弱"].some((key) =>
          verdict.includes(key),
        )
      )
        summary.negative += 1;
      else summary.watch += 1;
      return summary;
    },
    {
      positive: 0,
      watch: 0,
      negative: 0,
      missing: Math.max(
        0,
        analysisQuotes.length - Object.keys(conditions).length,
      ),
    },
  );
  const observed = fourStates.positive + fourStates.watch + fourStates.negative;
  const tier = !observed
    ? "未分档"
    : fourStates.negative / observed >= 0.5
      ? "风险集中"
      : fourStates.positive / observed >= 0.5
        ? "条件集中"
        : "中性观察";
  return (
    <div className={styles.viewStack}>
      <section className={styles.deskHero}>
        <article className={styles.glass}>
          <span className={styles.eyebrow}>PORTFOLIO MODE A</span>
          <h2>个人自选开放 · 持仓接口保留</h2>
          <p>
            可在下方按代码或名称维护个人自选；当前仍不创建私有持仓文件，也不展示示例金额。
          </p>
          <span className={styles.goodChip}>
            个人自选 {personalStocks.length} 只 · 持仓 0 项
          </span>
        </article>
        <article className={styles.glass}>
          <span className={styles.eyebrow}>CONDITION WATCH</span>
          <h2>关注清单证据分析</h2>
          <p>
            自动计算 M60、RSI、MACD、量价和数据质量，并给出可复核的当前结论。
          </p>
          <button
            className={styles.secondaryButton}
            onClick={() => void calculateAll()}
          >
            计算全部真实条件
          </button>
          <span className={styles.purpleChip}>{status}</span>
        </article>
      </section>
      <section className={`${styles.glass} ${styles.personalStockManager}`}>
        <header>
          <span>
            <small>PERSONAL WATCHLIST &amp; PORTFOLIO GATEWAY</small>
            <b>个人自选与持仓接口</b>
            <em>搜索代码或名称加入个人自选；持仓数量和成本继续受 A 模式保护。</em>
          </span>
          <i>MODE A</i>
        </header>
        <div className={styles.stockSearchBox}>
          <label>
            <Icon name="search" />
            <input
              value={stockSearch}
              onChange={(event) => setStockSearch(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") void searchStocks();
              }}
              placeholder="输入股票代码或名称，例如 600519 / 贵州茅台"
              aria-label="搜索股票代码或名称"
            />
          </label>
          <button
            type="button"
            onClick={() => void searchStocks()}
            disabled={stockManagerBusy}
          >
            {stockManagerBusy ? "处理中…" : "搜索"}
          </button>
          <small>{stockManagerStatus || "支持 A 股、港股和美股代码；名称由腾讯证券搜索目录解析。"}</small>
        </div>
        {stockSearchResults.length > 0 && (
          <div className={styles.stockSearchResults}>
            {stockSearchResults.map((item) => {
              const added = personalStocks.some(
                (stock) => stock.code === item.code,
              );
              return (
                <div key={`${item.market}-${item.code}`}>
                  <span>
                    <b>{item.name || item.code}</b>
                    <small>
                      {item.code} · {item.market}
                    </small>
                  </span>
                  <button
                    type="button"
                    disabled={added || stockManagerBusy || !workspace}
                    onClick={() => void addPersonalStock(item)}
                  >
                    {added ? "已加入" : "加入个人自选"}
                  </button>
                </div>
              );
            })}
          </div>
        )}
        <div className={styles.personalStockBody}>
          <div>
            <small>我的个人自选</small>
            <div className={styles.personalStockChips}>
              {personalStocks.map((item) => (
                <span key={item.code}>
                  <button type="button" onClick={() => onSelect(item.code)}>
                    <b>{item.name || item.code}</b>
                    <small>{item.code}</small>
                  </button>
                  <button
                    type="button"
                    aria-label={`移除 ${item.name || item.code}`}
                    disabled={stockManagerBusy}
                    onClick={() => void removePersonalStock(item.code)}
                  >
                    移除
                  </button>
                </span>
              ))}
              {!personalStocks.length && (
                <p>当前个人自选为空；下方分析暂沿用原有关注清单。</p>
              )}
            </div>
          </div>
          <aside>
            <span>持仓写入接口</span>
            <b>当前关闭</b>
            <p>
              状态接口：<code>/api/portfolio/capabilities</code>
              。切换到基础持仓模式并确认私有数据后，才开放数量、成本与账户字段。
            </p>
          </aside>
        </div>
      </section>
      <section className={`${styles.glass} ${styles.llmDeskBar}`}>
        <span>
          <small>LLM EVIDENCE LAYER</small>
          <b>大模型证据解读</b>
          <em>仅解释下方真实指标，不补造新闻、财务或目标价</em>
        </span>
        <label>
          <small>模型接口</small>
          <select
            value={llmProvider}
            onChange={(event) => setLlmProvider(event.target.value)}
          >
            {!llmProviders.length && <option value="">尚未配置</option>}
            {llmProviders.map((provider) => (
              <option key={provider.id} value={provider.id}>
                {provider.label} · {provider.model || "模型待填写"}
              </option>
            ))}
          </select>
          <button type="button" onClick={onOpenModelSettings}>
            管理接口
          </button>
        </label>
      </section>
      <section
        className={`${styles.glass} ${styles.conditionSummary}`}
        data-section="condition-summary"
      >
        <div>
          <small>积极</small>
          <b>{fourStates.positive}</b>
        </div>
        <div>
          <small>观察</small>
          <b>{fourStates.watch}</b>
        </div>
        <div>
          <small>风险</small>
          <b>{fourStates.negative}</b>
        </div>
        <div>
          <small>数据不足</small>
          <b>{fourStates.missing}</b>
        </div>
        <span>
          <small>当前分档</small>
          <strong>{tier}</strong>
        </span>
      </section>
      <section className={styles.conditionCards}>
        {analysisQuotes.map((item) => {
          const record = conditions[item.code];
          const matrix = record?.conditions as
            | Record<string, unknown>
            | undefined;
          const conclusion = matrix?.conclusion as
            | Record<string, unknown>
            | undefined;
          const features =
            (matrix?.featureProfile as Record<string, unknown>[] | undefined) ??
            [];
          const llm = llmAnalyses[item.code];
          return (
            <article className={styles.glass} key={item.code}>
              <button
                className={styles.conditionHeader}
                onClick={() => onSelect(item.code)}
              >
                <span>
                  <b>{item.name}</b>
                  <small>
                    {item.code} · {item.market}
                  </small>
                </span>
                <em className={tone(item.changePercent)}>
                  {change(item.changePercent)}
                </em>
              </button>
              <div className={styles.stockConclusion}>
                <span data-tone={String(conclusion?.tone ?? "missing")}>
                  {String(conclusion?.label ?? "计算中")}
                </span>
                <b>
                  {typeof conclusion?.score === "number"
                    ? `${conclusion.score.toFixed(0)} / 100`
                    : "—"}
                </b>
                <small>
                  {String(
                    conclusion?.summary ??
                      "等待真实日线完成条件计算，不生成占位结论。",
                  )}
                </small>
              </div>
              <div className={styles.featureProfile}>
                {features.map((feature) => (
                  <div key={String(feature.key)}>
                    <span>
                      <small>{String(feature.name)}</small>
                      <b>{String(feature.display ?? "数据不足")}</b>
                    </span>
                    <i>
                      <em
                        style={{
                          width: `${typeof feature.score === "number" ? Math.max(0, Math.min(100, feature.score)) : 0}%`,
                        }}
                      />
                    </i>
                  </div>
                ))}
                {!features.length && <p>指标计算中…</p>}
              </div>
              <div className={styles.conditionRows}>
                {[
                  [
                    "M60位置",
                    (matrix?.m60 as Record<string, unknown> | undefined)?.state,
                  ],
                  [
                    "M60方向",
                    (matrix?.m60 as Record<string, unknown> | undefined)
                      ?.direction,
                  ],
                  [
                    "RSI(14)",
                    (matrix?.rsi as Record<string, unknown> | undefined)?.value,
                  ],
                  [
                    "MACD",
                    (matrix?.macd as Record<string, unknown> | undefined)
                      ?.state,
                  ],
                  [
                    "量价",
                    (matrix?.volume as Record<string, unknown> | undefined)
                      ?.state,
                  ],
                  ["综合", matrix?.verdict],
                ].map(([label, value]) => (
                  <span key={String(label)}>
                    <small>{String(label)}</small>
                    <b>
                      {value == null
                        ? "数据不足"
                        : typeof value === "number"
                          ? value.toFixed(2)
                          : String(value)}
                    </b>
                  </span>
                ))}
              </div>
              <p>
                {String(
                  matrix?.reason ??
                    "读取真实历史数据后生成条件证据；没有数据时不生成判断。",
                )}
              </p>
              <div className={styles.llmAnalysisPanel}>
                <button
                  className={styles.secondaryButton}
                  disabled={!record || llmLoading === item.code}
                  onClick={() => void analyzeWithLlm(item.code)}
                >
                  {llmLoading === item.code
                    ? "模型解读中…"
                    : `${llmProviders.find((provider) => provider.id === llmProvider)?.label ?? "大模型"} 证据解读`}
                </button>
                {llm && (
                  <div>
                    <header>
                      <b>
                        {llm.error
                          ? "接口状态"
                          : `${String(llm.provider)} · ${String(llm.model)}`}
                      </b>
                      <small>
                        {String(
                          (llm.evidence as Record<string, unknown> | undefined)
                            ?.marketTime ?? "",
                        )}
                      </small>
                    </header>
                    <pre>{String(llm.analysis ?? llm.error ?? "")}</pre>
                    <small>{String(llm.riskNotice ?? "")}</small>
                  </div>
                )}
              </div>
            </article>
          );
        })}
      </section>
    </div>
  );
}

function ResearchView({
  tab,
  setTab,
  query,
  selected,
  dashboard,
}: {
  tab: ResearchTab;
  setTab: (tab: ResearchTab) => void;
  query: (
    path: string,
    params?: Record<string, string | number>,
    payload?: Record<string, unknown>,
  ) => Promise<unknown>;
  selected?: Quote;
  dashboard: Dashboard | null;
}) {
  const [message, setMessage] = useState("");
  const [technical, setTechnical] = useState<Record<string, unknown> | null>(
    null,
  );
  const [dual, setDual] = useState<Record<string, unknown> | null>(null);
  const [factors, setFactors] = useState<Record<string, unknown>[]>([]);
  const [factorPresets, setFactorPresets] = useState<
    Record<string, unknown>[]
  >([]);
  const [selectedFactors, setSelectedFactors] = useState([
    "Relative_Strength_20",
    "MACD_Hist_Norm",
    "Z_Score_20",
    "ATR_Ratio_14_60",
  ]);
  const [jobs, setJobs] = useState<Record<string, unknown>[]>([]);
  const [models, setModels] = useState<Record<string, unknown>[]>([]);
  const [trainingJob, setTrainingJob] = useState("");
  const [factorDraft, setFactorDraft] = useState({
    id: "",
    name: "",
    formula: "",
    family: "custom",
    track: "shared",
    description: "",
  });
  const [backtestConfig, setBacktestConfig] = useState({
    dateFrom: "2021-01-01",
    dateTo: new Date().toISOString().slice(0, 10),
    labelHorizon: 5,
    feeBps: 8,
    slippageBps: 5,
    minTrainDays: 250,
    testWindowDays: 20,
    t5ObservationStep: 5,
    attentionTopN: 2,
    probabilityFloor: 0.53,
  });
  async function run(task: () => Promise<void>) {
    setMessage("读取中");
    try {
      await task();
      setMessage("");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "请求失败");
    }
  }
  async function loadFactors() {
    const data = (await query("/api/research/factors")) as {
      records?: Record<string, unknown>[];
    };
    setFactors(data.records ?? []);
  }
  async function loadFactorPresets() {
    const data = (await query("/api/research/factor-presets")) as {
      records?: Record<string, unknown>[];
    };
    setFactorPresets(data.records ?? []);
  }
  useEffect(() => {
    if (!factorPresets.length && (tab === "dual" || tab === "factors"))
      queueMicrotask(() =>
        void loadFactorPresets().catch((error) =>
          setMessage(
            error instanceof Error ? error.message : "因子方案读取失败",
          ),
        ),
      );
    // Presets are immutable within one API version.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, query, factorPresets.length]);
  useEffect(() => {
    if (tab === "backtest" && !jobs.length)
      queueMicrotask(() =>
        void loadJobs("backtest").catch((error) =>
          setMessage(
            error instanceof Error ? error.message : "历史案例读取失败",
          ),
        ),
      );
    // Historical artifacts are immutable during this view session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, query, jobs.length]);
  async function loadJobs(mode?: string) {
    const data = (await query(
      "/api/research/jobs",
      mode ? { mode } : undefined,
    )) as { records?: Record<string, unknown>[] };
    setJobs(data.records ?? []);
  }
  async function loadModels() {
    const data = (await query("/api/research/models")) as {
      records?: Record<string, unknown>[];
    };
    setModels(data.records ?? []);
  }
  async function createFactor() {
    await query("/api/research/factors", undefined, factorDraft);
    setFactorDraft({
      id: "",
      name: "",
      formula: "",
      family: "custom",
      track: "shared",
      description: "",
    });
    await loadFactors();
  }
  const condition = technical?.conditions as
    | Record<string, { state?: string; value?: number; direction?: string }>
    | undefined;
  const latestJob = jobs[0];
  const backtestResults = latestJob?.results as
    | Record<string, unknown>
    | undefined;
  const walkForwardResults = backtestResults?.walkForwardResults as
    | Record<string, unknown>
    | undefined;
  const dualHorizonResults = backtestResults?.dualHorizonResults as
    | Record<string, Record<string, unknown>>
    | undefined;
  const t1Package = dualHorizonResults?.t1Attention;
  const t5Package = dualHorizonResults?.t5Return;
  const t1Attention = t1Package
    ? {
        ...((t1Package.tracks as Record<string, unknown> | undefined) ?? {}),
        consensus: t1Package.consensus,
      }
    : undefined;
  const t5Return = t5Package
    ? {
        ...((t5Package.tracks as Record<string, unknown> | undefined) ?? {}),
        consensus: t5Package.consensus,
      }
    : undefined;
  const resultPercent = (value: unknown) =>
    typeof value === "number" ? `${(value * 100).toFixed(2)}%` : "未计算";
  const trackLabel = (track: "tx" | "bs" | "consensus") =>
    track === "tx"
      ? "腾讯财经"
      : track === "bs"
        ? "BaoStock"
        : "双源一致";
  const trend = dashboard?.market.trend;
  const valuationRows = dashboard?.market.valuation?.data ?? [];
  const dualRows = (value: unknown) =>
    (
      (value as { records?: Record<string, unknown>[] } | undefined)?.records ??
      []
    )
      .slice()
      .sort((a, b) => Number(b.probability) - Number(a.probability));
  return (
    <div className={styles.researchLayout}>
      <aside className={`${styles.glass} ${styles.subnav}`}>
        {researchTabs.map((item) => (
          <button
            key={item.id}
            className={tab === item.id ? styles.subActive : ""}
            onClick={() => setTab(item.id)}
          >
            <span>
              <b>{item.label}</b>
              <small>{item.note}</small>
            </span>
            <i>
              <Icon name="chevron" />
            </i>
          </button>
        ))}
      </aside>
      <section className={styles.viewStack}>
        {message && (
          <div className={styles.alertBar}>
            <b>研究状态</b>
            <span>{message}</span>
          </div>
        )}
        {tab === "signals" && (
          <>
            <article
              className={`${styles.glass} ${styles.trendHero}`}
              data-section="medium-trend"
            >
              <div>
                <span className={styles.eyebrow}>MEDIUM-TERM TREND</span>
                <strong>
                  <TweenNumber value={trend?.score} decimals={1} />
                </strong>
                <h2>{trend?.state ?? "数据不足"}</h2>
                <p>{trend?.timeframe ?? "中期日线"} · 只用于状态观察</p>
              </div>
              <span className={styles.trendRail}>
                <i
                  style={{
                    left: `${Math.max(0, Math.min(100, ((trend?.score ?? 0) + 100) / 2))}%`,
                  }}
                />
              </span>
            </article>
            <article className={styles.glass}>
              <div className={styles.sectionHeading}>
                <span>01</span>
                <h2>五个关键反转信号</h2>
                <em>{selected?.name ?? "选择标的"}</em>
              </div>
              <button
                className={styles.secondaryButton}
                onClick={() =>
                  void run(async () =>
                    setTechnical(
                      (await query("/api/rsi-margin", {
                        code: selected?.code ?? "300308",
                      })) as Record<string, unknown>,
                    ),
                  )
                }
              >
                计算真实条件
              </button>
              <div className={styles.signalRows}>
                {[
                  [
                    "M60 位置与方向",
                    `${condition?.m60?.state ?? "数据不足"} / ${condition?.m60?.direction ?? "—"}`,
                  ],
                  ["RSI(14) 区间", condition?.rsi?.value],
                  ["MACD 动能状态", condition?.macd?.state],
                  ["量价确认", condition?.volume?.state],
                  [
                    "综合条件",
                    technical?.conditions &&
                      (technical.conditions as Record<string, unknown>).verdict,
                  ],
                ].map(([name, value]) => (
                  <div key={String(name)}>
                    <span>{String(name)}</span>
                    <b>
                      {value == null
                        ? "数据不足"
                        : typeof value === "number"
                          ? value.toFixed(2)
                          : String(value)}
                    </b>
                    <small>证据来自该标的历史行情</small>
                    <EvidencePopover
                      title={String(name)}
                      asOf={String(
                        (technical?.meta as Record<string, unknown> | undefined)
                          ?.market_time ?? "",
                      )}
                      source={String(
                        (technical?.meta as Record<string, unknown> | undefined)
                          ?.source ?? "",
                      )}
                      method="日线条件矩阵"
                    />
                  </div>
                ))}
              </div>
            </article>
            <article className={styles.glass}>
              <div className={styles.sectionHeading}>
                <span>02</span>
                <h2>估值监测</h2>
                <em>PE-TTM 历史分位</em>
              </div>
              <div className={styles.valuationBanner}>
                <b>
                  低估：{dashboard?.market.valuation?.alerts?.low?.length ?? 0}
                </b>
                <b>
                  高估：{dashboard?.market.valuation?.alerts?.high?.length ?? 0}
                </b>
              </div>
              <div className={styles.valuationAxis}>
                <span>0 极低</span>
                <span>30 低估</span>
                <span>50 中性</span>
                <span>70 高估</span>
                <span>100 极高</span>
              </div>
              <div className={styles.valuationRows}>
                {valuationRows.map((row) => (
                  <div key={String(row.requestedCode)}>
                    <span>
                      <b>{String(row.requestedCode)}</b>
                      <small>{String(row.band ?? "normal")}</small>
                    </span>
                    <i>
                      <em
                        style={{
                          left: `${Math.max(0, Math.min(100, Number(row.percentile ?? 0)))}%`,
                        }}
                      />
                    </i>
                    <strong>{Number(row.percentile).toFixed(1)}%</strong>
                  </div>
                ))}
              </div>
              <p className={styles.valueTrap}>
                低价格分位不等于真正便宜；缺少原子
                PE-TTM、净值或盈利质量时不生成价值结论。
              </p>
            </article>
            <article className={styles.glass}>
              <div className={styles.sectionHeading}>
                <span>03</span>
                <h2>指数技术明细矩阵</h2>
                <em>{dashboard?.market.technical?.length ?? 0} 项</em>
              </div>
              <div className={styles.techMatrix}>
                {(dashboard?.market.technical ?? []).map((row) => {
                  const matrix = row.conditions as
                    | Record<string, Record<string, unknown>>
                    | undefined;
                  return (
                    <div key={String(row.code)}>
                      <b>{String(row.name)}</b>
                      <span>M60 {String(matrix?.m60?.state ?? "—")}</span>
                      <span>RSI {String(matrix?.rsi?.value ?? "—")}</span>
                      <span>MACD {String(matrix?.macd?.state ?? "—")}</span>
                    </div>
                  );
                })}
              </div>
            </article>
            <article className={styles.glass}>
              <div className={styles.sectionHeading}>
                <span>04</span>
                <h2>状态变化提醒</h2>
                <em>跨进程去重</em>
              </div>
              <div className={styles.changeList}>
                {(
                  (technical?.changes as
                    | Record<string, unknown>[]
                    | undefined) ?? []
                ).map((changeRecord) => (
                  <div key={String(changeRecord.key)}>
                    <b>{String(changeRecord.key)}</b>
                    <span>
                      {String(changeRecord.from)} → {String(changeRecord.to)}
                    </span>
                    <small>{String(changeRecord.asOf ?? "")}</small>
                  </div>
                ))}
                {technical && !(technical.changes as unknown[])?.length && (
                  <p>本次没有新的状态翻转；首次载入不会误报。</p>
                )}
              </div>
            </article>
          </>
        )}
        {tab === "dual" && (
          <article className={styles.glass}>
            <div className={styles.sectionHeading}>
              <span>01</span>
              <h2>个人因子组合</h2>
              <em>条件研判基线之外的个人附加层</em>
            </div>
            <p className={styles.sectionIntro}>
              两条个人路径按真实数据源命名：腾讯财经历史行情侧重趋势与价格结构，BaoStock 日线历史数据侧重量价与流动性。科技成长（创业板/科创板）与主板使用不同因子族；两路独立计算后只做一致性观察，不构成买卖指令。
            </p>
            <div className={styles.factorPresetGrid}>
              {factorPresets.map((preset) => {
                const presetFactors =
                  (preset.factors as string[] | undefined) ?? [];
                const segments =
                  (preset.segments as Record<string, unknown>[] | undefined) ?? [];
                return (
                  <article key={String(preset.id)}>
                    <span>{String(preset.sourceName ?? preset.scope ?? "shared")}</span>
                    <h3>{String(preset.name)}</h3>
                    <p>{String(preset.description)}</p>
                    <em>{String(preset.characteristics ?? "")}</em>
                    <div className={styles.factorSegments}>
                      {segments.map((segment) => (
                        <details key={String(segment.name)}>
                          <summary>{String(segment.name)}</summary>
                          <p>{String(segment.note ?? "")}</p>
                          <small>
                            {(
                              (segment.factors as string[] | undefined) ?? []
                            ).join(" · ")}
                          </small>
                        </details>
                      ))}
                    </div>
                    {!segments.length && <small>{presetFactors.join(" · ")}</small>}
                    <button
                      className={styles.secondaryButton}
                      onClick={() => {
                        setSelectedFactors(presetFactors);
                        setMessage(`已导入“${String(preset.name)}”的 ${presetFactors.length} 个因子；尚未训练或回测。`);
                      }}
                    >
                      导入为当前方案
                    </button>
                  </article>
                );
              })}
            </div>
            <div className={styles.actionRow}>
              <button
                onClick={() =>
                  void run(async () =>
                    setDual(
                      (await query("/api/research/dual-track/latest")) as Record<
                        string,
                        unknown
                      >,
                    ),
                  )
                }
              >
                读取最近个人评分归档
              </button>
              <span className={styles.importState}>
                当前方案 {selectedFactors.length} 个因子
              </span>
            </div>
            <div className={styles.dualEvidence}>
              {(["tx", "bs"] as const).map((track) => (
                <section key={track}>
                  <h3>
                    {track === "tx"
                      ? "腾讯财经 · 趋势价格模型"
                      : "BaoStock · 量价流动性模型"} ·{" "}
                    {String(
                      (dual?.[track] as Record<string, unknown> | undefined)
                        ?.day ?? "未载入",
                    )}
                  </h3>
                  {dualRows(dual?.[track])
                    .slice(0, 11)
                    .map((row) => (
                      <div key={String(row.code)}>
                        <b>{String(row.code)}</b>
                        <span>
                          {(Number(row.probability) * 100).toFixed(2)}%
                        </span>
                        <em>
                          {String(row.tier || "未分档")} ·{" "}
                          {String(row.sector || "未分类")}
                        </em>
                      </div>
                    ))}
                </section>
              ))}
            </div>
            {dual?.comparison ? (
              <div className={styles.consensusTable}>
                <h3>
                  两路径一致性阈值{" "}
                  {Number(
                    (dual.comparison as Record<string, unknown>).threshold ??
                      0.53,
                  ) * 100}
                  % ·{" "}
                  {String(
                    (dual.comparison as Record<string, unknown>).day ?? "",
                  )}
                </h3>
                {(
                  ((dual.comparison as Record<string, unknown>).rows as
                    | Record<string, unknown>[]
                    | undefined) ?? []
                ).map((row) => (
                  <div key={String(row.code)}>
                    <b>{String(row.code)}</b>
                    <span>
                      腾讯财经{" "}
                      {typeof row.tx_probability === "number"
                        ? `${(row.tx_probability * 100).toFixed(1)}%`
                        : "—"}
                    </span>
                    <span>
                      BaoStock{" "}
                      {typeof row.bs_probability === "number"
                        ? `${(row.bs_probability * 100).toFixed(1)}%`
                        : "—"}
                    </span>
                    <em>{String(row.consensus)}</em>
                  </div>
                ))}
              </div>
            ) : (
              <div className={styles.honestEmpty}>
                没有同日完整的两路径归档时不拼接比较；可先导入上方因子方案。
              </div>
            )}
            {message && <p className={styles.inlineState}>{message}</p>}
          </article>
        )}
        {tab === "factors" && (
          <>
            <article className={styles.glass}>
              <div className={styles.sectionHeading}>
                <span>01</span>
                <h2>因子目录与版本</h2>
                <em>可审计</em>
              </div>
              <button
                className={styles.secondaryButton}
                onClick={() => void run(loadFactors)}
              >
                载入因子目录
              </button>
              <div className={styles.factorGrid}>
                {factors.map((record) => (
                  <label key={`${String(record.id)}-${String(record.version)}`}>
                    <input
                      type="checkbox"
                      checked={selectedFactors.includes(String(record.id))}
                      onChange={(event) =>
                        setSelectedFactors((current) =>
                          event.target.checked
                            ? [...new Set([...current, String(record.id)])]
                            : current.filter(
                                (name) => name !== String(record.id),
                              ),
                        )
                      }
                    />
                    <span>{String(record.family ?? "factor")}</span>
                    <b>{String(record.id)}</b>
                    <small>
                      v{String(record.version)} · {String(record.track)} ·{" "}
                      {String(record.status)}
                    </small>
                  </label>
                ))}
              </div>
            </article>
            <article className={styles.glass}>
              <div className={styles.sectionHeading}>
                <span>02</span>
                <h2>安全公式因子设计</h2>
                <em>禁止任意代码</em>
              </div>
              <div className={styles.formGrid}>
                {Object.entries(factorDraft).map(([key, value]) => (
                  <label key={key}>
                    <span>{key}</span>
                    <input
                      value={value}
                      onChange={(event) =>
                        setFactorDraft((current) => ({
                          ...current,
                          [key]: event.target.value,
                        }))
                      }
                      placeholder={
                        key === "formula" ? "Return_20 / ATR_Ratio_14_60" : key
                      }
                    />
                  </label>
                ))}
              </div>
              <button
                className={styles.secondaryButton}
                onClick={() => void run(createFactor)}
              >
                保存新版本
              </button>
            </article>
          </>
        )}
        {tab === "backtest" && (
          <article className={styles.glass}>
            <div className={styles.sectionHeading}>
              <span>01</span>
              <h2>自定义回测接口与历史案例</h2>
              <em>本轮暂停执行</em>
            </div>
            <div className={styles.pipeline}>
              {[
                "数据快照",
                "自定义因子",
                "标签可知边界",
                "样本外概率",
                "T+1关注命中",
                "T+5持有收益",
                "审计归档",
              ].map((item, index) => (
                <span key={item}>
                  <i>{String(index + 1).padStart(2, "0")}</i>
                  <b>{item}</b>
                </span>
              ))}
            </div>
            <p className={styles.sectionIntro}>
              页面保留自定义因子、日期、成本、窗口和阈值接口；按本次优先级不再触发新回测。现有
              腾讯财经/BaoStock 双周期结果作为历史案例只读保留；工作台其他模块验收完成后再处理实盘回测。
            </p>
            <div className={styles.formGrid}>
              {Object.entries(backtestConfig).map(([key, value]) => (
                <label key={key}>
                  <span>{key}</span>
                  <input
                    type={key.startsWith("date") ? "date" : "number"}
                    step={key === "probabilityFloor" ? "0.01" : "1"}
                    value={value}
                    onChange={(event) =>
                      setBacktestConfig((current) => ({
                        ...current,
                        [key]: key.startsWith("date")
                          ? event.target.value
                          : Number(event.target.value),
                      }))
                    }
                  />
                </label>
              ))}
            </div>
            <div className={styles.actionRow}>
              <button disabled title="按本次任务范围暂停新回测">
                执行接口已保留
              </button>
              <button onClick={() => void run(() => loadJobs("backtest"))}>
                读取历史案例
              </button>
            </div>
            {latestJob ? (
              <div className={styles.jobCard}>
                <b>{String(latestJob.id)}</b>
                <span>历史案例 · {String(latestJob.status)}</span>
                <small>{String(latestJob.progress_message ?? "")}</small>
                <div className={styles.caseMeta}>
                  <span>
                    <small>样本</small>
                    <b>{String(backtestResults?.observations ?? "—")} 行</b>
                  </span>
                  <span>
                    <small>标的</small>
                    <b>
                      {Array.isArray(backtestResults?.stocks)
                        ? backtestResults.stocks.length
                        : "—"} 只
                    </b>
                  </span>
                  <span>
                    <small>数据版本</small>
                    <b>{String(backtestResults?.dataVersion ?? "—")}</b>
                  </span>
                  <span>
                    <small>样本底座</small>
                    <b>腾讯历史复权日线</b>
                  </span>
                </div>
                <p className={styles.caseBoundary}>
                  本案例从既有文件制品读取。样本底座为 AkShare
                  腾讯复权日线；“BaoStock”表示量价流动性因子族，并非本案例重新拉取了 BaoStock
                  双份样本。结果仅用于方法展示，不作为当前实盘结论。
                </p>
                {t1Attention && (
                  <>
                    <h3>T+1 · 关注命中，不假设交易</h3>
                    <div className={styles.metricGrid}>
                      {(["tx", "bs", "consensus"] as const)
                        .flatMap((track) => {
                          const row = t1Attention[track] as
                            | Record<string, unknown>
                            | undefined;
                          return [
                            [
                              `${trackLabel(track)} 跑赢率`,
                              resultPercent(row?.outperformanceHitRate),
                            ],
                            [
                              `${trackLabel(track)} 上涨率`,
                              resultPercent(row?.positiveHitRate),
                            ],
                          ];
                        })
                        .map(([name, value]) => (
                          <div key={String(name)}>
                            <span>{String(name)}</span>
                            <b>{String(value)}</b>
                          </div>
                        ))}
                    </div>
                  </>
                )}
                {t5Return && (
                  <>
                    <h3>T+5 · 非重叠持有与成本后收益</h3>
                    <div className={styles.metricGrid}>
                      {(["tx", "bs", "consensus"] as const)
                        .flatMap((track) => {
                          const row = t5Return[track] as
                            | Record<string, unknown>
                            | undefined;
                          const study = row?.returnStudy as
                            | Record<string, unknown>
                            | undefined;
                          return [
                            [
                              `${trackLabel(track)} 成本后年化`,
                              resultPercent(
                                study?.costAdjustedAnnualizedReturn,
                              ),
                            ],
                            [
                              `${trackLabel(track)} 最大回撤`,
                              resultPercent(study?.maxDrawdown),
                            ],
                          ];
                        })
                        .map(([name, value]) => (
                          <div key={String(name)}>
                            <span>{String(name)}</span>
                            <b>{String(value)}</b>
                          </div>
                        ))}
                    </div>
                  </>
                )}
                {walkForwardResults && (
                  <div className={styles.honestEmpty}>
                    兼容旧版 T+1
                    多空结果已保留在历史制品，不作为当前双周期主口径。
                  </div>
                )}
                {Boolean(latestJob.results) && (
                  <details>
                    <summary>查看只读案例摘要与方法边界</summary>
                    <pre>{JSON.stringify(latestJob.results, null, 2)}</pre>
                  </details>
                )}
              </div>
            ) : (
              <div className={styles.honestEmpty}>
                点击“读取历史案例”查看已完成结果；本轮不会创建新的回测任务。
              </div>
            )}
          </article>
        )}
        {tab === "models" && (
          <article className={styles.glass}>
            <div className={styles.sectionHeading}>
              <span>01</span>
              <h2>模型晋级与回滚</h2>
              <em>稳定版不覆盖</em>
            </div>
            <div className={styles.modelControl}>
              <input
                value={trainingJob}
                onChange={(event) => setTrainingJob(event.target.value)}
                placeholder="已完成训练任务 ID"
              />
              <button
                onClick={() =>
                  void run(async () => {
                    await query("/api/research/models/promote", undefined, {
                      engine: "tx",
                      job_id: trainingJob,
                    });
                    await loadModels();
                  })
                }
              >
                晋级腾讯财经模型
              </button>
              <button
                onClick={() =>
                  void run(async () => {
                    await query("/api/research/models/promote", undefined, {
                      engine: "bs",
                      job_id: trainingJob,
                    });
                    await loadModels();
                  })
                }
              >
                晋级 BaoStock 模型
              </button>
              <button
                onClick={() =>
                  void run(async () => {
                    await query(
                      "/api/research/models/tx/rollback",
                      undefined,
                      {},
                    );
                    await loadModels();
                  })
                }
              >
                回滚腾讯财经模型
              </button>
              <button
                onClick={() =>
                  void run(async () => {
                    await query(
                      "/api/research/models/bs/rollback",
                      undefined,
                      {},
                    );
                    await loadModels();
                  })
                }
              >
                回滚 BaoStock 模型
              </button>
              <button onClick={() => void run(loadModels)}>刷新</button>
            </div>
            <div className={styles.changeList}>
              {models.map((record) => (
                <div key={String(record.id)}>
                  <b>
                    {String(record.engine).toLowerCase() === "tx"
                      ? "腾讯财经"
                      : String(record.engine).toLowerCase() === "bs"
                        ? "BaoStock"
                        : String(record.engine)}{" "}
                    ·{" "}
                    {String(record.status)}
                  </b>
                  <span>{String(record.job_id)}</span>
                  <small>{String(record.created_at)}</small>
                </div>
              ))}
            </div>
          </article>
        )}
      </section>
    </div>
  );
}

export function ResearchViewLegacy({
  tab,
  setTab,
  query,
  selected,
}: {
  tab: ResearchTab;
  setTab: (tab: ResearchTab) => void;
  query: (
    path: string,
    params?: Record<string, string | number>,
    payload?: Record<string, unknown>,
  ) => Promise<unknown>;
  selected?: Quote;
}) {
  const [records, setRecords] = useState<Record<string, unknown>[]>([]);
  const [message, setMessage] = useState("");
  async function load(path: string) {
    setMessage("读取中");
    try {
      const data = (await query(path)) as {
        records?: Record<string, unknown>[];
      };
      setRecords(data.records ?? []);
      setMessage(data.records?.length ? "" : "暂无真实记录");
    } catch (error) {
      setRecords([]);
      setMessage(error instanceof Error ? error.message : "读取失败");
    }
  }
  return (
    <div className={styles.researchLayout}>
      <aside className={`${styles.glass} ${styles.subnav}`}>
        {researchTabs.map((item) => (
          <button
            key={item.id}
            className={tab === item.id ? styles.subActive : ""}
            onClick={() => setTab(item.id)}
          >
            <span>
              <b>{item.label}</b>
              <small>{item.note}</small>
            </span>
            <i>›</i>
          </button>
        ))}
      </aside>
      <section className={styles.viewStack}>
        {tab === "signals" && (
          <>
            <article className={styles.glass}>
              <div className={styles.sectionHeading}>
                <span>01</span>
                <h2>中期趋势与条件矩阵</h2>
                <em>{selected?.name ?? "选择标的"}</em>
              </div>
              <div className={styles.signalGrid}>
                {[
                  "M60 位置与方向",
                  "RSI 区间",
                  "MACD 状态",
                  "缩量回调",
                  "估值高低区",
                  "数据质量",
                ].map((item) => (
                  <div key={item}>
                    <span>{item}</span>
                    <b>数据不足</b>
                    <small>不补造结论</small>
                  </div>
                ))}
              </div>
            </article>
            <article className={styles.glass}>
              <div className={styles.sectionHeading}>
                <span>02</span>
                <h2>六维全局信号</h2>
                <em>条件观察</em>
              </div>
              <div className={styles.dimensionGrid}>
                {["估值", "趋势", "动量", "宽度", "情绪", "波动"].map(
                  (item) => (
                    <span key={item}>
                      <i />
                      <b>{item}</b>
                      <small>待计算</small>
                    </span>
                  ),
                )}
              </div>
            </article>
          </>
        )}
        {tab === "dual" && (
          <article className={styles.glass}>
            <div className={styles.sectionHeading}>
              <span>01</span>
              <h2>个人因子组合</h2>
              <em>日频</em>
            </div>
            <p className={styles.sectionIntro}>
              腾讯财经历史行情用于趋势动能评分，BaoStock 日线历史数据用于量价流动性评分；两者均为条件研判基线之外的个人附加层。
            </p>
            <button
              className={styles.secondaryButton}
              onClick={() => void load("/api/research/dual-track/latest")}
            >
              读取最近个人评分归档
            </button>
            <div className={styles.dualCards}>
              <div>
                <small>腾讯财经趋势模型</small>
                <strong>—</strong>
                <span>等待归档</span>
              </div>
              <div>
                <small>BaoStock 量价模型</small>
                <strong>—</strong>
                <span>等待归档</span>
              </div>
              <div>
                <small>两路径一致性</small>
                <strong>—</strong>
                <span>阈值 53%</span>
              </div>
            </div>
            {message && <p className={styles.inlineState}>{message}</p>}
          </article>
        )}
        {tab === "factors" && (
          <article className={styles.glass}>
            <div className={styles.sectionHeading}>
              <span>01</span>
              <h2>因子设计与分析</h2>
              <em>版本化</em>
            </div>
            <div className={styles.actionLine}>
              <p>
                因子定义、公式、窗口、方向、缺失处理、中性化、轨道与版本独立保存。
              </p>
              <button
                className={styles.secondaryButton}
                onClick={() => void load("/api/research/factors")}
              >
                载入因子目录
              </button>
            </div>
            {records.length ? (
              <div className={styles.factorGrid}>
                {records.map((record) => (
                  <div key={String(record.id)}>
                    <span>{String(record.family ?? "factor")}</span>
                    <b>{String(record.id)}</b>
                    <small>
                      {String(record.track)} · W{String(record.window)} ·{" "}
                      {String(record.status)}
                    </small>
                  </div>
                ))}
              </div>
            ) : (
              <div className={styles.honestEmpty}>
                {message ||
                  "载入后展示覆盖率、IC、RankIC、ICIR、衰减、换手、相关性与市场状态稳定性。"}
              </div>
            )}
          </article>
        )}
        {tab === "backtest" && (
          <article className={styles.glass}>
            <div className={styles.sectionHeading}>
              <span>01</span>
              <h2>训练与真实回测</h2>
              <em>Walk-forward</em>
            </div>
            <div className={styles.pipeline}>
              {[
                "数据快照",
                "因子计算",
                "未来函数检查",
                "训练/验证/测试",
                "Walk-forward",
                "成本回测",
                "候选模型",
              ].map((item, index) => (
                <span key={item}>
                  <i>{String(index + 1).padStart(2, "0")}</i>
                  <b>{item}</b>
                </span>
              ))}
            </div>
            <button
              className={styles.secondaryButton}
              onClick={() => void load("/api/research/backtests")}
            >
              读取真实回测任务
            </button>
            <div className={styles.metricGrid}>
              {[
                "IC / RankIC",
                "ICIR",
                "年化/超额",
                "最大回撤",
                "换手率",
                "成本后收益",
              ].map((item) => (
                <div key={item}>
                  <span>{item}</span>
                  <b>未计算</b>
                </div>
              ))}
            </div>
            <p className={styles.inlineState}>
              {message || "未实际运行的指标保持“未计算”，不会生成占位数值。"}
            </p>
          </article>
        )}
        {tab === "models" && (
          <article className={styles.glass}>
            <div className={styles.sectionHeading}>
              <span>01</span>
              <h2>模型与报告归档</h2>
              <em>可回退</em>
            </div>
            <div className={styles.modelStages}>
              {["DRAFT", "CANDIDATE", "SHADOW", "STABLE", "RETIRED"].map(
                (item, index) => (
                  <span key={item}>
                    <i>{index + 1}</i>
                    <b>{item}</b>
                  </span>
                ),
              )}
            </div>
            <p className={styles.sectionIntro}>
              每个版本绑定数据快照、因子版本、参数、代码版本、回测报告、制品哈希与上线记录；候选版本不会覆盖稳定模型。
            </p>
          </article>
        )}
      </section>
    </div>
  );
}

function ReferenceView({
  quotes,
  selected,
  selectedCode,
  setSelectedCode,
  query,
}: {
  quotes: Quote[];
  selected?: Quote;
  selectedCode: string;
  setSelectedCode: (code: string) => void;
  query: (
    path: string,
    params?: Record<string, string | number>,
    payload?: Record<string, unknown>,
  ) => Promise<unknown>;
}) {
  const [period, setPeriod] = useState<"minute" | "day" | "week" | "month">(
    "day",
  );
  const [chart, setChart] = useState<KlinePackage | IntradayPackage | null>(
    null,
  );
  const [chartState, setChartState] = useState("尚未读取");
  const [layers, setLayers] = useState({
    ma5: true,
    ma10: true,
    ma20: true,
    ma60: true,
    macd: true,
  });
  const [newsFilter, setNewsFilter] = useState<
    "all" | "bull" | "bear" | "focus"
  >("all");
  const [usTab, setUsTab] = useState<
    "overview" | "indices" | "stocks" | "china" | "futures" | "macro" | "impact"
  >("overview");
  const [usOpen, setUsOpen] = useState(false);
  const [referenceData, setReferenceData] = useState<{
    valuation?: Record<string, unknown>;
    margin?: Record<string, unknown>;
    news?: Record<string, unknown>[];
    fund?: Record<string, unknown>;
    macro?: Record<string, unknown>[];
    fx?: Record<string, unknown>[];
    futures?: Record<string, unknown>[];
    impact?: Record<string, unknown>[];
    investor?: Record<string, unknown>;
    buffett?: Record<string, unknown>;
  }>({});
  const loadChart = useCallback(async () => {
    setChartState("读取中");
    try {
      const result =
        period === "minute"
          ? ((await query("/api/intraday", {
              code: selectedCode,
            })) as IntradayPackage)
          : ((await query("/api/kline", {
              code: selectedCode,
              period,
              limit: 160,
            })) as KlinePackage);
      setChart(result);
      setChartState(
        result.data?.length
          ? `${result.data.length} 条 · ${result.meta?.source ?? "来源未知"} · ${result.cacheState ?? "live"}`
          : "数据不足",
      );
    } catch (error) {
      setChart(null);
      setChartState(error instanceof Error ? error.message : "读取失败");
    }
  }, [period, query, selectedCode]);
  useEffect(() => {
    queueMicrotask(() => void loadChart());
  }, [loadChart]);
  useEffect(() => {
    let active = true;
    const selectedJob =
      selected?.assetType === "index"
        ? query("/api/valuations", { codes: selected.code })
        : selected?.assetType === "fund"
          ? query("/api/fund", { code: selected.code })
          : Promise.resolve(null);
    const jobs = [
      query("/api/news", { limit: 20 }),
      query("/api/margin"),
      selectedJob,
      query("/api/macro"),
      query("/api/fx"),
      query("/api/us-futures"),
      query("/api/cross-market-impact"),
      query("/api/investor-accounts"),
      query("/api/buffett-history"),
    ];
    Promise.allSettled(jobs).then((results) => {
      if (!active) return;
      const next: typeof referenceData = {};
      if (results[0]?.status === "fulfilled")
        next.news =
          (results[0].value as { data?: Record<string, unknown>[] }).data ?? [];
      if (results[1]?.status === "fulfilled")
        next.margin = (
          results[1].value as { data?: Record<string, unknown> }
        ).data;
      if (selected?.assetType === "index" && results[2]?.status === "fulfilled")
        next.valuation = ((
          results[2].value as { data?: Record<string, unknown>[] } | null
        )?.data ?? [])[0];
      if (selected?.assetType === "fund" && results[2]?.status === "fulfilled")
        next.fund = (
          results[2].value as { data?: Record<string, unknown> } | null
        )?.data;
      if (results[3]?.status === "fulfilled")
        next.macro =
          (results[3].value as { data?: Record<string, unknown>[] }).data ?? [];
      if (results[4]?.status === "fulfilled")
        next.fx =
          (results[4].value as { data?: Record<string, unknown>[] }).data ?? [];
      if (results[5]?.status === "fulfilled")
        next.futures =
          (results[5].value as { data?: Record<string, unknown>[] }).data ?? [];
      if (results[6]?.status === "fulfilled")
        next.impact =
          (results[6].value as { data?: Record<string, unknown>[] }).data ?? [];
      if (results[7]?.status === "fulfilled")
        next.investor = (
          results[7].value as { data?: Record<string, unknown> }
        ).data;
      if (results[8]?.status === "fulfilled")
        next.buffett = (
          results[8].value as { data?: Record<string, unknown> }
        ).data;
      setReferenceData(next);
    });
    return () => {
      active = false;
    };
  }, [query, selected?.assetType, selected?.code]);
  const valuation = referenceData.valuation;
  const fund = referenceData.fund;
  const margin = referenceData.margin;
  const news = referenceData.news ?? [];
  const macro = referenceData.macro ?? [];
  const fx = referenceData.fx ?? [];
  const futures = referenceData.futures ?? [];
  const impact = referenceData.impact ?? [];
  const investor = referenceData.investor;
  const buffett = referenceData.buffett;
  const filteredNews = news
    .filter(
      (item) =>
        newsFilter === "all" ||
        (Array.isArray(item.tags) &&
          item.tags.map(String).includes(newsFilter)),
    )
    .slice(0, 8);
  const usQuotes = quotes.filter((item) => item.market === "US");
  const usRows =
    usTab === "indices"
      ? usQuotes.filter((item) => item.assetType === "index")
      : usTab === "stocks"
        ? usQuotes.filter((item) => item.assetType === "equity")
        : usTab === "china"
          ? usQuotes.filter((item) =>
              ["BABA", "JD", "PDD", "BIDU", "NIO"].includes(item.code),
            )
          : usQuotes;
  const upstreamRows =
    usTab === "futures"
      ? futures
      : usTab === "macro"
        ? [
            ...macro,
            ...fx,
            ...(investor
              ? [
                  {
                    code: "SSE_ACCOUNT",
                    name: "股票账户新开户",
                    value: (
                      investor.latest as Record<string, unknown> | undefined
                    )?.newStockAccounts,
                    unit: "万户",
                    date: (
                      investor.latest as Record<string, unknown> | undefined
                    )?.month,
                    source: "上交所月报",
                  },
                ]
              : []),
            ...(buffett
              ? [
                  {
                    code: "BUFFETT",
                    name: "上市公司市值/GDP历史分位",
                    value: buffett.historicalPercentile,
                    unit: "%",
                    date: buffett.latestYear,
                    source: "World Bank / WFE",
                  },
                ]
              : []),
          ]
        : [];
  const usContent = (
    <>
      <div className={styles.referenceTabs}>
        {[
          ["overview", "实时分时"],
          ["futures", "盘前期货"],
          ["indices", "主要指数"],
          ["stocks", "科技龙头"],
          ["china", "中概股"],
          ["macro", "宏观监测"],
          ["impact", "对A股影响"],
        ].map(([key, label]) => (
          <button
            key={key}
            className={usTab === key ? styles.chartActive : ""}
            onClick={() => setUsTab(key as typeof usTab)}
          >
            {label}
          </button>
        ))}
      </div>
      {usTab === "impact" ? (
        <div className={styles.usQuoteGrid}>
          {impact.slice(0, 9).map((item, index) => (
            <div key={`${String(item.usCode)}-${String(item.cnCode)}-${index}`}>
              <span>
                <b>
                  {String(item.usName)} → {String(item.cnName)}
                </b>
                <small>
                  前一美股收盘对齐下一中国交易日 · n={String(item.samples)}
                </small>
              </span>
              <strong>
                ρ {String(item.correlation ?? "—")} · β{" "}
                {String(item.beta ?? "—")}
              </strong>
              <em>条件映射 {String(item.conditionalMove ?? "—")}%</em>
            </div>
          ))}
          {!impact.length && (
            <div className={styles.honestEmpty}>
              共同交易日样本不足或上游不可用；不生成影响结论。
            </div>
          )}
        </div>
      ) : ["futures", "macro"].includes(usTab) ? (
        <div className={styles.usQuoteGrid}>
          {upstreamRows.map((item, index) => (
            <div key={`${String(item.code ?? item.pair)}-${index}`}>
              <span>
                <b>{String(item.name ?? item.pair ?? "指标")}</b>
                <small>
                      {String(item.sourceClass ?? item.source ?? item.method ?? "公开上游")}
                </small>
              </span>
              <strong>
                {String(item.value ?? item.price ?? "—")}
                {item.unit ? ` ${String(item.unit)}` : ""}
              </strong>
              <em>{String(item.date ?? item.marketTime ?? "")}</em>
            </div>
          ))}
          {!upstreamRows.length && (
            <div className={styles.honestEmpty}>
              该正式上游当前不可用；不以现货或旧值冒充。
            </div>
          )}
        </div>
      ) : (
        <div className={styles.usQuoteGrid}>
          {usRows.map((item) => (
            <button key={item.code} onClick={() => setSelectedCode(item.code)}>
              <span>
                <b>{item.name}</b>
                <small>{item.code}</small>
              </span>
              <strong>{price(item.price, item.currency)}</strong>
              <em className={tone(item.changePercent)}>
                {change(item.changePercent)}
              </em>
            </button>
          ))}
          {!usRows.length && (
            <div className={styles.honestEmpty}>该分类暂无已接入标的。</div>
          )}
        </div>
      )}
    </>
  );
  return (
    <div className={styles.referenceLayout}>
      <aside className={`${styles.glass} ${styles.securityPicker}`}>
        <div className={styles.panelTitle}>
          <span>
            <small>SECURITIES</small>
            <b>研究标的</b>
          </span>
        </div>
        {quotes.map((item) => (
          <button
            key={`${item.market}-${item.code}`}
            className={selectedCode === item.code ? styles.picked : ""}
            onClick={() => setSelectedCode(item.code)}
          >
            <span>
              <b>{item.name}</b>
              <small>{item.code}</small>
            </span>
            <em>
              {item.market}
              {item.delayLabel ? ` · ${item.delayLabel}` : ""}
            </em>
          </button>
        ))}
      </aside>
      <section className={styles.viewStack}>
        <article className={styles.glass}>
          <div className={styles.securityHeader}>
            <div>
              <span className={styles.eyebrow}>
                {selected?.code} · {selected?.market}
                {selected?.delayLabel ? ` · ${selected.delayLabel}` : ""}
              </span>
              <h2>{selected?.name}</h2>
            </div>
            <div>
              <small>实时参考价</small>
              <strong>{price(selected?.price, selected?.currency)}</strong>
              <span className={tone(selected?.changePercent)}>
                {change(selected?.changePercent)}
              </span>
            </div>
          </div>
          <div className={styles.klineBox}>
            <div className={styles.klineToolbar}>
              {(["minute", "day", "week", "month"] as const).map((value) => (
                <button
                  key={value}
                  className={period === value ? styles.chartActive : ""}
                  onClick={() => setPeriod(value)}
                >
                  {value === "minute"
                    ? "分时"
                    : value === "day"
                      ? "日"
                      : value === "week"
                        ? "周"
                        : "月"}
                </button>
              ))}
              <span>{chartState}</span>
              <button onClick={() => void loadChart()}>刷新</button>
            </div>
            {period !== "minute" && (
              <div className={styles.layerToggles}>
                {(["ma5", "ma10", "ma20", "ma60", "macd"] as const).map(
                  (key) => (
                    <label key={key}>
                      <input
                        type="checkbox"
                        checked={layers[key]}
                        onChange={(event) =>
                          setLayers((current) => ({
                            ...current,
                            [key]: event.target.checked,
                          }))
                        }
                      />
                      {key.toUpperCase()}
                    </label>
                  ),
                )}
              </div>
            )}
            <MarketCanvas
              packageData={chart}
              mode={period === "minute" ? "minute" : "kline"}
              layers={layers}
            />
          </div>
        </article>
        {usQuotes.length > 0 && (
          <article className={styles.glass}>
            <div className={styles.panelTitle}>
              <span>
                <small>US MARKET</small>
                <b>美股与跨市场影响</b>
              </span>
              <button
                className={styles.expandButton}
                onClick={() => setUsOpen(true)}
              >
                <Icon name="expand" />
                全屏
              </button>
            </div>
            {usContent}
          </article>
        )}
        <section className={styles.threeGrid}>
          <article className={styles.glass}>
            <div className={styles.panelTitle}>
              <span>
                <small>REFERENCE</small>
                <b>估值与净值</b>
              </span>
              <em>原子数据</em>
            </div>
            {valuation ? (
              <div className={styles.compactList}>
                <div>
                  <b>PE-TTM</b>
                  <span>{Number(valuation.peTtm).toFixed(2)}</span>
                  <small>{String(valuation.date ?? "")}</small>
                </div>
                <div>
                  <b>历史分位</b>
                  <span>{Number(valuation.percentile).toFixed(2)}%</span>
                  <small>{String(valuation.band ?? "")}</small>
                </div>
              </div>
            ) : fund ? (
              <div className={styles.compactList}>
                <div>
                  <b>官方净值</b>
                  <span>{String(fund.officialNav ?? "—")}</span>
                  <small>{String(fund.officialDate ?? "")}</small>
                </div>
                <div>
                  <b>盘中估算</b>
                  <span>
                    {fund.estimateChangePercent == null
                      ? (fund.benchmarkQuote as Record<string, unknown> | undefined)?.proxyChangePercent == null
                        ? "数据不足"
                        : `${Number((fund.benchmarkQuote as Record<string, unknown>).proxyChangePercent).toFixed(2)}%`
                      : `${Number(fund.estimateChangePercent).toFixed(2)}%`}
                  </span>
                  <small>{fund.estimateChangePercent == null && fund.benchmarkQuote ? "H30539→399997 指数代理" : "平台估算；不以昨日净值冒充"}</small>
                </div>
                <div>
                  <b>官方业绩基准</b>
                  <span>{String((fund.benchmark as Record<string, unknown> | undefined)?.name ?? "未配置")}</span>
                  <small>{String((fund.benchmark as Record<string, unknown> | undefined)?.formula ?? "")}</small>
                </div>
              </div>
            ) : (
              <div className={styles.honestEmpty}>
                该标的没有可靠原子 PE-TTM / 基金净值；不以价格分位冒充估值。
              </div>
            )}
          </article>
          <article className={styles.glass}>
            <div className={styles.panelTitle}>
              <span>
                <small>REFERENCE</small>
                <b>公告 / 新闻</b>
              </span>
              <em>东方财富</em>
            </div>
            <div className={styles.referenceTabs}>
              {[
                ["all", "全部"],
                ["bull", "利好"],
                ["bear", "利空"],
                ["focus", "重点"],
              ].map(([key, label]) => (
                <button
                  key={key}
                  className={newsFilter === key ? styles.chartActive : ""}
                  onClick={() => setNewsFilter(key as typeof newsFilter)}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className={styles.compactList}>
              {filteredNews.map((item, index) => {
                const tags = Array.isArray(item.tags)
                  ? item.tags.map(String)
                  : [];
                const newsTone = tags.includes("bear")
                  ? styles.newsBear
                  : tags.includes("bull")
                    ? styles.newsBull
                    : styles.newsNeutral;
                return (
                  <details
                    className={`${styles.newsItem} ${newsTone}`}
                    key={`${String(item.time)}-${index}`}
                  >
                    <summary>
                      <b>{String(item.title)}</b>
                      <span>{String(item.time ?? "")}</span>
                    </summary>
                    <small>{tags.join(" · ") || "未分类"}</small>
                    <p>
                      {String(
                        item.summary ?? "原文摘要未提供；保留标题与时间。",
                      )}
                    </p>
                  </details>
                );
              })}
              {!filteredNews.length && (
                <div className={styles.honestEmpty}>该筛选项暂无可靠记录。</div>
              )}
            </div>
          </article>
          <article className={styles.glass}>
            <div className={styles.panelTitle}>
              <span>
                <small>REFERENCE</small>
                <b>融资融券与资金流</b>
              </span>
              <em>日频</em>
            </div>
            {typeof margin?.balance === "number" ? (
              <div className={styles.compactList}>
                <div>
                  <b>融资余额</b>
                  <span>{`${(margin.balance / 1e12).toFixed(2)} 万亿`}</span>
                  <small>{String(margin.date ?? "")}</small>
                </div>
                <div>
                  <b>覆盖证券</b>
                  <span>{String(margin.constituentCount ?? "—")}</span>
                  <small>汇总口径</small>
                </div>
              </div>
            ) : (
              <div className={styles.honestEmpty}>
                上游融资余额暂不可用；不填造数值。
              </div>
            )}
          </article>
        </section>
      </section>
      {usOpen && (
        <div
          className={styles.fullscreenLayer}
          role="dialog"
          aria-modal="true"
          aria-label="美股与跨市场七页签"
        >
          <header>
            <div>
              <span className={styles.eyebrow}>US MARKET & CROSS-MARKET</span>
              <h2>美股与跨市场影响</h2>
            </div>
            <button onClick={() => setUsOpen(false)} aria-label="关闭">
              <Icon name="close" />
            </button>
          </header>
          <div className={styles.fullscreenBody}>{usContent}</div>
          <footer>
            仅呈现已接入的真实上游；盘前、宏观及影响数据缺失时明确留空。
          </footer>
        </div>
      )}
    </div>
  );
}

function MarketCanvas({
  packageData,
  mode,
  layers,
}: {
  packageData: KlinePackage | IntradayPackage | null;
  mode: "kline" | "minute";
  layers: {
    ma5: boolean;
    ma10: boolean;
    ma20: boolean;
    ma60: boolean;
    macd: boolean;
  };
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [cursor, setCursor] = useState<{
    x: number;
    y: number;
    index: number;
  } | null>(null);
  const rows = useMemo(() => packageData?.data ?? [], [packageData]);
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !rows.length) return;
    const rect = canvas.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.round(rect.width * ratio));
    canvas.height = Math.max(1, Math.round(rect.height * ratio));
    const context = canvas.getContext("2d");
    if (!context) return;
    context.scale(ratio, ratio);
    const width = rect.width,
      height = rect.height,
      pad = { left: 44, right: 14, top: 16, bottom: 25 };
    const macdHeight = mode === "kline" && layers.macd ? height * 0.13 : 0;
    const plotH = height - pad.top - pad.bottom - macdHeight;
    const plotW = width - pad.left - pad.right;
    context.clearRect(0, 0, width, height);
    context.strokeStyle = "rgba(160,190,228,.11)";
    context.lineWidth = 1;
    for (let index = 0; index <= 4; index += 1) {
      const y = pad.top + (plotH * index) / 4;
      context.beginPath();
      context.moveTo(pad.left, y);
      context.lineTo(width - pad.right, y);
      context.stroke();
    }
    if (mode === "minute") {
      const points = rows as IntradayPackage["data"];
      const values = points.map((row) => row.price).filter(Number.isFinite);
      const low = Math.min(...values),
        high = Math.max(...values);
      const span = high - low || 1;
      const priceH = plotH * 0.78;
      const drawLine = (series: number[], color: string, dashed = false) => {
        context.save();
        context.strokeStyle = color;
        context.lineWidth = 1.5;
        context.setLineDash(dashed ? [5, 4] : []);
        context.beginPath();
        series.forEach((value, index) => {
          const x = pad.left + (index * plotW) / Math.max(1, series.length - 1);
          const y = pad.top + ((high - value) / span) * priceH;
          if (index) context.lineTo(x, y);
          else context.moveTo(x, y);
        });
        context.stroke();
        context.restore();
      };
      drawLine(
        points.map((row) => row.price),
        "#00e0ff",
      );
      const average = (packageData as IntradayPackage).average ?? [];
      if (average.length) drawLine(average, "#b9c5d4", true);
      const maxVolume = Math.max(
        ...points.map((row) => Number(row.volume ?? 0)),
        1,
      );
      const step = plotW / Math.max(1, points.length);
      points.forEach((row, index) => {
        const bar = (Number(row.volume ?? 0) / maxVolume) * plotH * 0.18;
        context.fillStyle =
          index === 0 || row.price >= points[index - 1].price
            ? "rgba(255,92,107,.52)"
            : "rgba(34,211,238,.52)";
        context.fillRect(
          pad.left + index * step,
          pad.top + plotH - bar,
          Math.max(1, step * 0.72),
          bar,
        );
      });
    } else {
      const candles = rows as KlineRow[];
      const values = candles.flatMap((row) => [row.high, row.low]);
      const low = Math.min(...values),
        high = Math.max(...values),
        span = high - low || 1;
      const step = plotW / candles.length,
        body = Math.max(1, Math.min(8, step * 0.62));
      const yOf = (value: number) => pad.top + ((high - value) / span) * plotH;
      candles.forEach((row, index) => {
        const x = pad.left + (index + 0.5) * step,
          color = row.close >= row.open ? "#ff5c6b" : "#22d3ee";
        context.strokeStyle = color;
        context.fillStyle = color;
        context.beginPath();
        context.moveTo(x, yOf(row.high));
        context.lineTo(x, yOf(row.low));
        context.stroke();
        const top = yOf(Math.max(row.open, row.close)),
          bottom = yOf(Math.min(row.open, row.close));
        context.fillRect(x - body / 2, top, body, Math.max(1, bottom - top));
      });
      const indicators = (packageData as KlinePackage).indicators;
      const colors: Record<string, string> = {
        ma5: "#f7d36b",
        ma10: "#a88cff",
        ma20: "#7de0b5",
        ma60: "#f6a36f",
      };
      for (const key of ["ma5", "ma10", "ma20", "ma60"] as const) {
        if (!layers[key]) continue;
        const series = indicators?.[key] ?? [];
        context.strokeStyle = colors[key];
        context.lineWidth = 1.15;
        context.beginPath();
        let started = false;
        series.forEach((value, index) => {
          if (value == null) return;
          const x = pad.left + (index + 0.5) * step,
            y = yOf(value);
          if (started) context.lineTo(x, y);
          else {
            context.moveTo(x, y);
            started = true;
          }
        });
        context.stroke();
      }
      if (layers.macd && indicators?.macd) {
        const macd = indicators.macd,
          top = pad.top + plotH + 8,
          bottom = height - pad.bottom,
          center = (top + bottom) / 2,
          max = Math.max(
            ...macd.histogram.map(Math.abs),
            ...macd.dif.map(Math.abs),
            ...macd.dea.map(Math.abs),
            0.0001,
          );
        macd.histogram.forEach((value, index) => {
          const x = pad.left + (index + 0.5) * step;
          context.fillStyle =
            value >= 0 ? "rgba(255,92,107,.7)" : "rgba(34,211,238,.7)";
          const bar = ((value / max) * (bottom - top)) / 2;
          context.fillRect(
            x - Math.max(1, body / 3),
            center - bar,
            Math.max(1, body * 0.66),
            bar,
          );
        });
        for (const [series, color] of [
          [macd.dif, "#f7d36b"],
          [macd.dea, "#a88cff"],
        ] as const) {
          context.strokeStyle = color;
          context.beginPath();
          series.forEach((value, index) => {
            const x = pad.left + (index + 0.5) * step,
              y = center - ((value / max) * (bottom - top)) / 2;
            if (index) context.lineTo(x, y);
            else context.moveTo(x, y);
          });
          context.stroke();
        }
      }
    }
  }, [layers, mode, packageData, rows]);
  function locate(clientX: number, clientY: number) {
    const canvas = canvasRef.current;
    if (!canvas || !rows.length) return;
    const rect = canvas.getBoundingClientRect();
    const x = Math.max(44, Math.min(rect.width - 14, clientX - rect.left));
    const index = Math.max(
      0,
      Math.min(
        rows.length - 1,
        Math.round(
          ((x - 44) / Math.max(1, rect.width - 58)) * (rows.length - 1),
        ),
      ),
    );
    setCursor({
      x,
      y: Math.max(16, Math.min(rect.height - 25, clientY - rect.top)),
      index,
    });
  }
  const selected = cursor
    ? (rows[cursor.index] as Record<string, unknown>)
    : null;
  if (!rows.length)
    return (
      <div className={styles.candlePlaceholder}>
        <span>真实图表数据不足</span>
      </div>
    );
  return (
    <div
      className={styles.marketCanvas}
      onMouseMove={(event) => locate(event.clientX, event.clientY)}
      onMouseLeave={() => setCursor(null)}
      onTouchMove={(event) => {
        const point = event.touches[0];
        if (point) locate(point.clientX, point.clientY);
      }}
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.key === "Escape") setCursor(null);
      }}
    >
      <canvas ref={canvasRef} />
      {cursor && (
        <div className={styles.crosshair} aria-hidden>
          <i className={styles.crossV} style={{ left: cursor.x }} />
          <i className={styles.crossH} style={{ top: cursor.y }} />
          <span
            style={{
              left: Math.min(cursor.x + 8, 520),
              top: Math.max(5, cursor.y - 34),
            }}
          >
            {String(selected?.date ?? selected?.time ?? "")} ·{" "}
            {mode === "minute"
              ? Number(selected?.price).toFixed(2)
              : `O ${Number(selected?.open).toFixed(2)} H ${Number(selected?.high).toFixed(2)} L ${Number(selected?.low).toFixed(2)} C ${Number(selected?.close).toFixed(2)}`}
          </span>
        </div>
      )}
    </div>
  );
}
