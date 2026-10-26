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
    你是一位就职于顶级量化私募的首席策略分析师。
    你收到了一份基于4核心（XGBoost/LightGBM/CatBoost/Transformer）及动态加权融合模型输出的量化预测简报。

    【核心监控池数据】
    {json.dumps(ml_predictions, ensure_ascii=False, indent=2)}

    【核心认知】：
    1. 系统输出的“综合胜率(超额)”代表该股票在下一个交易日【跑赢上证指数（取得Alpha收益）】的概率。
    2. 新版本剔除了传统指标，引入了“波动率”、“量价相关性”、“隔夜跳空情绪”等高阶因子。
    3. 股票池呈现“哑铃型”结构：一端是科技成长阵营（科创板688、创业板300），另一端是周期/金融/制造阵营（主板600、000）。

    请务必严格按照以下4个模块撰写深度研报：

    ### 第一部分：🌍 大势与总结
    基于整体胜率分布，研判当前量化视角下的市场情绪是偏向进攻还是防守。

    ### 第二部分：⚔️ 阵营对抗分析
    明确对比“科技成长阵营”与“周期/金融阵营”的综合表现。研判当前资金正在攻击哪个阵营，哪个阵营处于弱势退潮期。

    ### 第三部分：👨‍💼 专业量化视点 (逐一个股深度解析)
    （⚠️必做：必须覆盖传入的每一支股票，绝不可遗漏！）
    - 结合其所属阵营、最新价格、综合胜率，进行定性判断。
    - 透视其“专家底牌”：对比四大底层模型的概率差异，解读分歧或共振。

    ### 第四部分：👶 实盘操作指南 (趋势交易建议)
    【核心要求】：务必结合“底层的逻辑确定”与“当前的数据交易分析”，推导并给出最核心的趋势交易建议！
    为每一只股票提供一段明确操作建议（不用专业术语）：给出“重点加仓”、“防守底仓”、“逢高减磅”、“坚决规避”等明确指示。

    严格使用 Markdown 格式排版，加粗核心结论。
    """

    payload = {
        "model": ENDPOINT_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个冷酷、严谨、具有机构操盘手决断力的量化 AI 分析师。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.35,
        "max_tokens": 3000
    }

    print("   [LLM] 正在通过原生通道直连豆包大模型，撰写深度研报...")
    for attempt in range(1, max_retries + 1):
        try:
            return chat_completion_text(_PROVIDER, payload["messages"], temperature=0.35, max_tokens=3000, max_retries=1, timeout_seconds=180)
        except Exception as e:
            if attempt == max_retries: return f"⚠️ 大模型调用失败: {e}"
            print(f"   [LLM] 第 {attempt} 次请求超时或失败，2秒后重试...")
            time.sleep(2)
    return "❌ 接口持续异常，请稍后再试。"
