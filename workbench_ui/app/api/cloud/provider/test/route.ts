import { callOpenAICompatible, readLimitedJson, redactSensitive } from "../../../../../lib/server-security";
import { AccessError, enforceRateLimit, requireInviteAccess, writeAudit } from "../../../../../lib/access-control";

export async function POST(request: Request) {
  const started = Date.now();
  let subject = "";
  try {
    const access = await requireInviteAccess(request);
    subject = access.subject;
    await enforceRateLimit(request, "provider-test", 20, 60 * 60, subject);
    const body = await readLimitedJson(request, 20_000);
    await callOpenAICompatible(request, {
      apiKey: String(body.apiKey ?? ""),
      baseUrl: String(body.baseUrl ?? ""),
      model: String(body.model ?? ""),
      provider: String(body.provider ?? ""),
      system: "You are a connection checker. Reply with CONNECTED only.",
      user: "Test this API connection.",
      maxTokens: 8,
    });
    await writeAudit(request, "provider_test", true, `provider:${String(body.provider ?? "custom").slice(0, 40)}`, subject);
    return Response.json({ ok: true, latencyMs: Date.now() - started, model: String(body.model ?? "") });
  } catch (error) {
    await writeAudit(request, "provider_test", false, redactSensitive(error), subject);
    const status = error instanceof AccessError ? error.status : 400;
    return Response.json({ ok: false, error: redactSensitive(error) || "连接测试失败" }, { status });
  }
}
