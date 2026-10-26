import { AccessError, enforceRateLimit, requireInviteAccess, writeAudit } from "../../../../../lib/access-control";
import { readLimitedJson, redactSensitive, validateOutboundUrl } from "../../../../../lib/server-security";

const ALLOWED_PATHS = new Set([
  "/api/health", "/api/ready", "/api/all", "/api/realtime", "/api/instruments/search", "/api/intraday", "/api/kline",
  "/api/rsi-margin", "/api/news", "/api/us", "/api/portfolio/capabilities",
  "/api/research/factors", "/api/research/factor-presets", "/api/research/dual-track/latest", "/api/research/backtests",
  "/api/research/jobs", "/api/research/models", "/api/research/models/promote",
  "/api/research/models/tx/rollback", "/api/research/models/bs/rollback", "/api/jobs",
  "/api/market-flows", "/api/valuations", "/api/margin", "/api/limit-pools",
  "/api/fund", "/api/macro", "/api/fx", "/api/us-futures", "/api/investor-accounts",
  "/api/buffett-history", "/api/cross-market-impact", "/api/upstream-status",
  "/api/config/status", "/api/capabilities", "/api/llm/stock-analysis",
  "/api/extensions/vibe/status",
]);

export async function POST(request: Request) {
  let subject = "";
  try {
    const access = await requireInviteAccess(request);
    subject = access.subject;
    await enforceRateLimit(request, "rich-context", 360, 60 * 60, subject);
    const body = await readLimitedJson(request, 40_000);
    const base = validateOutboundUrl(String(body.baseUrl ?? ""), request);
    const path = String(body.path ?? "");
    if (!ALLOWED_PATHS.has(path)) throw new Error("该 Rich Core 接口未列入安全白名单");
    const key = String(body.apiKey ?? "").trim();
    const method = String(body.method ?? "GET").toUpperCase();
    if (!new Set(["GET", "POST"]).has(method)) throw new Error("只允许 GET / POST");
    const writable = new Set(["/api/research/factors", "/api/research/models/promote", "/api/research/models/tx/rollback", "/api/research/models/bs/rollback", "/api/jobs", "/api/llm/stock-analysis"]);
    if (method === "POST" && !writable.has(path)) throw new Error("该 Rich Core 接口不允许写入");
    const params = body.params && typeof body.params === "object" ? body.params as Record<string, unknown> : {};
    const url = new URL(path, base);
    for (const [name, raw] of Object.entries(params)) {
      if (!["code", "codes", "q", "period", "limit", "day", "kind", "mode"].includes(name)) continue;
      const value = String(raw).slice(0, 80);
      if (value) url.searchParams.set(name, value);
    }
    const response = await fetch(url, {
      method,
      headers: { ...(key ? { Authorization: `Bearer ${key}` } : {}), ...(method === "POST" ? { "Content-Type": "application/json" } : {}) },
      body: method === "POST" ? JSON.stringify(body.payload ?? {}) : undefined,
      signal: AbortSignal.timeout(path === "/api/llm/stock-analysis" ? 180_000 : path === "/api/all" || path === "/api/jobs" ? 30_000 : 15_000),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = result && typeof result === "object" && typeof (result as Record<string, unknown>).detail === "string" ? String((result as Record<string, unknown>).detail) : `Rich Core 返回 HTTP ${response.status}`;
      throw new Error(detail.slice(0, 300));
    }
    const serialized = JSON.stringify(result);
    if (serialized.length > 500_000) throw new Error("Rich Core 返回内容过大");
    await writeAudit(request, "rich_context", true, path, subject);
    return Response.json({ ok: true, result });
  } catch (error) {
    await writeAudit(request, "rich_context", false, redactSensitive(error), subject);
    const status = error instanceof AccessError ? error.status : 400;
    return Response.json({ ok: false, error: redactSensitive(error) || "Rich Core 读取失败" }, { status });
  }
}
