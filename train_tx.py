import os
import datetime
import pandas as pd
import numpy as np
import akshare as ak
import xgboost as xgb
import lightgbm as lgb
import catboost as cb
import torch
import torch.nn as nn
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression  # 🌟 新增：引入逻辑回归
import joblib
import warnings
import random

warnings.filterwarnings('ignore')
random.seed(42)
np.random.seed(42)
torch.manual_seed(42)
os.makedirs("models_tx", exist_ok=True)

TICKERS_RAW = ['300308', '300502', '300857', '688008', '688257', '688313','301297']

# 🌟 V4.4 黄金因子组
FEATURE_COLS = [
    'Relative_Strength', 'Return_5', 'BIAS_20', 'BIAS_60', 'Vol_Ratio',
    'Norm_ATR_14', 'Entity_Ratio', 'Boll_Width', 'Realized_Vol_20',
    'PV_Corr_10', 'Overnight_Return', 'CMF_20', 'Trend_Strength_20'
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


def build_features(df, df_market):
    # 🛡️ 恢复最强壮的列名映射字典
    col_mapping = {
        '日期': 'date', 'date': 'date', 'time': 'date',
        '开盘': 'Open', 'open': 'Open',
        '收盘': 'Close', 'close': 'Close',
        '最高': 'High', 'high': 'High',
        '最低': 'Low', 'low': 'Low',
        '成交量': 'Volume', 'volume': 'Volume', 'vol': 'Volume',
        'amount': 'Volume',  # 修复腾讯特供 Bug
        '涨跌幅': 'PctChg', 'pct_chg': 'PctChg', 'pctChg': 'PctChg'
    }
    df = df.rename(columns=col_mapping)

    # 腾讯没返回涨跌幅，手动计算
    if 'PctChg' not in df.columns:
        df['PctChg'] = df['Close'].pct_change().fillna(0) * 100

    for c in ['Open', 'High', 'Low', 'Close', 'Volume', 'PctChg']:
        df[c] = pd.to_numeric(df[c], errors='coerce')

    df.index = pd.to_datetime(df['date'])
    df['PctChg'] = df['PctChg'] / 100.0
    df = df.join(df_market, how='left').ffill()

    # 因子矩阵计算
    df['Relative_Strength'] = df['PctChg'] - df['Market_PctChg'].fillna(0)
    df['MA20'] = df['Close'].rolling(20).mean()
    df['BIAS_20'] = (df['Close'] - df['MA20']) / (df['MA20'] + 1e-8)
    df['BIAS_60'] = (df['Close'] - df['Close'].rolling(60).mean()) / (df['Close'].rolling(60).mean() + 1e-8)
    df['Return_5'] = df['Close'] / (df['Close'].shift(5) + 1e-8) - 1
    df['Prev_Close'] = df['Close'].shift(1).fillna(df['Close'])
    df['TR'] = df[['High', 'Prev_Close']].max(axis=1) - df[['Low', 'Prev_Close']].min(axis=1)
    df['Norm_ATR_14'] = df['TR'].rolling(14).mean() / (df['Close'] + 1e-8)
    df['Vol_Ratio'] = df['Volume'] / (df['Volume'].rolling(20).mean() + 1e-8)
    df['HL_Range'] = df['High'] - df['Low'] + 1e-8
    df['Entity_Ratio'] = abs(df['Close'] - df['Open']) / df['HL_Range']
    df['Boll_Width'] = (df['Close'].rolling(20).std() * 2) / (df['MA20'] + 1e-8)
    df['Realized_Vol_20'] = df['PctChg'].rolling(20).std() * np.sqrt(252)
    df['PV_Corr_10'] = df['Close'].rolling(10).corr(df['Volume']).fillna(0)
    df['Overnight_Return'] = df['Open'] / (df['Prev_Close'] + 1e-8) - 1

    # 🌟 V4.4 核心双雄
    clv = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / df['HL_Range']
    df['CMF_20'] = (clv * df['Volume']).rolling(20).sum() / (df['Volume'].rolling(20).sum() + 1e-8)
    df['Trend_Strength_20'] = (df['Close'] - df['Close'].shift(20)) / (
                df['High'].rolling(20).max() - df['Low'].rolling(20).min() + 1e-8)

    df['Target'] = (df['PctChg'].shift(-1) > df['Market_PctChg'].shift(-1)).astype(int)
    return df.dropna()


def train():
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"🚀 V4.4 腾讯原生纯血版炼丹炉启动 | 硬件: {device}")

    df_m = ak.stock_zh_index_daily_tx(symbol="sh000001")
    df_m['Market_PctChg'] = df_m['close'].astype(float).pct_change()
    df_market = df_m.set_index(pd.to_datetime(df_m['date']))[['Market_PctChg']]

    for code in TICKERS_RAW:
        sym = f"sh{code}" if code.startswith('6') else f"sz{code}"
        print(f"\n⏳ 正在拉取并提炼 [{code}]...")
        try:
            df_raw = ak.stock_zh_a_hist_tx(symbol=sym, start_date="20200101",
                                           end_date=datetime.datetime.now().strftime("%Y%m%d"), adjust="qfq")
            df = build_features(df_raw, df_market)
            X, y = df[FEATURE_COLS].values, df['Target'].values

            idx = int(len(X) * 0.8)
            scaler = StandardScaler().fit(X[:idx])
            X_s = scaler.transform(X)
            joblib.dump(scaler, f"models_tx/{code}_scaler.pkl")

            print("   -> 训练四大底层专家...")
            m1 = xgb.XGBClassifier(max_depth=4)
            m1.fit(X_s[:idx], y[:idx])
            m2 = lgb.LGBMClassifier(max_depth=4, verbose=-1)
            m2.fit(X_s[:idx], y[:idx])
            m3 = cb.CatBoostClassifier(depth=4, verbose=0)
            m3.fit(X_s[:idx], y[:idx])

            net = StockTransformer(len(FEATURE_COLS)).to(device)
            X_t = torch.FloatTensor(np.array([X_s[:idx][i - 10:i] for i in range(10, idx)])).to(device)
            y_t = torch.FloatTensor(y[10:idx]).unsqueeze(1).to(device)
            opt = torch.optim.Adam(net.parameters(), lr=0.001)
            crit = nn.BCELoss()
            for _ in range(80):
                opt.zero_grad()
                crit(net(X_t), y_t).backward()
                opt.step()

            print("   -> 训练 逻辑回归 总司令 (OOF)...")
            p1 = m1.predict_proba(X_s[idx:])[10:, 1]
            p2 = m2.predict_proba(X_s[idx:])[10:, 1]
            p3 = m3.predict_proba(X_s[idx:])[10:, 1]

            net.eval()
            X_v = torch.FloatTensor(np.array([X_s[idx:][i - 10:i] for i in range(10, len(X_s[idx:]))])).to(device)
            with torch.no_grad():
                p4 = net(X_v).cpu().numpy().flatten()

            # 🌟 核心修改：剥夺树模型的反向扭曲，使用平滑的逻辑回归总司令
            meta = LogisticRegression(C=1.0, max_iter=1000)
            meta.fit(np.c_[p1, p2, p3, p4], y[idx + 10:])

            joblib.dump(meta, f"models_tx/{code}_meta.pkl")
            m1.save_model(f"models_tx/{code}_xgb.json")
            joblib.dump(m2, f"models_tx/{code}_lgb.pkl")
            m3.save_model(f"models_tx/{code}_cat.cbm")
            torch.save(net.state_dict(), f"models_tx/{code}_tf.pth")
            print(f"   ✅ [{code}] TX-V4.4 炼制完毕 (总司令已重构)！")

        except Exception as e:
            print(f"   ❌ [{code}] 失败: {e}")


if __name__ == "__main__":
    train()