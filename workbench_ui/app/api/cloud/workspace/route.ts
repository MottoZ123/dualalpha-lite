import { readWorkspace, writeWorkspace } from "../../../../db/workspace";
import { createDefaultWorkspace, normalizeWorkspace } from "../../../../lib/workspace";
import { readLimitedJson } from "../../../../lib/server-security";
import { AccessError, enforceRateLimit, requireInviteAccess, writeAudit } from "../../../../lib/access-control";
import { cloudOwner } from "../../../../lib/cloud-owner";

export async function GET(request: Request) {
  try {
    const access = await requireInviteAccess(request);
    await enforceRateLimit(request, "workspace-read", 240, 60 * 60, access.subject);
    const viewer = cloudOwner(request, access);
    return Response.json({ workspace: await readWorkspace(viewer.id), viewer: { name: viewer.name, email: viewer.email }, localPreview: viewer.localPreview });
  } catch (error) {
    const status = error instanceof AccessError ? error.status : 500;
    return Response.json({ error: error instanceof Error ? error.message : "读取工作区失败" }, { status });
  }
}

export async function PUT(request: Request) {
  try {
    const access = await requireInviteAccess(request);
    await enforceRateLimit(request, "workspace-write", 120, 60 * 60, access.subject);
    const viewer = cloudOwner(request, access);
    const payload = await readLimitedJson(request, 750_000);
    const workspace = normalizeWorkspace(payload.workspace);
    const stored = await writeWorkspace(viewer.id, workspace);
    await writeAudit(request, "workspace_write", true, `schema:${stored.schemaVersion}`, access.subject);
    return Response.json({ workspace: stored });
  } catch (error) {
    const status = error instanceof AccessError ? error.status : 400;
    return Response.json({ error: error instanceof Error ? error.message : "保存工作区失败" }, { status });
  }
}

export async function DELETE(request: Request) {
  try {
    const access = await requireInviteAccess(request);
    await enforceRateLimit(request, "workspace-reset", 10, 60 * 60, access.subject);
    const viewer = cloudOwner(request, access);
    const workspace = await writeWorkspace(viewer.id, createDefaultWorkspace());
    await writeAudit(request, "workspace_reset", true, "", access.subject);
    return Response.json({ workspace });
  } catch (error) {
    const status = error instanceof AccessError ? error.status : 500;
    return Response.json({ error: error instanceof Error ? error.message : "重置工作区失败" }, { status });
  }
}
