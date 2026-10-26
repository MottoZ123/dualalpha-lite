import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

test("ships the 本地工作台 product shell and PWA metadata", async () => {
  const [layout, page, motto, manifest, serviceWorker] = await Promise.all([
    readFile(new URL("../app/layout.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/page.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/_components/LocalWorkbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../public/manifest.webmanifest", import.meta.url), "utf8"),
    readFile(new URL("../public/sw.js", import.meta.url), "utf8"),
  ]);
  assert.match(layout, /本地工作台 · 双轨量化研究/);
  assert.match(layout, /manifest\.webmanifest/);
  assert.match(page, /<LocalWorkbench/);
  for (const group of ["MARKET", "MY DESK", "RESEARCH", "REFERENCE"]) assert.match(motto, new RegExp(group));
  assert.match(manifest, /本地工作台/);
  assert.match(serviceWorker, /url\.pathname\.startsWith\("\/api\/"\)/);
  assert.doesNotMatch(`${layout}\n${page}\n${motto}`, /codex-preview|Your site is taking shape|react-loading-skeleton/i);
});

test("renders audited macro, FX, futures and exact limit-pool contracts", async () => {
  const dashboard = await readFile(new URL("../app/_components/LocalWorkbench.tsx", import.meta.url), "utf8");
  assert.match(dashboard, /\/api\/macro/);
  assert.match(dashboard, /\/api\/fx/);
  assert.match(dashboard, /\/api\/us-futures/);
  assert.match(dashboard, /\/api\/investor-accounts/);
  assert.match(dashboard, /\/api\/buffett-history/);
  assert.match(dashboard, /\/api\/cross-market-impact/);
  assert.match(dashboard, /preciseCommercialPoolAvailable/);
  assert.match(dashboard, /精确池/);
  assert.match(dashboard, /不以现货或旧值冒充/);
  assert.match(dashboard, /H30539→399997 指数代理/);
  assert.match(dashboard, /前一美股收盘对齐下一中国交易日/);
});

test("renders baseline-first personal evidence analysis and optional LLM layer", async () => {
  const [dashboard, richContext] = await Promise.all([
    readFile(new URL("../app/_components/LocalWorkbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/api/cloud/rich/context/route.ts", import.meta.url), "utf8"),
  ]);
  assert.match(dashboard, /个人因子组合/);
  assert.match(dashboard, /腾讯财经历史行情侧重趋势与价格结构/);
  assert.match(dashboard, /BaoStock 日线历史数据侧重量价与流动性/);
  assert.match(dashboard, /导入为当前方案/);
  assert.match(dashboard, /featureProfile/);
  assert.match(dashboard, /\/api\/llm\/stock-analysis/);
  assert.match(dashboard, /设置 → 模型连接/);
  assert.match(dashboard, /PROVIDER_PRESETS/);
  assert.match(dashboard, /API Key · 当前会话/);
  assert.match(dashboard, /\/api\/cloud\/provider\/test/);
  assert.match(dashboard, /\/api\/cloud\/analysis/);
  assert.match(dashboard, /仅解释下方真实指标/);
  assert.match(dashboard, /个人自选与持仓接口/);
  assert.match(dashboard, /\/api\/instruments\/search/);
  assert.match(dashboard, /\/api\/portfolio\/capabilities/);
  assert.match(richContext, /\/api\/research\/factor-presets/);
  assert.match(richContext, /\/api\/instruments\/search/);
  assert.match(richContext, /\/api\/llm\/stock-analysis/);
  assert.match(richContext, /180_000/);
});

test("renders the PDF C.11 market overview hierarchy", async () => {
  const [dashboard, styles] = await Promise.all([
    readFile(new URL("../app/_components/LocalWorkbench.tsx", import.meta.url), "utf8"),
    readFile(new URL("../app/_components/LocalWorkbench.module.css", import.meta.url), "utf8"),
  ]);
  assert.match(dashboard, /开屏 · 市场涨跌速览/);
  assert.match(dashboard, /overviewTiles/);
  assert.match(dashboard, /宽基 \/ 行业 \/ 主题涨跌/);
  assert.match(dashboard, /今日盘面雷达/);
  assert.match(dashboard, /板块领涨 \/ 领跌与资金验证/);
  assert.match(dashboard, /const pointer = dialPoint\(pointerAngle, 51\)/);
  assert.match(dashboard, /个人持仓操作建议/);
  assert.match(styles, /grid-template-columns:repeat\(6,minmax\(0,1fr\)\)/);
  assert.match(styles, /\.indexTileUp/);
  assert.match(styles, /\.indexTileDown/);
  assert.match(styles, /\.marketPrimaryGrid/);
  assert.match(styles, /\.dialMarker/);
  assert.match(styles, /\.personalStockManager/);
});
