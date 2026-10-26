import requests
import json
import time
from research_core.config import get_provider_config
from research_core.llm_client import chat_completion_text

_PROVIDER = get_provider_config("volcengine")
API_KEY = _PROVIDER.api_key
ENDPOINT_MODEL = _PROVIDER.model
BASE_URL = _PROVIDER.base_url

def ask_ai_agent(ml_predictions, max_retries=3):
    _PROVIDER.validate()
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

    prompt = f"""
    【机密输入：TX-V4.4 纯血量价引擎测算数据】
    {json.dumps(ml_predictions, ensure_ascii=False, indent=2)}

    你现在的身份是顶级量化私募的“首席基金经理”。
    本模型已装载全新的【CMF_20资金流量】(衡量主力吸筹与派发) 与【Trend_Strength_20趋势强度】因子。
    股票池呈现“哑铃型”结构：一端是科技成长（688/300），另一端是周期金融（600/000）。

    请极其严格地按以下结构输出今日复盘研报：

    ### 🌍 一、大势定调与阵营博弈
    1. **总体情绪**：一句话总结当前量化系统给出的市场进攻/防守基调。
    2. **阵营对抗**：科技线和周期线目前谁在抽血？谁在被抛弃？

    ### 🕵️ 二、全标的 X 光扫描 (逐只分析，绝不可遗漏)
    针对每一只输入的股票，依次进行：
    - **【核心数据】**：当前价格与超额胜率。
    - **【专家底牌透视】**：对比树模型(XGB/LGB)与神经网络(TF)的分歧与共振，推导日内游资与中长线机构的态度。
    - **【资金面推理】**：结合该股的胜率，推测其 CMF (资金收集) 与趋势连贯性的健康度。

    ### 🎯 三、操作指令双语版 (最终趋势交易建议)
    【核心要求】：务必结合“底层的逻辑确定”与“当前的数据交易分析”，得出最终的趋势交易建议！
    为每一只股票分别提供以下两句简短的指令：
    - **👨‍💼 机构专业版**：例如“底层逻辑支撑，数据呈多头排列，建议沿均线低吸建仓”、“逻辑破位，逢冲高减磅”。
    - **👶 小白说人话版**：例如“主力还在吸筹，死拿别卖！”、“AI都看不懂了，千万别碰！”。

    排版要求：冷酷、专业、层次分明，使用 Markdown 格式，股票代码加粗。
    """

    payload = {
        "model": ENDPOINT_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个冷酷果断、精通向下兼容表达（能讲专业术语也能说大白话）的量化操盘手。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.25,
        "max_tokens": 3000
    }

    print("   [LLM] 战术中枢正在深度思考全局博弈与个股策略，请耐心等待 (最高180s)...")
    for attempt in range(1, max_retries + 1):
        try:
            return chat_completion_text(_PROVIDER, payload["messages"], temperature=0.25, max_tokens=3000, max_retries=1, timeout_seconds=180)
        except Exception as e:
            if attempt == max_retries: return f"⚠️ 指挥中心连接彻底失败: {e}"
            print(f"   [LLM] 信号波动，尝试第 {attempt+1} 次重连...")
            time.sleep(3)
    return "❌ 接口超时访问被拒绝。"
