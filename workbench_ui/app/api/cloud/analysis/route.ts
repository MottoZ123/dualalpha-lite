import { callOpenAICompatibleDetailed, readLimitedJson, redactSensitive } from "../../../../lib/server-security";
import { AccessError, enforceRateLimit, requireInviteAccess, writeAudit } from "../../../../lib/access-control";

export async function POST(request: Request) {
  let subject = "";
  try {
    const access = await requireInviteAccess(request);
    subject = access.subject;
    await enforceRateLimit(request, "llm-analysis", 40, 24 * 60 * 60, subject);
    const body = await readLimitedJson(request);
    const completion = await callOpenAICompatibleDetailed(request, {
      apiKey: String(body.apiKey ?? ""),
      baseUrl: String(body.baseUrl ?? ""),
      model: String(body.model ?? ""),
      provider: String(body.provider ?? ""),
      system: String(body.system ?? ""),
      user: String(body.user ?? ""),
      maxTokens: 2400,
    });
    await writeAudit(request, "llm_analysis", true, `provider:${String(body.provider ?? "custom").slice(0, 40)}`, subject);
    return Response.json({ ok: true, report: completion.text, usage: completion.usage });
  } catch (error) {
    await writeAudit(request, "llm_analysis", false, redactSensitive(error), subject);
    const status = error instanceof AccessError ? error.status : 400;
    return Response.json({ ok: false, error: redactSensitive(error) || "分析失败" }, { status });
  }
}
