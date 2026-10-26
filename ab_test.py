import os
import datetime
import json
import time
import requests
import warnings
import akshare as ak
import pandas as pd
import numpy as np
from daily_agent_tx import run_daily_check as run_tx
from daily_agent_bs import run_daily_check_bs as run_bs
from research_core.config import get_provider_config
from research_core.llm_client import chat_completion_text

warnings.filterwarnings('ignore')

_PROVIDER = get_provider_config("volcengine")
API_KEY = _PROVIDER.api_key
ENDPOINT_MODEL = _PROVIDER.model
BASE_URL = _PROVIDER.base_url
FRICTION_COST = 0.002


def get_sector(code):
    return "科技阵营" if code.startswith('688') or code.startswith('300') else "周期阵营"


def settle_predictions(pred_date, buy_date, sell_date, horizon_name):
    reports_dir = "AB_Test_Reports"
    last_dir = f"{reports_dir}/{pred_date}"
    tx_file = f"{last_dir}/tx_raw_preds.json"
    bs_file = f"{last_dir}/bs_raw_preds.json"

    if not os.path.exists(tx_file) or not os.path.exists(bs_file):
        return f"⏳ **[{horizon_name} 结算列队]** 未找到 {pred_date} 的预测档案，等待种子数据积累。\n"

    with open(tx_file, 'r', encoding='utf-8') as f:
        preds_tx = json.load(f)
    with open(bs_file, 'r', encoding='utf-8') as f:
        preds_bs = json.load(f)

    try:
        df_hs300 = ak.stock_zh_index_daily_tx(symbol="sz399300").set_index('date')
        df_cyb = ak.stock_zh_index_daily_tx(symbol="sz399006").set_index('date')
        b_dt = f"{buy_date[:4]}-{buy_date[4:6]}-{buy_date[6:]}"
        s_dt = f"{sell_date[:4]}-{sell_date[4:6]}-{sell_date[6:]}"
        hs300_buy, hs300_sell = df_hs300.loc[b_dt, 'open'], df_hs300.loc[s_dt, 'close']
        cyb_buy, cyb_sell = df_cyb.loc[b_dt, 'open'], df_cyb.loc[s_dt, 'close']
        market_pct = (((hs300_sell - hs300_buy) / hs300_buy) * 0.5 + ((cyb_sell - cyb_buy) / cyb_buy) * 0.5) * 100
    except:
        market_pct = 0.0

    report = f"### ⚖️ 【{horizon_name} 真金结算】 (预测日:{pred_date} ➔ 买入:{buy_date} ➔ 卖出:{sell_date})\n"
    report += f"> 🛡️ *已扣除 0.4% 双边摩擦 | 同期大盘基准波动：**{market_pct:.2f}%***\n\n"
    report += "| 股票 | 板块 | 真实涨跌 | 真实超额 | A组(TX)仓位 | A组赚取 | B组(BS)仓位 | B组赚取 |\n"
    report += "| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |\n"

    stats = {"TX": {"Tech": 0, "Cyc": 0, "Tot": 0}, "BS": {"Tech": 0, "Cyc": 0, "Tot": 0}}

    for code in preds_tx.keys():
        sym = f"sh{code}" if code.startswith('6') else f"sz{code}"
        try:
            df_stock = ak.stock_zh_a_hist_tx(symbol=sym, start_date=buy_date, end_date=sell_date, adjust="qfq")
            if df_stock.empty: continue

            buy_price = float(df_stock.iloc[0]['open']) * (1 + FRICTION_COST)
            sell_price = float(df_stock.iloc[-1]['close']) * (1 - FRICTION_COST)
            stock_pct = ((sell_price - buy_price) / buy_price) * 100
            real_alpha = stock_pct - market_pct

            tx_prob = preds_tx[code].get('raw_prob', 0.5)
            bs_prob = preds_bs.get(code, {}).get('raw_prob', 0.5)
            sector = get_sector(code)

            tx_w = np.clip((tx_prob - 0.50) * 4.0 * (1.5 if sector == "科技阵营" else 0.5), 0,
                           0.8) if tx_prob >= 0.53 else 0
            bs_w = np.clip((bs_prob - 0.50) * 4.0 * (2.0 if sector == "科技阵营" else 0.0), 0,
                           0.8) if bs_prob >= 0.53 else 0

            tx_earn, bs_earn = real_alpha * tx_w, real_alpha * bs_w

            if sector == "科技阵营":
                stats["TX"]["Tech"] += tx_earn;
                stats["BS"]["Tech"] += bs_earn
            else:
                stats["TX"]["Cyc"] += tx_earn;
                stats["BS"]["Cyc"] += bs_earn
            stats["TX"]["Tot"] += tx_earn;
            stats["BS"]["Tot"] += bs_earn

            report += f"| **{code}** | {sector[:2]} | {stock_pct:.2f}% | **{real_alpha:.2f}%** | {tx_w * 100:.0f}% | {tx_earn:.2f}% | {bs_w * 100:.0f}% | {bs_earn:.2f}% |\n"
        except Exception:
            continue

    report += f"\n#### 🏆 {horizon_name} 账户净值贡献榜 (扣费后真实 Alpha)\n"
    report += f"- **🔴 A组**: 总贡献 **{stats['TX']['Tot']:.2f}%** ｜ 科技组: {stats['TX']['Tech']:.2f}%，周期: {stats['TX']['Cyc']:.2f}%\n"
    report += f"- **🔵 B组**: 总贡献 **{stats['BS']['Tot']:.2f}%** ｜ 科技组: {stats['BS']['Tech']:.2f}%，周期: {stats['BS']['Cyc']:.2f}%\n\n"
    return report


def verify_all_horizons():
    try:
        df_index = ak.stock_zh_index_daily_tx(symbol="sh000001")
        recent_dates = df_index['date'].astype(str).str.replace('-', '').tolist()[-4:]
        if len(recent_dates) < 4: return "⚠️ 大盘交易日数据不足。\n"
        T_3, T_2, T_1, T_0 = recent_dates[0], recent_dates[1], recent_dates[2], recent_dates[3]
        return settle_predictions(T_1, T_0, T_0, "T+1 极短线") + "---\n\n" + settle_predictions(T_3, T_2, T_0,
                                                                                                "T+3 黄金波段")
    except Exception as e:
        return f"⚠️ 滚动结算失败: {e}\n"


def ask_ab_comparison_agent(preds_tx, preds_bs, max_retries=3):
    _PROVIDER.validate()
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    prompt = f"""
    你是一位顶级百亿量化私募的“首席策略大脑”。今日两套核心系统数据：
    🔴 【A组: TX 动态加权版】: {json.dumps(preds_tx, ensure_ascii=False)}
    🔵 【B组: BS 动态加权版】: {json.dumps(preds_bs, ensure_ascii=False)}

    撰写报告：
    ### 📊 一、全维信号扫描雷达
    | 股票代码 | 板块 | A组胜率 | A组权重偏好（四个模型胜率） | B组胜率 | B组权重偏好（四个模型胜率） | 信号状态 |
    *(状态填写“🔥双多共振”、“❄️双空共识”或“⚔️多空分歧”。共振基准线：0.53)*

    ### 🕵️ 二、逐个股深度博弈透视
    1. **逻辑对撞**：结合底层专家的胜率与动态分配的“权重偏好”，剖析模型为什么要重仓某个专家。
    2. **操作建议**：重仓出击/轻仓博弈/规避。

    ### 👑 三、终极决策中枢
    1. **倾向研判**：顺势资金流占优，还是逆势抄底占优？
    2. **采信建议**：明日仓位偏重A组还是B组，还是只打双多金股？给出资金分配基调。
    """
    payload = {"model": ENDPOINT_MODEL, "messages": [{"role": "system", "content": "冷酷犀利的量化风控官。"},
                                                     {"role": "user", "content": prompt}], "temperature": 0.25,
               "max_tokens": 5000}

    print("   [裁判 LLM] 正在深度推演 (最长等待 5 分钟)...")
    for _ in range(max_retries):
        try:
            return chat_completion_text(
                _PROVIDER, payload["messages"], temperature=0.25, max_tokens=5000,
                max_retries=1, timeout_seconds=300,
            )
        except Exception:
            time.sleep(3)
    return "❌ 接口持续超时访问被拒绝。"


def run_ab_test():
    today = datetime.datetime.now().strftime("%Y%m%d")
    folder_path = f"AB_Test_Reports/{today}"
    os.makedirs(folder_path, exist_ok=True)

    print("=" * 60)
    print(f"🚀 [双轨监控台 动态加权平均版] 启动 {today} 测试")
    print("=" * 60)

    print("\n>>> 🔴 正在拉起 [A组: TX 趋势稳健流]...")
    preds_tx, report_tx = run_tx()
    print("\n>>> 🔵 正在拉起 [B组: BS 暴力超跌流]...")
    preds_bs, report_bs = run_bs()

    with open(f"{folder_path}/tx_raw_preds.json", "w", encoding="utf-8") as f:
        json.dump(preds_tx, f, ensure_ascii=False)
    with open(f"{folder_path}/bs_raw_preds.json", "w", encoding="utf-8") as f:
        json.dump(preds_bs, f, ensure_ascii=False)

    tomorrow_table = "### 📋 【明日实盘作战指引卡】 (基于 0.53 共振雷达)\n\n| 股票 | 现价 | 板块 | 🔴 A组 | 🔵 B组 | 🔥 共振信号 |\n| :--- | :---: | :---: | :---: | :---: | :--- |\n"
    for code in sorted(set(list(preds_tx.keys()) + list(preds_bs.keys()))):
        tx_p = preds_tx.get(code, {}).get('raw_prob', 0);
        bs_p = preds_bs.get(code, {}).get('raw_prob', 0)
        price = preds_tx.get(code, {}).get('最新价格', 'N/A');
        sector = get_sector(code)[:2]

        tx_mark = f"**{tx_p * 100:.1f}%**" if tx_p >= 0.53 else f"{tx_p * 100:.1f}%"
        bs_mark = f"**{bs_p * 100:.1f}%**" if bs_p >= 0.53 else f"{bs_p * 100:.1f}%"

        if tx_p >= 0.53 and bs_p >= 0.53:
            action = "🚀 **戴维斯双击！重点加仓**"
        elif tx_p >= 0.53 and bs_p < 0.53:
            action = "🛡️ 稳健流看多，可铺底仓"
        elif tx_p < 0.53 and bs_p >= 0.53:
            action = "🛑 周期禁入 / 科技小仓搏杀"
        else:
            action = "❄️ 坚决空仓观望"
        tomorrow_table += f"| **{code}** | {price} | {sector} | {tx_mark} | {bs_mark} | {action} |\n"

    comparison_report = ask_ab_comparison_agent(preds_tx, preds_bs)
    accuracy_report = verify_all_horizons()

    try:
        with open(f"{folder_path}/1_TX_V4.4_Report.md", "w", encoding="utf-8") as f:
            f.write(report_tx)
        with open(f"{folder_path}/2_BaoStock_Report.md", "w", encoding="utf-8") as f:
            f.write(report_bs)
        with open(f"{folder_path}/3_AB_Comparison_Verdict.md", "w", encoding="utf-8") as f:
            f.write(accuracy_report + tomorrow_table + "\n\n" + comparison_report)
        print(
            "\n" + "★" * 60 + f"\n✅ 双轨影子盘监控完成！📁 报告已归档至: {folder_path}/3_AB_Comparison_Verdict.md\n" + "★" * 60)
    except Exception as e:
        print(f"❌ 报告归档失败: {e}")


if __name__ == "__main__":
    run_ab_test()
