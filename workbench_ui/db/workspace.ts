import { env } from "cloudflare:workers";
import { createDefaultWorkspace, normalizeWorkspace, type ResearchWorkspace } from "../lib/workspace";

type D1Statement = {
  bind(...values: unknown[]): D1Statement;
  first<T>(): Promise<T | null>;
  run(): Promise<unknown>;
};

type D1Database = {
  prepare(sql: string): D1Statement;
};

function database(): D1Database {
  const db = env.DB as D1Database | undefined;
  if (!db) throw new Error("D1 binding DB is unavailable");
  return db;
}

async function ensureSchema(db: D1Database) {
  await db.prepare(`
    CREATE TABLE IF NOT EXISTS research_workspaces (
      owner_id TEXT PRIMARY KEY,
      payload TEXT NOT NULL,
      updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
  `).run();
}

export async function readWorkspace(ownerId: string): Promise<ResearchWorkspace> {
  const db = database();
  await ensureSchema(db);
  const row = await db.prepare("SELECT payload FROM research_workspaces WHERE owner_id = ? LIMIT 1").bind(ownerId).first<{ payload: string }>();
  if (!row) return createDefaultWorkspace();
  try {
    return normalizeWorkspace(JSON.parse(row.payload));
  } catch {
    return createDefaultWorkspace();
  }
}

export async function writeWorkspace(ownerId: string, workspace: ResearchWorkspace): Promise<ResearchWorkspace> {
  const db = database();
  await ensureSchema(db);
  const normalized = normalizeWorkspace({ ...workspace, updatedAt: new Date().toISOString() });
  await db.prepare(`
    INSERT INTO research_workspaces (owner_id, payload, updated_at)
    VALUES (?, ?, CURRENT_TIMESTAMP)
    ON CONFLICT(owner_id) DO UPDATE SET payload = excluded.payload, updated_at = CURRENT_TIMESTAMP
  `).bind(ownerId, JSON.stringify(normalized)).run();
  return normalized;
}
