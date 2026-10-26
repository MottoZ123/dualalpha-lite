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

# ==========================================
# ⚙️ 双模型串行配置 (裁判中心)
# ==========================================
_VOLC_PROVIDER = get_provider_config("volcengine")
_DEEPSEEK_PROVIDER = get_provider_config("deepseek")
VOLC_CONFIG = {"api_key": _VOLC_PROVIDER.api_key, "model": _VOLC_PROVIDER.model, "url": _VOLC_PROVIDER.base_url}
DEEPSEEK_CONFIG = {"api_key": _DEEPSEEK_PROVIDER.api_key, "model": _DEEPSEEK_PROVIDER.model, "url": _DEEPSEEK_PROVIDER.base_url}
FRICTION_COST = 0.002


def get_sector(code):
    return "科技阵营" if code.startswith('688') or code.startswith('300') else "周期主板"


def settle_predictions(pred_date, buy_date, sell_date, horizon_name):
    reports_dir = "AB_Test_Reports"
    last_dir = f"{reports_dir}/{pred_date}"
    tx_file = f"{last_dir}/tx_raw_preds.json"
    bs_file = f"{last_dir}/bs_raw_preds.json"

    if not os.path.exists(tx_file) or not os.path.exists(bs_file):
        return f"⏳ **[{horizon_name} 结算列队]** 未找到 {pred_date} 的预测档案。\n"

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
    report += "| 股票 | 板块 | 真实涨跌 | 真实超额 | A组(TX)仓位 | A组赚取 | B组(BS)仓位 | B组赚取 |\n| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |\n"

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
            bs_w = np.clip((bs_prob - 0.50) * 4.0 * (2.0 if sector == "科技阵营" else 0.5), 0,
                           0.8) if bs_prob >= 0.53 else 0

            # 特殊风控：600522 强制减半仓位结算
            if code == '600522': tx_w, bs_w = tx_w * 0.5, bs_w * 0.5

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

    report += f"\n#### 🏆 {horizon_name} 账户净值贡献榜\n"
    report += f"- **🔴 A组**: 总贡献 **{stats['TX']['Tot']:.2f}%** ｜ 科技组: {stats['TX']['Tech']:.2f}%，周期: {stats['TX']['Cyc']:.2f}%\n"
    report += f"- **🔵 B组**: 总贡献 **{stats['BS']['Tot']:.2f}%** ｜ 科技组: {stats['BS']['Tech']:.2f}%，周期: {stats['BS']['Cyc']:.2f}%\n\n"
    return report


def verify_all_horizons():
    try:
        df_index = ak.stock_zh_index_daily_tx(symbol="sh000001")
        recent_dates = df_index['date'].astype(str).str.replace('-', '').tolist()[-4:]
        if len(recent_dates) < 4: return "⚠️ 大盘日数据不足。\n"
        T_3, T_2, T_1, T_0 = recent_dates[0], recent_dates[1], recent_dates[2], recent_dates[3]
        return settle_predictions(T_1, T_0, T_0, "T+1 极短线") + "---\n\n" + settle_predictions(T_3, T_2, T_0,
                                                                                                "T+3 黄金波段")
    except Exception as e:
        return f"⚠️ 滚动结算失败: {e}\n"


# ==========================================
# 🧠 升级版：冷血机构对撞大脑
# ==========================================
def ask_ab_comparison_agent(preds_tx, preds_bs, user_holdings="", max_retries=3):
    _DEEPSEEK_PROVIDER.validate()
    # 第一步：火山进行初级分歧扫描
    volc_prompt = f"请作为量化内审员，客观提炼出全域A/B两组数据的多空胜率差异点：\nA组(TX): {json.dumps(preds_tx, ensure_ascii=False)}\nB组(BS): {json.dumps(preds_bs, ensure_ascii=False)}"
    print("   [Chain-Judge] 📡 阶段 1/2：火山引擎正在扫描系统多空分歧...")
    try:
        _VOLC_PROVIDER.validate()
        volc_verdict = chat_completion_text(
            _VOLC_PROVIDER, [{"role": "user", "content": volc_prompt}],
            temperature=0.2, max_tokens=2000, max_retries=1, timeout_seconds=60,
        )
    except Exception:
        volc_verdict = "初级扫描不可用，请直接裁定。"

    holding_info = f"\n    【指挥官当前实盘持仓状况】：{user_holdings}\n" if user_holdings.strip() else ""

    # 🌟 史诗级升级的 DeepSeek 对撞提示词
    ds_prompt = f"""
    【机密输入：全域海陆空双轨对撞数据】
    🔴 A组 [TX 全域引擎]: 
    {json.dumps(preds_tx, ensure_ascii=False, indent=2)}

    🔵 B组 [BS 全域引擎]: 
    {json.dumps(preds_bs, ensure_ascii=False, indent=2)}

    【初审意见与持仓情报】：
    - 火山引擎初级扫描摘要：{volc_verdict}
    {holding_info}

    你现在的身份是顶级百亿量化私募的“全域风控决策总司令”。
    你面前的两组数据代表了A股截然不同的两套物理法则：
    1. A组(TX)：侧重“纯K线形态”与“资金流趋势”。
    2. B组(BS)：侧重“底部量能异动”与“VWAP成本偏离”。
    股票池呈现“哑铃型”结构：一端是科技成长（688/300），另一端是周期金融（600/000）。

    🚨 【最高风控警报】：
    如果数据中包含 **600522 (中天科技)**，在双轨对撞裁定时必须最高级别警戒！该股历史回测证明不适合左侧博弈，极易骗线。即使 A、B 双组达成高胜率共振，也必须提示“骗线高危，建议缩减预期仓位，快进快出 T+1，绝不轻易死拿扛单”。

    请极其严格地按以下结构输出今日【双轨对撞终极研报】：

    ### 📊 一、全维信号对撞雷达
    请输出严格排版的 Markdown 表格：
    | 股票代码 | 板块 | A组胜率 | A组主力底牌 | B组胜率 | B组主力底牌 | 对撞信号状态 |
    *(状态必须填写：“🔥双多共振”、“❄️双空共识”或“⚔️多空分歧”。共振基准线设定为 53%)*

    ### 🕵️ 二、阵营对撞深度剖析
    - **🚀 科技阵营博弈**：对比 A 组(资金流)与 B 组(成本偏离)的看法，是合力拉升还是分歧洗盘？
    - **🛡️ 主板阵营博弈**：对比 A 组(纯价形态)与 B 组(量价异动)的看法。(遇到 600522 必须严格下达置信度警示！)

    ### 🎯 三、T+1/T+5 双栖作战指引
    为每一只股票提供终极裁定：
    首先明确对于每一支股票我更应该听A组还是B组（不要盲目自信也不要盲目看空，结合当然数据与市场逻辑进行中立分析，但是给出的结果必须是确定的）
    - **⚡ T+1 闪击游资战法**：明日早盘/尾盘的短线进出与防守纪律。
    - **🛡️ T+5 波段机构战法**：如果选择底仓格局，核心防守位及波段预期在哪。

    ### 💼 四、 指挥官专属决断
    结合双轨胜率、初审意见与当前持仓情况，给出绝对冷血的卖出止损、做T降本（但请严格遵守A股T+1的规定）或换股加仓指令。(若无持仓请回答暂无动作)。
    （是操作不要局限于我的当前持仓，可以认为我有部分盈余的子弹去射击别的股票，我也可以卖出当前的的股票存子弹，也允许本日不发射。对于两套数据非常看好的股票或者看衰的股票你也需要给出相应的建议，但是要给出对应的优先级方案和风险评估）
    """

    payload_ds = {
        "model": DEEPSEEK_CONFIG["model"],
        "messages": [
            {"role": "system", "content": "你是一个冷酷果断、深谙多维因子对撞原理的全域量化操盘手。"},
            {"role": "user", "content": ds_prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 5000
    }
    print("   [Chain-Judge] 🧠 阶段 2/2：DeepSeek 正在综合双系法则产出最高作战指示...")
    for attempt in range(max_retries):
        try:
            return chat_completion_text(
                _DEEPSEEK_PROVIDER, payload_ds["messages"], temperature=0.3,
                max_tokens=5000, max_retries=1, timeout_seconds=240,
            )
        except Exception as e:
            if attempt == max_retries - 1: return f"❌ 裁判中心崩溃: {str(e)}"
            time.sleep(3)


def run_ab_test():
    today = datetime.datetime.now().strftime("%Y%m%d")
    folder_path = f"AB_Test_Reports/{today}"
    os.makedirs(folder_path, exist_ok=True)

    print("=" * 60)
    print(f"🚀 [双轨监控台 全域海陆空融合版] 启动 {today} 测试")
    print("=" * 60)

    user_holdings = input("\n>>> 👨‍💼 指挥官，请输入您的当前全域持仓情况（直接回车跳过）：\n> ")

    print("\n>>> 🔴 正在拉起 [A组: TX 科技游资+主板纯价]...")
    preds_tx, report_tx = run_tx(user_holdings)
    print("\n>>> 🔵 正在拉起 [B组: BS 科技错杀+主板量价]...")
    preds_bs, report_bs = run_bs(user_holdings)

    with open(f"{folder_path}/tx_raw_preds.json", "w", encoding="utf-8") as f:
        json.dump(preds_tx, f, ensure_ascii=False)
    with open(f"{folder_path}/bs_raw_preds.json", "w", encoding="utf-8") as f:
        json.dump(preds_bs, f, ensure_ascii=False)

    tomorrow_table = "### 📋 【明日实盘作战指引卡】\n\n| 股票 | 现价 | 板块 | 🔴 A组 | 🔵 B组 | 🔥 共振信号 |\n| :--- | :---: | :---: | :---: | :---: | :--- |\n"
    for code in sorted(set(list(preds_tx.keys()) + list(preds_bs.keys()))):
        if code == "【指挥官当前实盘持仓】": continue
        tx_p = preds_tx.get(code, {}).get('raw_prob', 0);
        bs_p = preds_bs.get(code, {}).get('raw_prob', 0)
        price = preds_tx.get(code, {}).get('最新价格', 'N/A')
        sector = get_sector(code)
        tx_mark = f"**{tx_p * 100:.1f}%**" if tx_p >= 0.53 else f"{tx_p * 100:.1f}%"
        bs_mark = f"**{bs_p * 100:.1f}%**" if bs_p >= 0.53 else f"{bs_p * 100:.1f}%"

        action = "🚀 **戴维斯双击！**" if tx_p >= 0.53 and bs_p >= 0.53 else "🛡️ 单边看多试错" if tx_p >= 0.53 or bs_p >= 0.53 else "❄️ 坚决空仓观望"
        if code == '600522': action += " (⚠️降级防守)"
        tomorrow_table += f"| **{code}** | {price} | {sector} | {tx_mark} | {bs_mark} | {action} |\n"

    comparison_report = ask_ab_comparison_agent(preds_tx, preds_bs, user_holdings)
    accuracy_report = verify_all_horizons()

    try:
        with open(f"{folder_path}/1_TX_Full_Report.md", "w", encoding="utf-8") as f:
            f.write(report_tx)
        with open(f"{folder_path}/2_BS_Full_Report.md", "w", encoding="utf-8") as f:
            f.write(report_bs)
        with open(f"{folder_path}/3_AB_Comparison_Verdict.md", "w", encoding="utf-8") as f:
            f.write(accuracy_report + tomorrow_table + "\n\n" + comparison_report)
        print(
            "\n" + "★" * 60 + f"\n✅ 双轨全域监控完成！📁 报告已归档至: {folder_path}/3_AB_Comparison_Verdict.md\n" + "★" * 60)
    except Exception as e:
        print(f"❌ 报告归档失败: {e}")


if __name__ == "__main__":
    run_ab_test()
