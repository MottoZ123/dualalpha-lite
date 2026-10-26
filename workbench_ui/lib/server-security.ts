export type Viewer = { id: string; email: string; name: string; localPreview: boolean };

export function redactSensitive(value: unknown, secrets: string[] = []) {
  let text = value instanceof Error ? value.message : String(value ?? "");
  for (const secret of secrets) {
    if (secret && secret.length >= 6) text = text.split(secret).join("[REDACTED]");
  }
  return text
    .replace(/\bsk-[A-Za-z0-9._-]{8,}\b/g, "[REDACTED]")
    .replace(/\bBearer\s+[A-Za-z0-9._~+\/-]{8,}/gi, "Bearer [REDACTED]")
    .slice(0, 300);
}

function isLocalHostname(hostname: string) {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

export function viewerFromRequest(request: Request): Viewer | null {
  const url = new URL(request.url);
  const localPreview = isLocalHostname(url.hostname);
  const email = request.headers.get("oai-authenticated-user-email")?.trim() ?? "";
  const encodedName = request.headers.get("oai-authenticated-user-full-name")?.trim() ?? "";
  const encoding = request.headers.get("oai-authenticated-user-full-name-encoding");
  let name = "";
  if (encodedName && encoding === "percent-encoded-utf-8") {
    try { name = decodeURIComponent(encodedName); } catch { name = ""; }
  }
  if (email) return { id: email.toLowerCase(), email, name: name || email.split("@")[0], localPreview: false };
  if (localPreview) return { id: "local-preview", email: "local@preview", name: "本地预览", localPreview: true };
  return null;
}

function isPrivateHostname(hostname: string) {
  const value = hostname.toLowerCase();
  if (isLocalHostname(value) || value.endsWith(".local") || value.endsWith(".internal")) return true;
  if (/^10\./.test(value) || /^192\.168\./.test(value) || /^169\.254\./.test(value)) return true;
  const match = value.match(/^172\.(\d+)\./);
  return Boolean(match && Number(match[1]) >= 16 && Number(match[1]) <= 31);
}

export function validateOutboundUrl(raw: unknown, request: Request) {
  if (typeof raw !== "string" || raw.length > 500) throw new Error("服务地址无效");
  const url = new URL(raw);
  const requestUrl = new URL(request.url);
  const localRequest = isLocalHostname(requestUrl.hostname);
  if (url.protocol !== "https:" && !(localRequest && url.protocol === "http:" && isPrivateHostname(url.hostname))) {
    throw new Error("云端连接必须使用 HTTPS 地址");
  }
  if (!localRequest && isPrivateHostname(url.hostname)) throw new Error("云端服务不能访问本机或内网地址");
  if (url.username || url.password) throw new Error("服务地址不能包含用户名或密码");
  return url;
}

export function completionUrl(raw: unknown, request: Request, provider?: string) {
  const url = validateOutboundUrl(raw, request);
  const path = url.pathname.replace(/\/+$/, "");
  if (path.endsWith("/chat/completions")) return url.toString();
  if (provider === "deepseek" || url.hostname === "api.deepseek.com") {
    url.pathname = `${path}/chat/completions`.replace(/\/\//g, "/");
    return url.toString();
  }
  if (path.endsWith("/v1") || path.endsWith("/v3") || path.endsWith("/api/v3")) {
    url.pathname = `${path}/chat/completions`;
    return url.toString();
  }
  url.pathname = `${path}/v1/chat/completions`.replace(/\/\//g, "/");
  return url.toString();
}

export type CompletionInput = {
  apiKey: string;
  baseUrl: string;
  model: string;
  provider?: string;
  system: string;
  user: string;
  maxTokens?: number;
};

function extractText(data: Record<string, unknown>) {
  const choices = data.choices as Array<Record<string, unknown>> | undefined;
  const message = choices?.[0]?.message as Record<string, unknown> | undefined;
  return typeof message?.content === "string" ? message.content : "";
}

function extractUsage(data: Record<string, unknown>) {
  const usage = data.usage as Record<string, unknown> | undefined;
  if (!usage) return undefined;
  const promptTokens = Number(usage.prompt_tokens);
  const completionTokens = Number(usage.completion_tokens);
  const totalTokens = Number(usage.total_tokens);
  return {
    promptTokens: Number.isFinite(promptTokens) ? promptTokens : undefined,
    completionTokens: Number.isFinite(completionTokens) ? completionTokens : undefined,
    totalTokens: Number.isFinite(totalTokens) ? totalTokens : undefined,
  };
}

function errorText(data: unknown, status: number) {
  if (data && typeof data === "object") {
    const error = (data as Record<string, unknown>).error;
    if (error && typeof error === "object" && typeof (error as Record<string, unknown>).message === "string") {
      return String((error as Record<string, unknown>).message).slice(0, 240);
    }
  }
  return `模型服务返回 HTTP ${status}`;
}

export async function callOpenAICompatibleDetailed(request: Request, input: CompletionInput) {
  const apiKey = input.apiKey?.trim();
  const model = input.model?.trim();
  if (!apiKey || apiKey.length < 8 || apiKey.length > 500) throw new Error("请输入有效的 API Key");
  if (!model || model.length > 160) throw new Error("请输入模型名称或推理接入点 ID");
  if (input.system.length > 20_000 || input.user.length > 40_000) throw new Error("Prompt 超过允许长度");
  const payload: Record<string, unknown> = {
    model,
    messages: [{ role: "system", content: input.system }, { role: "user", content: input.user }],
    temperature: 0.2,
    max_tokens: Math.min(Math.max(input.maxTokens ?? 1200, 8), 4000),
  };
  if (input.provider === "deepseek" && model.startsWith("deepseek-v4-")) {
    payload.thinking = { type: "enabled" };
    payload.reasoning_effort = "high";
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 45_000);
  try {
    const response = await fetch(completionUrl(input.baseUrl, request, input.provider), {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    const data = await response.json().catch(() => ({})) as Record<string, unknown>;
    if (!response.ok) throw new Error(errorText(data, response.status));
    const text = extractText(data);
    if (!text) throw new Error("模型响应缺少 message.content");
    return { text, usage: extractUsage(data) };
  } finally {
    clearTimeout(timer);
  }
}

export async function callOpenAICompatible(request: Request, input: CompletionInput) {
  return (await callOpenAICompatibleDetailed(request, input)).text;
}

export async function readLimitedJson(request: Request, maxBytes = 100_000) {
  const text = await request.text();
  if (text.length > maxBytes) throw new Error("请求内容过大");
  return JSON.parse(text) as Record<string, unknown>;
}
