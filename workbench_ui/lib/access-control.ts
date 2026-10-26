import { env } from "cloudflare:workers";

const COOKIE_NAME = "__Host-xuanshu_access";
const SESSION_SECONDS = 60 * 60 * 24 * 30;

type D1Statement = {
  bind(...values: unknown[]): D1Statement;
  first<T>(): Promise<T | null>;
  run(): Promise<unknown>;
};

type D1Database = { prepare(sql: string): D1Statement };

export type InviteAccess = {
  granted: boolean;
  subject: string;
  expiresAt?: number;
  localPreview: boolean;
};

export class AccessError extends Error {
  status: number;
  constructor(message: string, status = 401) {
    super(message);
    this.status = status;
  }
}

function runtimeValue(name: string) {
  const runtime = env as unknown as Record<string, unknown>;
  return typeof runtime[name] === "string" ? String(runtime[name]).trim() : "";
}

function database(): D1Database {
  const db = (env as unknown as Record<string, unknown>).DB as D1Database | undefined;
  if (!db) throw new AccessError("访问数据库暂不可用", 503);
  return db;
}

function isLocal(request: Request) {
  const hostname = new URL(request.url).hostname;
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

function cookieValue(request: Request, name: string) {
  const cookie = request.headers.get("cookie") ?? "";
  for (const part of cookie.split(";")) {
    const [key, ...value] = part.trim().split("=");
    if (key === name) return value.join("=");
  }
  return "";
}

function toBase64Url(bytes: Uint8Array) {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
}

function fromBase64Url(value: string) {
  const padding = (4 - (value.length % 4)) % 4;
  const padded = value.replace(/-/g, "+").replace(/_/g, "/") + "=".repeat(padding);
  const binary = atob(padded);
  return Uint8Array.from(binary, (character) => character.charCodeAt(0));
}

async function hmac(value: string, secret: string) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return new Uint8Array(await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(value)));
}

async function sha256Hex(value: string) {
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)));
  return [...digest].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function inviteIdentities() {
  const raw = runtimeValue("INVITE_CODE_IDENTITIES");
  if (!raw) return new Map<string, string>();
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return new Map(Object.entries(parsed).flatMap(([hash, subject]) => (
      /^[a-f0-9]{64}$/i.test(hash) && typeof subject === "string" && /^[A-Za-z0-9:_-]{3,80}$/.test(subject)
        ? [[hash.toLowerCase(), subject] as const]
        : []
    )));
  } catch {
    throw new AccessError("邀请码身份映射配置无效", 503);
  }
}

export async function workspacePublicId(subject: string) {
  return `WS-${(await sha256Hex(`xuanshu:${subject}`)).slice(0, 12).toUpperCase()}`;
}

function equalBytes(left: Uint8Array, right: Uint8Array) {
  if (left.length !== right.length) return false;
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) difference |= left[index] ^ right[index];
  return difference === 0;
}

async function ensureAccessSchema(db: D1Database) {
  await db.prepare(`
    CREATE TABLE IF NOT EXISTS api_rate_limits (
      identifier TEXT NOT NULL,
      scope TEXT NOT NULL,
      window_start INTEGER NOT NULL,
      request_count INTEGER NOT NULL DEFAULT 0,
      PRIMARY KEY (identifier, scope, window_start)
    )
  `).run();
  await db.prepare(`
    CREATE TABLE IF NOT EXISTS access_audit_events (
      id TEXT PRIMARY KEY,
      subject TEXT NOT NULL,
      event_type TEXT NOT NULL,
      success INTEGER NOT NULL,
      detail TEXT NOT NULL DEFAULT '',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
  `).run();
}

async function requestIdentity(request: Request) {
  const forwarded = request.headers.get("cf-connecting-ip") || request.headers.get("x-forwarded-for")?.split(",")[0] || "unknown";
  return `ip:${(await sha256Hex(forwarded.trim())).slice(0, 20)}`;
}

export async function enforceRateLimit(request: Request, scope: string, limit: number, windowSeconds: number, subject?: string) {
  if (isLocal(request)) return;
  const db = database();
  await ensureAccessSchema(db);
  const identifier = subject || await requestIdentity(request);
  const windowStart = Math.floor(Date.now() / 1000 / windowSeconds) * windowSeconds;
  await db.prepare(`
    INSERT INTO api_rate_limits (identifier, scope, window_start, request_count)
    VALUES (?, ?, ?, 1)
    ON CONFLICT(identifier, scope, window_start)
    DO UPDATE SET request_count = request_count + 1
  `).bind(identifier, scope.slice(0, 80), windowStart).run();
  const row = await db.prepare("SELECT request_count FROM api_rate_limits WHERE identifier = ? AND scope = ? AND window_start = ? LIMIT 1")
    .bind(identifier, scope.slice(0, 80), windowStart).first<{ request_count: number }>();
  if ((row?.request_count ?? 0) > limit) throw new AccessError("请求过于频繁，请稍后再试", 429);
}

export async function writeAudit(request: Request, eventType: string, success: boolean, detail = "", subject?: string) {
  try {
    if (isLocal(request)) return;
    const db = database();
    await ensureAccessSchema(db);
    const identity = subject || await requestIdentity(request);
    await db.prepare("INSERT INTO access_audit_events (id, subject, event_type, success, detail) VALUES (?, ?, ?, ?, ?)")
      .bind(crypto.randomUUID(), identity.slice(0, 160), eventType.slice(0, 80), success ? 1 : 0, detail.replace(/sk-[A-Za-z0-9._-]+/gi, "[REDACTED]").slice(0, 240)).run();
  } catch {
    // Auditing must not reveal secrets or turn a successful user request into a failure.
  }
}

export async function createInviteToken(subject = crypto.randomUUID()) {
  const secret = runtimeValue("INVITE_COOKIE_SECRET");
  if (secret.length < 32) throw new AccessError("邀请码服务尚未完成安全配置", 503);
  const payload = toBase64Url(new TextEncoder().encode(JSON.stringify({ sub: subject, exp: Math.floor(Date.now() / 1000) + SESSION_SECONDS })));
  const signature = toBase64Url(await hmac(payload, secret));
  return `${payload}.${signature}`;
}

export async function inviteAccessFromRequest(request: Request): Promise<InviteAccess> {
  if (isLocal(request)) return { granted: true, subject: "local-preview", localPreview: true };
  const sitesUserId = request.headers.get("oai-authenticated-user-id")?.trim();
  if (sitesUserId) {
    return { granted: true, subject: `sites:${sitesUserId}`, localPreview: false };
  }
  if (runtimeValue("PUBLIC_ACCESS_ENABLED") !== "1") return { granted: false, subject: "", localPreview: false };
  const secret = runtimeValue("INVITE_COOKIE_SECRET");
  const token = cookieValue(request, COOKIE_NAME);
  if (!secret || !token.includes(".")) return { granted: false, subject: "", localPreview: false };
  try {
    const [payload, providedSignature] = token.split(".", 2);
    const expectedSignature = await hmac(payload, secret);
    if (!equalBytes(expectedSignature, fromBase64Url(providedSignature))) return { granted: false, subject: "", localPreview: false };
    const parsed = JSON.parse(new TextDecoder().decode(fromBase64Url(payload))) as { sub?: string; exp?: number };
    if (!parsed.sub || !parsed.exp || parsed.exp <= Math.floor(Date.now() / 1000)) return { granted: false, subject: "", localPreview: false };
    return { granted: true, subject: parsed.sub, expiresAt: parsed.exp, localPreview: false };
  } catch {
    return { granted: false, subject: "", localPreview: false };
  }
}

export async function requireInviteAccess(request: Request) {
  const access = await inviteAccessFromRequest(request);
  if (!access.granted) throw new AccessError("请输入有效邀请码后继续", 401);
  return access;
}

export async function redeemInvite(request: Request, rawCode: string) {
  const code = rawCode.trim().toUpperCase();
  if (!/^[A-Z0-9-]{8,80}$/.test(code)) {
    await enforceRateLimit(request, "invite-redeem-failure", 8, 15 * 60);
    await writeAudit(request, "invite_redeem", false, "invalid_format");
    throw new AccessError("邀请码格式不正确", 400);
  }
  const identities = inviteIdentities();
  if (!identities.size) throw new AccessError("个人邀请码服务尚未配置", 503);
  const candidate = await sha256Hex(code);
  let subject = "";
  for (const [expected, mappedSubject] of identities) {
    if (equalBytes(new TextEncoder().encode(candidate), new TextEncoder().encode(expected))) subject = mappedSubject;
  }
  const accepted = Boolean(subject);
  if (!accepted) {
    await enforceRateLimit(request, "invite-redeem-failure", 8, 15 * 60);
    await writeAudit(request, "invite_redeem", false, "rejected");
    throw new AccessError("邀请码无效", 403);
  }
  await writeAudit(request, "invite_redeem", true, "accepted");
  return { token: await createInviteToken(subject), subject };
}

export function inviteCookie(token: string) {
  return `${COOKIE_NAME}=${token}; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=${SESSION_SECONDS}`;
}

export function clearInviteCookie() {
  return `${COOKIE_NAME}=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0`;
}
