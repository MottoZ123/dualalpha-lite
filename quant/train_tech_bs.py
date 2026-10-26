"""科技成长 BS 训练。"""

import os
import baostock as bs
import pandas as pd
import numpy as np
import xgboost as xgb
import lightgbm as lgb
import catboost as cb
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression  #  新增：引入逻辑回归
import joblib
import warnings
import random

random.seed(42)
np.random.seed(42)
torch.manual_seed(42)
warnings.filterwarnings('ignore')
os.makedirs("models", exist_ok=True)

TICKERS_RAW = ['300308', '300502', '300857', '688008', '688257', '688313','301297']

#  V4.3 全新黄金 13 因子 (剔除老旧指标，引入波动率与隔夜情绪)
FEATURE_COLS = [
    'Relative_Strength', 'Turn', 'Return_5', 'BIAS_20', 'BIAS_60',
    'Vol_Ratio', 'Norm_ATR_14', 'Entity_Ratio', 'Price_Cost_Bias',
    'Boll_Width', 'Realized_Vol_20', 'PV_Corr_10', 'Overnight_Return'
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
        x = self.embedding(x)
        x = x + self.pos_encoder[:, :x.size(1), :]
        out = self.transformer(x)
        out = self.fc(out[:, -1, :])
        return self.sigmoid(out)


def build_features(df, df_market):
    df.rename(
        columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume', 'amount': 'Amount',
                 'turn': 'Turn', 'pctChg': 'PctChg'}, inplace=True)
    for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'Amount', 'Turn', 'PctChg']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.ffill()
    df['Turn'], df['PctChg'] = df['Turn'] / 100.0, df['PctChg'] / 100.0
    df.set_index('date', inplace=True)

    df = df.join(df_market, how='left')
    df['Market_PctChg'] = df['Market_PctChg'].fillna(0)
    df['Relative_Strength'] = df['PctChg'] - df['Market_PctChg']

    df['MA20'], df['MA60'] = df['Close'].rolling(20).mean(), df['Close'].rolling(60).mean()
    df['BIAS_20'], df['BIAS_60'] = (df['Close'] - df['MA20']) / df['MA20'], (df['Close'] - df['MA60']) / df['MA60']
    df['Return_5'] = df['Close'] / df['Close'].shift(5) - 1

    df['Prev_Close'] = df['Close'].shift(1).fillna(df['Close'])
    df['TR'] = df[['High', 'Prev_Close']].max(axis=1) - df[['Low', 'Prev_Close']].min(axis=1)
    df['ATR_14'], df['Norm_ATR_14'] = df['TR'].rolling(14).mean(), df['TR'].rolling(14).mean() / df['Close']

    df['Vol_Ratio'] = df['Volume'] / (df['Volume'].rolling(20).mean() + 1e-8)
    df['HL_Range'] = df['High'] - df['Low'] + 1e-8
    df['Entity_Ratio'] = abs(df['Close'] - df['Open']) / df['HL_Range']

    df['VWAP'] = df['Amount'] / (df['Volume'] + 1e-8)
    df['Price_Cost_Bias'] = df['Close'] / (df['VWAP'] + 1e-8) - 1
    df['Boll_Width'] = (df['Close'].rolling(window=20).std() * 2) / (df['MA20'] + 1e-8)

    #  注入 3 大高维新因子
    df['Realized_Vol_20'] = df['PctChg'].rolling(20).std() * np.sqrt(252)  # 20日年化波动率
    df['PV_Corr_10'] = df['Close'].rolling(10).corr(df['Volume']).fillna(0)  # 10日量价相关性
    df['Overnight_Return'] = df['Open'] / (df['Prev_Close'] + 1e-8) - 1  # 隔夜跳空情绪

    if 'Target' not in df.columns:
        try:
            df['Target'] = (df['PctChg'].shift(-1) > df['Market_PctChg'].shift(-1)).astype(int)
        except:
            pass

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    return df.dropna()


def train():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"🔥 V4.3 高维因子重构版 | 硬件: {device}")

    bs.login()
    rs_market = bs.query_history_k_data_plus("sh.000001", "date,pctChg", start_date="2020-01-01", frequency="d",
                                             adjustflag="2")
    df_market = pd.DataFrame(rs_market.get_data())
    df_market.rename(columns={'pctChg': 'Market_PctChg'}, inplace=True)
    df_market['Market_PctChg'] = pd.to_numeric(df_market['Market_PctChg'], errors='coerce') / 100.0
    df_market.set_index('date', inplace=True)

    for code in TICKERS_RAW:
        sym = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
        print(f"\n🚀 正在提炼 [{code}]...")
        rs = bs.query_history_k_data_plus(sym, "date,open,high,low,close,volume,amount,turn,pctChg",
                                          start_date="2020-01-01", frequency="d", adjustflag="2")
        df_raw = pd.DataFrame(rs.get_data())

        if len(df_raw) < 150: continue

        df = build_features(df_raw, df_market)
        X, y = df[FEATURE_COLS].values, df['Target'].values

        split_idx = int(len(X) * 0.8)
        X_train, y_train = X[:split_idx], y[:split_idx]
        X_val, y_val = X[split_idx:], y[split_idx:]

        scaler_train = StandardScaler()
        X_train_scaled = scaler_train.fit_transform(X_train)
        X_val_scaled = scaler_train.transform(X_val)

        def create_seq(X_data, y_data):
            X_s = np.array([X_data[i - 10:i] for i in range(10, len(X_data))])
            return torch.FloatTensor(X_s).to(device), torch.FloatTensor(y_data[10:]).unsqueeze(1).to(device)

        X_train_seq, y_train_seq = create_seq(X_train_scaled, y_train)
        X_val_seq, _ = create_seq(X_val_scaled, y_val)

        print("   -> 训练底层专家 (80%)...")
        m_xgb = xgb.XGBClassifier(device='cuda' if torch.cuda.is_available() else 'cpu', tree_method='hist',
                                  max_depth=4, min_child_weight=3)
        m_lgb = lgb.LGBMClassifier(max_depth=4, min_child_samples=20, verbose=-1)
        m_cat = cb.CatBoostClassifier(depth=4, verbose=0)

        m_xgb.fit(X_train_scaled, y_train)
        m_lgb.fit(X_train_scaled, y_train)
        m_cat.fit(X_train_scaled, y_train)

        net = StockTransformer(len(FEATURE_COLS), seq_len=10).to(device)
        optimizer = torch.optim.Adam(net.parameters(), lr=0.001)
        criterion = nn.BCELoss()
        for epoch in range(100):
            optimizer.zero_grad()
            loss = criterion(net(X_train_seq), y_train_seq)
            loss.backward()
            optimizer.step()

        print("   -> 训练 逻辑回归 总司令 (20% OOF)...")
        p_xgb_val = m_xgb.predict_proba(X_val_scaled)[10:, 1]
        p_lgb_val = m_lgb.predict_proba(X_val_scaled)[10:, 1]
        p_cat_val = m_cat.predict_proba(X_val_scaled)[10:, 1]
        net.eval()
        with torch.no_grad():
            p_tf_val = net(X_val_seq).cpu().numpy().flatten()

        X_meta_val = np.c_[p_xgb_val, p_lgb_val, p_cat_val, p_tf_val]

        #  核心修改：剥夺树模型的反向扭曲，使用平滑的逻辑回归总司令
        meta_model = LogisticRegression(C=1.0, max_iter=1000)
        meta_model.fit(X_meta_val, y_val[10:])
        joblib.dump(meta_model, f"models/{code}_meta.pkl")

        print("   -> 生产级全量数据归位...")
        scaler_full = StandardScaler()
        X_full_scaled = scaler_full.fit_transform(X)
        joblib.dump(scaler_full, f"models/{code}_scaler.pkl")

        m_xgb.fit(X_full_scaled, y)
        m_lgb.fit(X_full_scaled, y)
        m_cat.fit(X_full_scaled, y)

        X_full_seq, y_full_seq = create_seq(X_full_scaled, y)
        net.train()
        for epoch in range(100):
            optimizer.zero_grad()
            loss = criterion(net(X_full_seq), y_full_seq)
            loss.backward()
            optimizer.step()

        m_xgb.save_model(f"models/{code}_xgb.json")
        joblib.dump(m_lgb, f"models/{code}_lgb.pkl")
        m_cat.save_model(f"models/{code}_cat.cbm")
        torch.save(net.state_dict(), f"models/{code}_tf.pth")

        print(f"   ✅ [{code}] 炼制完成 (总司令已重构)！")

    bs.logout()
    print("\n🎉 V4.3 全系模型重铸完毕！")


if __name__ == "__main__":
    train()