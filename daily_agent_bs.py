import os
import baostock as bs
import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
import catboost as cb
import joblib
import torch
import torch.nn as nn
import warnings
from llm_DeepSeek_bs import ask_ai_agent

warnings.filterwarnings('ignore')

# 🌟 全域列装：科技成长阵营 + 主板周期阵营
# 🌟 全域列装：科技成长阵营 + 主板周期阵营
TECH_TICKERS = ['300308', '300502', '300857', '688008', '688257', '688313', '301297'] # 👈 已在此处加入 301297
MAIN_TICKERS = ['600522', '002335', '000657', '601899']
TICKERS_RAW = TECH_TICKERS + MAIN_TICKERS

# 🧱 科技阵营因子 (BS 成本偏离流)
TECH_FEATURES = [
    'Relative_Strength', 'Turn', 'Return_5', 'BIAS_20', 'BIAS_60',
    'Vol_Ratio', 'Norm_ATR_14', 'Entity_Ratio', 'Price_Cost_Bias',
    'Boll_Width', 'Realized_Vol_20', 'PV_Corr_10', 'Overnight_Return'
]
# 🧱 主板阵营因子 (BS-V6 量价共振流)
MAIN_FEATURES = [
    'Relative_Strength_20', 'MACD_Hist_Norm', 'Z_Score_20',
    'ATR_Ratio_14_60', 'Vol_Surge_60', 'Price_VWAP_Bias',
    'MFI_14', 'Amihud_Illiquidity', 'Return_5', 'Return_20'
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


def preprocess_basic(df_raw, df_market):
    df = df_raw.rename(
        columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume', 'amount': 'Amount',
                 'turn': 'Turn', 'pctChg': 'PctChg'})
    for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'Amount', 'Turn', 'PctChg']: df[col] = pd.to_numeric(
        df.get(col, 0), errors='coerce')
    df = df.ffill()
    if df['PctChg'].abs().max() > 10.0: df['PctChg'] /= 100.0
    if df['Turn'].abs().max() > 10.0: df['Turn'] /= 100.0
    df['date'] = pd.to_datetime(df['date'])
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
    df['ATR_14'], df['Norm_ATR_14'] = df['TR'].rolling(14).mean(), df['TR'].rolling(14).mean() / (df['Close'] + 1e-8)
    df['Vol_Ratio'] = df['Volume'] / (df['Volume'].rolling(20).mean() + 1e-8)
    df['HL_Range'] = df['High'] - df['Low'] + 1e-8
    df['Entity_Ratio'] = abs(df['Close'] - df['Open']) / df['HL_Range']
    df['VWAP'] = df['Amount'] / (df['Volume'] + 1e-8)
    df['Price_Cost_Bias'] = df['Close'] / (df['VWAP'] + 1e-8) - 1
    df['Boll_Width'] = (df['Close'].rolling(window=20).std() * 2) / (df['MA20'] + 1e-8)
    df['Realized_Vol_20'] = df['PctChg'].rolling(20).std() * np.sqrt(252)
    df['PV_Corr_10'] = df['Close'].rolling(10).corr(df['Volume']).fillna(0)
    df['Overnight_Return'] = df['Open'] / (df['Prev_Close'] + 1e-8) - 1
    return df.replace([np.inf, -np.inf], np.nan).dropna()


def build_features_main(df):
    df['Return_5'] = df['Close'] / (df['Close'].shift(5) + 1e-8) - 1
    df['Return_20'] = df['Close'] / (df['Close'].shift(20) + 1e-8) - 1
    df['Relative_Strength_20'] = df['Return_20'] - df['Market_PctChg'].fillna(0).rolling(20).sum()
    ema12, ema26 = df['Close'].ewm(span=12, adjust=False).mean(), df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Hist_Norm'] = ((ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()) / (df['Close'] + 1e-8)
    df['MA20'] = df['Close'].rolling(20).mean()
    df['Z_Score_20'] = (df['Close'] - df['MA20']) / (df['Close'].rolling(20).std() + 1e-8)
    df['Vol_Surge_60'] = df['Volume'] / (df['Volume'].rolling(60).mean() + 1e-8)
    df['Prev_Close'] = df['Close'].shift(1).fillna(df['Close'])
    df['TR'] = df[['High', 'Prev_Close']].max(axis=1) - df[['Low', 'Prev_Close']].min(axis=1)
    df['ATR_Ratio_14_60'] = df['TR'].rolling(14).mean() / (df['TR'].rolling(60).mean() + 1e-8)
    df['Price_VWAP_Bias'] = df['Close'] / (
                (df['Amount'].rolling(20).sum() / (df['Volume'].rolling(20).sum() + 1e-8)) + 1e-8) - 1
    df['Amihud_Illiquidity'] = (abs(df['PctChg']) / (df['Amount'] / 1e8 + 1e-8)).rolling(20).mean()
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    pf = np.where(tp > tp.shift(1), tp * df['Volume'], 0).flatten()
    nf = np.where(tp < tp.shift(1), tp * df['Volume'], 0).flatten()
    df['MFI_14'] = 100 - (100 / (1 + pd.Series(pf, index=df.index).rolling(14).sum() / (
                pd.Series(nf, index=df.index).rolling(14).sum() + 1e-8)))
    return df.replace([np.inf, -np.inf], np.nan).dropna()


def run_daily_check_bs(user_holdings=""):
    print(f"🔄 启动 [BS 全域海陆空融合版]")
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    predictions = {}

    bs.login()
    rs_market = bs.query_history_k_data_plus("sh.000001", "date,pctChg", start_date="2023-01-01", frequency="d",
                                             adjustflag="2")
    data_list = []
    while (rs_market.error_code == '0') & rs_market.next(): data_list.append(rs_market.get_row_data())
    df_market = pd.DataFrame(data_list, columns=rs_market.fields)
    df_market.rename(columns={'pctChg': 'Market_PctChg'}, inplace=True)
    df_market['Market_PctChg'] = pd.to_numeric(df_market['Market_PctChg'], errors='coerce') / 100.0
    df_market.set_index('date', inplace=True)

    for code in TICKERS_RAW:
        try:
            sym = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
            rs = bs.query_history_k_data_plus(sym, "date,open,high,low,close,volume,amount,turn,pctChg",
                                              start_date="2023-01-01", frequency="d", adjustflag="2")
            data_list = []
            while (rs.error_code == '0') & rs.next(): data_list.append(rs.get_row_data())
            df_raw = pd.DataFrame(data_list, columns=rs.fields)
            if len(df_raw) < 50: continue

            df_base = preprocess_basic(df_raw, df_market)

            # 🌟 核心：判断阵营，调用不同特征和模型文件夹
            is_tech = code in TECH_TICKERS
            df = build_features_tech(df_base) if is_tech else build_features_main(df_base)
            features = TECH_FEATURES if is_tech else MAIN_FEATURES
            model_dir = "models" if is_tech else "models_bs_v6"

            if len(df) < 10: continue
            latest_close = float(df['Close'].iloc[-1])

            scaler = joblib.load(f"{model_dir}/{code}_scaler.pkl")
            X_scaled = scaler.transform(df[features].values)
            X_last, X_seq = X_scaled[-1:], X_scaled[-10:]

            m_xgb = xgb.Booster() if is_tech else xgb.XGBClassifier()
            m_xgb.load_model(f"{model_dir}/{code}_xgb.json")
            p_xgb = float(m_xgb.predict(xgb.DMatrix(X_last))[0]) if is_tech else float(
                m_xgb.predict_proba(X_last)[0, 1])

            p_lgb = float(joblib.load(f"{model_dir}/{code}_lgb.pkl").predict_proba(X_last)[0, 1])
            m_cat = cb.CatBoostClassifier()
            m_cat.load_model(f"{model_dir}/{code}_cat.cbm")
            p_cat = float(m_cat.predict_proba(X_last)[0, 1])

            tf_model = StockTransformer(len(features), seq_len=10).to(device)
            tf_model.load_state_dict(torch.load(f"{model_dir}/{code}_tf.pth", map_location=device, weights_only=True))
            tf_model.eval()
            with torch.no_grad():
                p_tf = float(tf_model(torch.FloatTensor(X_seq).unsqueeze(0).to(device)).item())

            meta_model = joblib.load(f"{model_dir}/{code}_meta.pkl")
            raw_coefs = np.abs(meta_model.coef_[0])
            weights = raw_coefs / (np.sum(raw_coefs) + 1e-8)
            final_prob = float(np.dot(weights, np.array([p_xgb, p_lgb, p_cat, p_tf])))

            predictions[code] = {
                "最新价格": round(latest_close, 2), "综合胜率(超额)": f"{final_prob * 100:.1f}%",
                "专家底牌": f"XGB:{p_xgb * 100:.0f}%|LGB:{p_lgb * 100:.0f}%|CAT:{p_cat * 100:.0f}%|TF:{p_tf * 100:.0f}%",
                "模型权重": f"XGB:{weights[0] * 100:.0f}%|LGB:{weights[1] * 100:.0f}%|CAT:{weights[2] * 100:.0f}%|TF:{weights[3] * 100:.0f}%",
                "档位": "S档" if final_prob >= 0.65 else "A档" if final_prob >= 0.58 else "B档" if final_prob >= 0.53 else "C/D档",
                "raw_prob": final_prob, "sector": "科技" if is_tech else "主板"
            }
        except Exception as e:
            predictions[code] = {"状态": f"异常: {e}"}

    bs.logout()
    valid_preds = {k: v for k, v in predictions.items() if "raw_prob" in v}
    report = ask_ai_agent(valid_preds, user_holdings) if valid_preds else "无有效预测数据。"

    print("\n" + "★" * 80)
    for code in sorted([k for k in valid_preds], key=lambda x: valid_preds[x]['raw_prob'], reverse=True):
        v = valid_preds[code]
        print(
            f"[{code}]({v['sector']}) 价: ¥{v['最新价格']:<6} | 跑赢大盘概率: {v['综合胜率(超额)']:<6} | {v['档位']}\n         👉 底牌: {v['专家底牌']}")
    print("-" * 80 + "\n" + report + "\n" + "★" * 80)
    return valid_preds, report


if __name__ == "__main__":
    holdings = input("\n>>> 👨‍💼 指挥官，请输入您的当前持仓情况 (直接回车跳过):\n> ")
    run_daily_check_bs(holdings)