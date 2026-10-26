"""BS 报告提示词。"""

import requests
import json
import time
from research_core.config import get_provider_config
from research_core.llm_client import chat_completion_text

_PROVIDER = get_provider_config("deepseek")
DEEPSEEK_CONFIG = {
    "api_key": _PROVIDER.api_key,
    "model": _PROVIDER.model,
    "url": _PROVIDER.base_url,
}

def ask_ai_agent(tech_preds, main_preds, user_holdings="", max_retries=3):
    _PROVIDER.validate()
    headers = {"Authorization": f"Bearer {DEEPSEEK_CONFIG['api_key']}", "Content-Type": "application/json"}
    holdings_text = f"\n    【指挥官当前实盘持仓状况】：{user_holdings}\n" if user_holdings.strip() else ""

    pool_data = {
        "🚀 科技成长阵营 (创业板/科创板)": tech_preds,
        "🛡️ 主板蓝筹阵营 (资源/海缆/算力)": main_preds
    }

    prompt = f"""
    【机密输入：BS 双擎量价共振测算数据】
    {json.dumps(pool_data, ensure_ascii=False, indent=2)}
    {holdings_text}

    你现在的身份是顶级量化私募的“首席基金经理”。你面前的数据来自两个精准的量价引擎：
    1. 【科技成长引擎】：依赖 Price_Cost_Bias 成本偏离与 Entity_Ratio，专吃恐慌错杀与错杀修复。
    2. 【主板蓝筹引擎】：V6 纯净量价引擎，依赖 Vol_Surge (量能异动) 和 VWAP 均价，捕捉主力机构的隐秘放量吸筹动作。

    ⚠️ 【置信度最高级警报】：
    - 600522 (中天科技)：在主板左侧模型中历史胜率偏低，因为它的趋势连贯性极强，破位往往是真出货。点评该股必须提示“该标的不适合盲目左侧抄底，系统给出的胜率仅供参考，若无大级别量能配合应坚决观望”。

    请严格按以下结构输出今日复盘研报：

    ### 🌍 一、全域资金博弈定调
    对比“科技阵营”与“主板阵营”的总体胜率，研判当前市场的跷跷板效应。资金是在疯狂进攻科技，还是在向主板周期避险？

    ### ⚔️ 二、科技成长列阵扫描 (游资主升浪)
    逐个分析科技股。透视专家底牌和权重（XGB/LGB/CAT/TF），推测主力吸筹深度与趋势爆发力。

    ### 🛡️ 三、主板蓝筹列阵扫描 
    逐个分析主板股。透视专家底牌和权重（XGB/LGB/CAT/TF）利用能量异动和成本分离，评估并预测大资金建仓状态。（务必包含对 600522 的置信度审查！）

    ### 🎯 四、T+1/T+5 双栖操作指令（以表格形式呈现）
    先对每一支股票结合当前数据分析定性
    再为每一只股票提供简短明确的指令（请严格结合数据分析，不论是科技版还是周期股都没必要强行参与）：
    - 若实盘做 T+1：预期次日溢价空间及防守纪律。
    - 若实盘做 T+5 波段：波段持有的底线支撑位在哪里。

    ### 💼 五、指挥官专属调仓计划
    结合输入持仓，给出绝对冷血的卖出止损、做T降本或换股加仓指令。
    """

    payload = {
        "model": DEEPSEEK_CONFIG["model"],
        "messages": [{"role": "system", "content": "你是一个冷酷果断、精通全域量价分析的顶当量化黑客。"},
                     {"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 4000
    }

    print("   [LLM-BS 全域中枢] 正在穿透双阵营量价迷雾，撰写调仓指令...")
    for attempt in range(1, max_retries + 1):
        try:
            return chat_completion_text(_PROVIDER, payload["messages"], temperature=0.3, max_tokens=4000, max_retries=1, timeout_seconds=240)
        except Exception as e:
            if attempt == max_retries: return f"⚠️ 指挥中心连接失败: {e}"
            time.sleep(3)
