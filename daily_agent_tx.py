import os
import time
import random
import datetime
import requests
import json
import warnings
import akshare as ak
import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
import catboost as cb
import joblib
import torch
import torch.nn as nn
from workbench_core.research_registry import resolve_active_model_dir
from llm_DeepSeek_tx import ask_ai_agent

warnings.filterwarnings('ignore')

# 🌟 全域列装：科技成长阵营 + 主板周期阵营
TECH_TICKERS = ['300308', '300502', '300857', '688008', '688257', '688313', '301297'] # 👈 已在此处加入 301297
MAIN_TICKERS = ['600522', '002335', '000657', '601899']
TICKERS_RAW = TECH_TICKERS + MAIN_TICKERS

# 🧱 科技阵营因子 (TX-V4.4 趋势资金流)
TECH_FEATURES = [
    'Relative_Strength', 'Return_5', 'BIAS_20', 'BIAS_60',
    'Vol_Ratio', 'Norm_ATR_14', 'Entity_Ratio', 'Boll_Width',
    'Realized_Vol_20', 'PV_Corr_10', 'Overnight_Return',
    'CMF_20', 'Trend_Strength_20'
]
# 🧱 主板阵营因子 (TX-V7 纯价格免疫流)
MAIN_FEATURES = [
    'Relative_Strength_20', 'MACD_Hist_Norm', 'Z_Score_20',
    'ATR_Ratio_14_60', 'Price_EMA_Bias_20', 'Return_5', 'Return_20',
    'Williams_R_14', 'CCI_14', 'Candle_Shape'
]


class StockTransformer(nn.Module):
    def __init__(self, input_size, seq_len=10, d_model=64, nhead=4, num_layers=2):
        super(StockTransformer, self).__init__()
        self.embedding = nn.Linear(input_size, d_model)
        self.pos_encoder = nn.Parameter(torch.randn(1, seq_len, d_model))
        encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, batch_first=True)
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.fc = nn.Linear(d_model, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x):
        x = self.embedding(x) + self.pos_encoder[:, :x.size(1), :]
        return self.sigmoid(self.fc(self.transformer(x)[:, -1, :]))


def get_market_baseline_tx():
    df_market = ak.stock_zh_index_daily_tx(symbol="sh000001")
    df_market.rename(columns={'date': 'date', 'close': 'Close'}, inplace=True)
    df_market['date'] = pd.to_datetime(df_market['date'])
    df_market['Close'] = pd.to_numeric(df_market['Close'], errors='coerce')
    df_market['Market_PctChg'] = df_market['Close'].pct_change().fillna(0)
    df_market.set_index('date', inplace=True)
    return df_market[['Market_PctChg']]


def preprocess_basic(df_raw, df_market):
    # 🌟 修复点1：加入了最全的大小写英文与中文列名映射，防止因为找不到列名导致全部填0
    col_mapping = {
        '日期': 'date', 'time': 'date',
        '开盘': 'Open', 'open': 'Open',
        '收盘': 'Close', 'close': 'Close',
        '最高': 'High', 'high': 'High',
        '最低': 'Low', 'low': 'Low',
        '成交量': 'Volume', 'volume': 'Volume', 'vol': 'Volume',
        '涨跌幅': 'PctChg', 'pct_chg': 'PctChg', 'pctChg': 'PctChg'
    }
    df = df_raw.rename(columns=col_mapping).loc[:, ~df_raw.columns.duplicated()]
    if 'PctChg' not in df.columns:
        df['PctChg'] = pd.to_numeric(df['Close'], errors='coerce').pct_change().fillna(0) * 100

    for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'PctChg']:
        df[col] = pd.to_numeric(df.get(col, 0), errors='coerce')

    df['date'] = pd.to_datetime(df['date'])
    df = df.ffill()
    if df['PctChg'].abs().max() > 10.0: df['PctChg'] /= 100.0
    df.set_index('date', inplace=True)
    df = df.join(df_market, how='left')
    df['Market_PctChg'] = df['Market_PctChg'].fillna(0)
    return df


def build_features_tech(df):
    df['Relative_Strength'] = df['PctChg'] - df['Market_PctChg']
    df['MA20'], df['MA60'] = df['Close'].rolling(20).mean(), df['Close'].rolling(60).mean()
    df['BIAS_20'], df['BIAS_60'] = (df['Close'] - df['MA20']) / (df['MA20'] + 1e-8), (df['Close'] - df['MA60']) / (
                df['MA60'] + 1e-8)
    df['Return_5'] = df['Close'] / (df['Close'].shift(5) + 1e-8) - 1
    df['Prev_Close'] = df['Close'].shift(1).fillna(df['Close'])
    df['TR'] = df[['High', 'Prev_Close']].max(axis=1) - df[['Low', 'Prev_Close']].min(axis=1)
    df['Norm_ATR_14'] = df['TR'].rolling(14).mean() / (df['Close'] + 1e-8)
    df['Vol_Ratio'] = df['Volume'] / (df['Volume'].rolling(20).mean() + 1e-8)
    df['HL_Range'] = df['High'] - df['Low'] + 1e-8
    df['Entity_Ratio'] = abs(df['Close'] - df['Open']) / (df['HL_Range'] + 1e-8)
    df['Boll_Width'] = (df['Close'].rolling(window=20).std() * 2) / (df['MA20'] + 1e-8)
    df['Realized_Vol_20'] = df['PctChg'].rolling(20).std() * np.sqrt(252)
    df['PV_Corr_10'] = df['Close'].rolling(10).corr(df['Volume']).fillna(0)
    df['Overnight_Return'] = df['Open'] / (df['Prev_Close'] + 1e-8) - 1
    clv = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / (df['HL_Range'] + 1e-8)
    df['CMF_20'] = (clv * df['Volume']).rolling(20).sum() / (df['Volume'].rolling(20).sum() + 1e-8)
    df['Trend_Strength_20'] = (df['Close'] - df['Close'].shift(20)) / (
                df['High'].rolling(20).max() - df['Low'].rolling(20).min() + 1e-8)
    return df.replace([np.inf, -np.inf], np.nan).dropna()


def build_features_main(df):
    df['Return_5'] = df['Close'] / (df['Close'].shift(5) + 1e-8) - 1
    df['Return_20'] = df['Close'] / (df['Close'].shift(20) + 1e-8) - 1
    df['Relative_Strength_20'] = df['Return_20'] - df['Market_PctChg'].fillna(0).rolling(20).sum()
    ema12, ema26 = df['Close'].ewm(span=12, adjust=False).mean(), df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Hist_Norm'] = ((ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()) / (df['Close'] + 1e-8)
    df['MA20'] = df['Close'].rolling(20).mean()
    df['Z_Score_20'] = (df['Close'] - df['MA20']) / (df['Close'].rolling(20).std() + 1e-8)
    df['Price_EMA_Bias_20'] = df['Close'] / df['Close'].ewm(span=20, adjust=False).mean() - 1
    df['Prev_Close'] = df['Close'].shift(1).fillna(df['Close'])
    df['TR'] = df[['High', 'Prev_Close']].max(axis=1) - df[['Low', 'Prev_Close']].min(axis=1)
    df['ATR_Ratio_14_60'] = df['TR'].rolling(14).mean() / (df['TR'].rolling(60).mean() + 1e-8)
    highest_14, lowest_14 = df['High'].rolling(14).max(), df['Low'].rolling(14).min()
    df['Williams_R_14'] = (highest_14 - df['Close']) / (highest_14 - lowest_14 + 1e-8) * -100
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    df['CCI_14'] = (tp - tp.rolling(14).mean()) / (0.015 * tp.rolling(14).std() + 1e-8)
    df['Candle_Shape'] = (df['Close'] - df['Low']) / (df['High'] - df['Low'] + 1e-8)
    return df.replace([np.inf, -np.inf], np.nan).dropna()


def get_position_tier(prob):
    return "S档 🚀" if prob >= 0.65 else "A档 📈" if prob >= 0.58 else "B档 ⚖️" if prob >= 0.53 else "C/D档 🛑"


def run_daily_check(user_holdings=""):
    now = datetime.datetime.now()
    print(f"🔄 启动 [TX 全域海陆空融合版] | {now.strftime('%H:%M:%S')}")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    predictions = {}

    try:
        df_market = get_market_baseline_tx()
    except Exception:
        return {}, "大盘拉取失败"

    for raw_code in TICKERS_RAW:
        try:
            sym = f"sh{raw_code}" if raw_code.startswith('6') else f"sz{raw_code}"
            df_raw = None
            for _ in range(3):
                try:
                    time.sleep(random.uniform(1.0, 2.5))
                    df_raw = ak.stock_zh_a_hist_tx(symbol=sym, start_date="20230101", adjust="qfq")
                    break
                except:
                    time.sleep(2.0)

            if df_raw is None or len(df_raw) < 100:
                raise ValueError("历史数据不足100天或API拉取为空")

            df_base = preprocess_basic(df_raw, df_market)
            is_tech = raw_code in TECH_TICKERS
            df = build_features_tech(df_base) if is_tech else build_features_main(df_base)
            features = TECH_FEATURES if is_tech else MAIN_FEATURES
            model_dir = "models_tx" if is_tech else resolve_active_model_dir("tx", "models_tx_v7", "models_tx_v7")

            if len(df) < 10:
                raise ValueError("特征计算后有效行数不足10天 (常见于全部停牌)")

            latest_close = float(df['Close'].iloc[-1])

            scaler = joblib.load(f"{model_dir}/{raw_code}_scaler.pkl")
            X_scaled = scaler.transform(df[features].values)
            X_last, X_seq = X_scaled[-1:], X_scaled[-10:]

            m_xgb = xgb.Booster() if is_tech else xgb.XGBClassifier()
            m_xgb.load_model(f"{model_dir}/{raw_code}_xgb.json")
            p_xgb = float(m_xgb.predict(xgb.DMatrix(X_last))[0]) if is_tech else float(
                m_xgb.predict_proba(X_last)[0, 1])

            p_lgb = float(joblib.load(f"{model_dir}/{raw_code}_lgb.pkl").predict_proba(X_last)[0, 1])
            m_cat = cb.CatBoostClassifier()
            m_cat.load_model(f"{model_dir}/{raw_code}_cat.cbm")
            p_cat = float(m_cat.predict_proba(X_last)[0, 1])

            tf_model = StockTransformer(len(features), seq_len=10).to(device)
            tf_model.load_state_dict(
                torch.load(f"{model_dir}/{raw_code}_tf.pth", map_location=device, weights_only=True))
            tf_model.eval()
            with torch.no_grad():
                p_tf = float(tf_model(torch.FloatTensor(X_seq).unsqueeze(0).to(device)).item())

            meta_model = joblib.load(f"{model_dir}/{raw_code}_meta.pkl")
            raw_coefs = np.abs(meta_model.coef_[0])
            weights = raw_coefs / (np.sum(raw_coefs) + 1e-8)
            final_prob = float(np.dot(weights, np.array([p_xgb, p_lgb, p_cat, p_tf])))

            predictions[raw_code] = {
                "最新价格": round(latest_close, 2), "综合胜率(超额)": f"{final_prob * 100:.1f}%",
                "专家底牌": f"XGB:{p_xgb * 100:.0f}%|LGB:{p_lgb * 100:.0f}%|CAT:{p_cat * 100:.0f}%|TF:{p_tf * 100:.0f}%",
                "模型权重": f"XGB:{weights[0] * 100:.0f}%|LGB:{weights[1] * 100:.0f}%|CAT:{weights[2] * 100:.0f}%|TF:{weights[3] * 100:.0f}%",
                "档位": get_position_tier(final_prob), "raw_prob": final_prob, "sector": "科技" if is_tech else "主板"
            }
        except Exception as e:
            # 🌟 修复点2：将异常状态存下，后续会在控制台显性打印！
            predictions[raw_code] = {"状态": f"异常: {str(e)}"}

    valid_preds = {k: v for k, v in predictions.items() if "raw_prob" in v}
    error_preds = {k: v for k, v in predictions.items() if "raw_prob" not in v}

    print("\n" + "★" * 80)
    print("【🚀 科技成长阵营 (游资接力流)】")
    for c in sorted([k for k in valid_preds if valid_preds[k]['sector'] == '科技'],
                    key=lambda x: valid_preds[x]['raw_prob'], reverse=True):
        v = valid_preds[c]
        print(f"[{c}] 价: ¥{v['最新价格']:<5} | 胜率: {v['综合胜率(超额)']:<5} | {v['档位']} | 底牌: {v['专家底牌']}")

    print("\n【🛡️ 主板蓝筹阵营 (纯价反转流)】")
    for c in sorted([k for k in valid_preds if valid_preds[k]['sector'] == '主板'],
                    key=lambda x: valid_preds[x]['raw_prob'], reverse=True):
        v = valid_preds[c]
        print(f"[{c}] 价: ¥{v['最新价格']:<5} | 胜率: {v['综合胜率(超额)']:<5} | {v['档位']} | 底牌: {v['专家底牌']}")

    # 🌟 修复点3：将报错信息直接打在屏幕上，拒绝“蒙在鼓里”！
    if error_preds:
        print("\n⚠️ [警报] 以下股票拉取或计算发生异常：")
        for err_code, err_info in error_preds.items():
            print(f"   - {err_code}: {err_info['状态']}")

    print("★" * 80)

    report = ask_ai_agent(valid_preds, {}, user_holdings) if valid_preds else "无有效数据"
    print("\n" + report + "\n" + "★" * 80)
    return valid_preds, report


if __name__ == "__main__":
    holdings = input("\n>>> 👨‍💼 指挥官，请输入全域持仓情况 (直接回车跳过):\n> ")
    run_daily_check(holdings)
