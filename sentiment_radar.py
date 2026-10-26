import time
import random
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime
import json
import re
import akshare as ak
import warnings
from research_core.config import get_provider_config
from research_core.llm_client import chat_completion_text

warnings.filterwarnings('ignore')

# ==========================================
# ⚙️ 雷达配置与火山大模型接入
# ==========================================
TICKERS_RAW = ['688313', '688002', '300857', '300502', '688008', '600010', '000572', '601969', '601918']

_PROVIDER = get_provider_config("volcengine")
API_KEY = _PROVIDER.api_key
ENDPOINT_MODEL = _PROVIDER.model
BASE_URL = _PROVIDER.base_url

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
}


# ==========================================
# 🛡️ 辅助层：获取股票真实名称 (防相关性污染)
# ==========================================
def get_stock_names(ticker_list):
    print("⏳ 正在构建股票名称映射字典...")
    try:
        df_info = ak.stock_info_a_code_name()
        name_dict = dict(zip(df_info['code'], df_info['name']))
        result = {code: name_dict.get(code, f"未知股票({code})") for code in ticker_list}
        print("✅ 映射字典构建成功！")
        return result
    except Exception as e:
        print(f"⚠️ 名称字典构建失败，将使用纯代码: {e}")
        return {code: code for code in ticker_list}


# ==========================================
# 🧠 LLM 高阶情感降维引擎 (四级阶梯客观打分)
# ==========================================
def analyze_sentiment_batch_llm(code, stock_name, titles, max_retries=3):
    _PROVIDER.validate()
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    titles_str = "\n".join([f"{i + 1}. {t}" for i, t in enumerate(titles)])

    prompt = f"""
    你是一个精准、客观、具有极高金融颗粒度的 A 股量化舆情分析引擎。
    目标实体：【{stock_name} (代码: {code})】

    请对以下多条新闻进行独立的量化打分，评估其对目标实体短期股价的实质性影响。
    【新闻列表】：
    {titles_str}

    【量化评分标尺 (必须严格对应这四个层级)】：
    请输出 -1.00 到 1.00 之间的连续浮点数（保留两位小数）。

    ▶ T1级：核心重大事件 (分数: |0.60| 到 |1.00|)
      - 利好：财报超预期大增、重大重组成功、获批核心牌照、签下巨额订单。
      - 利空：立案调查、财务造假、面临退市、核心高管被捕、巨额亏损。

    ▶ T2级：公司日常经营/异动 (分数: |0.20| 到 |0.50|)
      - 利好：发布新产品、获得小额增持、回购股份、龙虎榜资金净买入。
      - 利空：大股东小幅减持、收到常规问询函、季度业绩微降。

    ▶ T3级：行业/宏观溢出效应 (分数: |0.05| 到 |0.15|)
      - (注意：不要打0分，给予情绪溢价)
      - 利好：所属行业爆发（如“板块大涨”）、出台行业利好政策，实体作为成分股跟涨。
      - 利空：宏观大跌、所属板块集体退潮。

    ▶ T4级：噪音与中性动态 (分数: -0.04 到 0.04)
      - 纯粹的盘面播报（如“今日平盘报收”、“成交量XX”）。
      - 毫无实质影响的公关文（如“参加某某展会”、“深入学习会议精神”）。
      - 如果新闻是行业盘点，且该实体仅被简单提及，未发生独立事件，一律打分为 0.00。

    【输出约束】：
    只允许输出一个 JSON 数组，数组内的浮点数严格对应输入的每条新闻。绝不允许输出任何其他解释文本！
    示例：[0.12, -0.42, 0.02, 0.75, 0.00]
    """

    payload = {
        "model": ENDPOINT_MODEL,
        "messages": [
            {"role": "system", "content": "你是一个严谨的量化打分机器。根据T1到T4标尺精确评估，只输出合法的 JSON 数组。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 100
    }

    for attempt in range(max_retries):
        try:
            result_str = chat_completion_text(
                _PROVIDER, payload["messages"], temperature=0.1, max_tokens=100,
                max_retries=1, timeout_seconds=15,
            ).strip()

            match = re.search(r'\[.*?\]', result_str, re.DOTALL)
            if match:
                scores = json.loads(match.group())
                if len(scores) == len(titles):
                    return [max(min(float(s), 1.0), -1.0) for s in scores]
            time.sleep(2)
        except Exception:
            time.sleep(2)

    return [0.0] * len(titles)


# ==========================================
# 🕷️ 资讯爬虫引擎
# ==========================================
def fetch_stock_news(code, stock_name):
    market = 'sh' if code.startswith('6') else 'sz'
    symbol = f"{market}{code}"
    url = f"https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllNewsStock/symbol/{symbol}.phtml"

    news_list = []
    print(f"\n📡 正在锁定目标 [{stock_name} ({code})]，切入资讯链路...")

    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        html_content = response.content.decode('gb2312', 'ignore')
        soup = BeautifulSoup(html_content, 'html.parser')

        news_container = soup.find('div', class_='datelist')
        if not news_container:
            print(f"⚠️ [{stock_name}] 未扫描到近期新闻。")
            return news_list

        links = news_container.find_all('a')
        titles = [link.text.strip() for link in links[:5] if link.text.strip()]

        if not titles: return news_list

        for t in titles:
            print(f"   📰 {t[:35]}...")

        scores = analyze_sentiment_batch_llm(code, stock_name, titles)

        for i, (title, score) in enumerate(zip(titles, scores)):
            if score >= 0.20:
                emotion = "🔴 实质利好 (T1/T2)"
            elif score <= -0.20:
                emotion = "🟢 实质利空 (T1/T2)"
            elif abs(score) > 0.04:
                emotion = "🟡 板块溢价 (T3)"
            else:
                emotion = "🌫️ 噪音/公关 (T4)"

            print(f"   🤖 LLM 定量: {score:>5.2f} {emotion}")

            # 时间衰减权重
            decay_weight = max(1.0 - (i * 0.15), 0.1)

            news_list.append({
                'Code': code,
                'Stock_Name': stock_name,
                'News_Title': title,
                'Raw_Score': score,
                'Weighted_Score': score * decay_weight,
                'Weight': decay_weight
            })

    except Exception as e:
        print(f"❌ [{stock_name}] 爬取或解析崩溃: {e}")

    time.sleep(random.uniform(1.0, 2.0))
    return news_list


# ==========================================
# 🎯 主程序调度聚合
# ==========================================
def run_radar():
    print("=" * 70)
    print("🕷️ [DeepEar 舆情量化雷达 V3.0 - 四级阶梯客观版] 已启动")
    print("=" * 70)

    name_map = get_stock_names(TICKERS_RAW)

    all_news = []
    for code in TICKERS_RAW:
        stock_name = name_map.get(code, code)
        news = fetch_stock_news(code, stock_name)
        all_news.extend(news)

    df_news = pd.DataFrame(all_news)

    if not df_news.empty:
        grouped = df_news.groupby(['Code', 'Stock_Name'])
        daily_sentiment = pd.DataFrame({
            'Daily_Avg_Sentiment': grouped['Weighted_Score'].sum() / grouped['Weight'].sum()
        }).reset_index()

        daily_sentiment['Daily_Avg_Sentiment'] = daily_sentiment['Daily_Avg_Sentiment'].round(3)
        daily_sentiment = daily_sentiment.sort_values(by='Daily_Avg_Sentiment', ascending=False)

        filename = f"sentiment_factor_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        daily_sentiment.to_csv(filename, index=False, encoding='utf-8-sig')

        print("\n" + "=" * 70)
        print(f"🎯 侦察完毕！大模型情绪因子已打包至: {filename}")
        print("-" * 70)
        print(daily_sentiment.to_string(index=False))
        print("=" * 70)
    else:
        print("⚠️ 全网静默，未提取到任何有效情报。")


if __name__ == "__main__":
    run_radar()
