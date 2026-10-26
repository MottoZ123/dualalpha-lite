"""主板 TX 训练。"""

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
from sklearn.linear_model import LogisticRegression
import joblib
import warnings
import matplotlib.pyplot as plt
import seaborn as sns
import shap

warnings.filterwarnings('ignore')
np.random.seed(42)
torch.manual_seed(42)

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

#  TX 专属 V7 (纯价格引擎) 隔离目录
os.makedirs("models_tx_v7", exist_ok=True)
os.makedirs("factor_reports_tx_v7", exist_ok=True)

TICKERS_RAW = ['600522', '002335', '000657', '601899']

#  V7 纯价格原生因子 (彻底弃用 Volume，100% 依赖高精度价格数据)
FEATURE_COLS = [
    'Relative_Strength_20', 'MACD_Hist_Norm', 'Z_Score_20',
    'ATR_Ratio_14_60', 'Price_EMA_Bias_20', 'Return_5', 'Return_20',
    'Williams_R_14', 'CCI_14', 'Candle_Shape'  #  新晋三大纯价格火力
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
    col_mapping = {
        '日期': 'date', 'time': 'date', '开盘': 'Open', 'open': 'Open',
        '收盘': 'Close', 'close': 'Close', '最高': 'High', 'high': 'High', '最低': 'Low', 'low': 'Low',
        '涨跌幅': 'PctChg', 'pct_chg': 'PctChg'
    }
    df = df.rename(columns=col_mapping).loc[:, ~df.columns.duplicated()]

    # 我们甚至不再强制要求提取 Volume
    for c in ['Open', 'High', 'Low', 'Close', 'PctChg']:
        df[c] = pd.to_numeric(df.get(c, 0), errors='coerce')
    if df['PctChg'].abs().max() > 10.0: df['PctChg'] /= 100.0

    df.index = pd.to_datetime(df['date'])
    df = df.join(df_market, how='left').ffill()

    # 1. 动量与相对强度
    df['Return_5'] = df['Close'] / (df['Close'].shift(5) + 1e-8) - 1
    df['Return_20'] = df['Close'] / (df['Close'].shift(20) + 1e-8) - 1
    df['Relative_Strength_20'] = df['Return_20'] - df['Market_PctChg'].fillna(0).rolling(20).sum()

    # 2. 核心趋势与位置
    ema12, ema26 = df['Close'].ewm(span=12, adjust=False).mean(), df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Hist_Norm'] = ((ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()) / (df['Close'] + 1e-8)

    df['MA20'] = df['Close'].rolling(20).mean()
    df['Z_Score_20'] = (df['Close'] - df['MA20']) / (df['Close'].rolling(20).std() + 1e-8)
    df['Price_EMA_Bias_20'] = df['Close'] / df['Close'].ewm(span=20, adjust=False).mean() - 1

    # 3. 波动率属性
    df['Prev_Close'] = df['Close'].shift(1).fillna(df['Close'])
    df['TR'] = df[['High', 'Prev_Close']].max(axis=1) - df[['Low', 'Prev_Close']].min(axis=1)
    df['ATR_Ratio_14_60'] = df['TR'].rolling(14).mean() / (df['TR'].rolling(60).mean() + 1e-8)

    #  4. 新晋纯价三剑客 (完全免疫 Volume 瘫痪)
    # 威廉指标 (超买超卖)
    highest_14 = df['High'].rolling(14).max()
    lowest_14 = df['Low'].rolling(14).min()
    df['Williams_R_14'] = (highest_14 - df['Close']) / (highest_14 - lowest_14 + 1e-8) * -100

    # CCI 顺势指标 (均值偏离极端度)
    tp = (df['High'] + df['Low'] + df['Close']) / 3
    df['CCI_14'] = (tp - tp.rolling(14).mean()) / (0.015 * tp.rolling(14).std() + 1e-8)

    # 裸 K 下影线强度 (日内反转信号)
    df['Candle_Shape'] = (df['Close'] - df['Low']) / (df['High'] - df['Low'] + 1e-8)

    df['Target'] = (df['PctChg'].shift(-1) > df['Market_PctChg'].shift(-1)).astype(int)
    return df.replace([np.inf, -np.inf], np.nan).dropna()


def train(tickers=None, feature_cols=None, output_root=None):
    tickers = [str(code).strip() for code in (tickers or TICKERS_RAW) if str(code).strip()]
    selected_features = [name for name in (feature_cols or FEATURE_COLS) if name in FEATURE_COLS]
    if len(selected_features) < 3:
        raise ValueError("TX training requires at least three compatible factors")
    if output_root:
        output_root = os.fspath(output_root)
        model_dir = os.path.join(output_root, "models_tx_v7")
        report_dir = os.path.join(output_root, "factor_reports_tx_v7")
    else:
        model_dir = "models_tx_v7"
        report_dir = "factor_reports_tx_v7"
    os.makedirs(model_dir, exist_ok=True)
    os.makedirs(report_dir, exist_ok=True)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"🚀 V7 纯价格引擎 TX 炼丹炉点火 | 硬件: {device}")

    try:
        df_m = ak.stock_zh_index_daily_tx(symbol="sh000001")
        df_m['Market_PctChg'] = df_m['close'].astype(float).pct_change()
        df_market = df_m.set_index(pd.to_datetime(df_m['date']))[['Market_PctChg']]
    except Exception as e:
        print(f"❌ 大盘拉取失败: {e}")
        return

    for code in tickers:
        sym = f"sh{code}" if code.startswith('6') else f"sz{code}"
        print(f"\n⏳ 正在提炼无量纲原生数据 [{code}]...")
        try:
            df_raw = ak.stock_zh_a_hist_tx(symbol=sym, start_date="20180101",
                                           end_date=datetime.datetime.now().strftime("%Y%m%d"), adjust="qfq")
            if len(df_raw) < 200: continue

            df = build_features(df_raw, df_market)
            X, y = df[selected_features].values, df['Target'].values

            idx = int(len(X) * 0.8)
            scaler = StandardScaler().fit(X[:idx])
            X_s = scaler.transform(X)

            m1 = xgb.XGBClassifier(max_depth=3);
            m1.fit(X_s[:idx], y[:idx])
            m2 = lgb.LGBMClassifier(max_depth=3, verbose=-1);
            m2.fit(X_s[:idx], y[:idx])
            m3 = cb.CatBoostClassifier(depth=3, verbose=0);
            m3.fit(X_s[:idx], y[:idx])

            net = StockTransformer(len(selected_features)).to(device)
            X_t = torch.FloatTensor(np.array([X_s[:idx][i - 10:i] for i in range(10, idx)])).to(device)
            y_t = torch.FloatTensor(y[10:idx]).unsqueeze(1).to(device)
            opt = torch.optim.Adam(net.parameters(), lr=0.001);
            crit = nn.BCELoss()
            for _ in range(80): opt.zero_grad(); crit(net(X_t), y_t).backward(); opt.step()

            p1, p2, p3 = m1.predict_proba(X_s[idx:])[10:, 1], m2.predict_proba(X_s[idx:])[10:, 1],\
            m3.predict_proba(X_s[idx:])[10:, 1]
            net.eval()
            with torch.no_grad():
                p4 = net(torch.FloatTensor(np.array([X_s[idx:][i - 10:i] for i in range(10, len(X_s[idx:]))])).to(
                    device)).cpu().numpy().flatten()

            meta = LogisticRegression(C=1.0).fit(np.c_[p1, p2, p3, p4], y[idx + 10:])

            joblib.dump(StandardScaler().fit(X), os.path.join(model_dir, f"{code}_scaler.pkl"))
            joblib.dump(meta, os.path.join(model_dir, f"{code}_meta.pkl"))
            m1.fit(X_s, y);
            m1.save_model(os.path.join(model_dir, f"{code}_xgb.json"))
            m2.fit(X_s, y);
            joblib.dump(m2, os.path.join(model_dir, f"{code}_lgb.pkl"))
            m3.fit(X_s, y);
            m3.save_model(os.path.join(model_dir, f"{code}_cat.cbm"))
            torch.save(net.state_dict(), os.path.join(model_dir, f"{code}_tf.pth"))

            print(f"   -> 📊 绘制 [{code}] V7 纯价验尸报告...")
            tree_imp = ((m2.feature_importances_ / (np.sum(m2.feature_importances_) + 1e-8)) * 100 + (
                        m3.get_feature_importance() / (np.sum(m3.get_feature_importance()) + 1e-8)) * 100) / 2
            shap_v = shap.TreeExplainer(m2).shap_values(X_s[-250:])
            if isinstance(shap_v, list): shap_v = shap_v[1]

            fig = plt.figure(figsize=(18, 12))
            ax1 = plt.subplot(2, 2, 1)
            ax1.pie((np.abs(meta.coef_[0]) / (np.sum(np.abs(meta.coef_[0])) + 1e-8)) * 100,
                    labels=['XGBoost', 'LightGBM', 'CatBoost', 'Transformer'], autopct='%1.1f%%', explode=(0.05,) * 4,
                    shadow=True, colors=sns.color_palette('Set2')[0:4])
            ax1.set_title(f"[{code}] 专家权重分布 (V7 纯价格版)", fontsize=14, fontweight='bold')

            ax2 = plt.subplot(2, 2, 2)
            tr = sorted(zip(selected_features, tree_imp), key=lambda x: x[1])
            sns.barplot(x=[x[1] for x in tr], y=[x[0] for x in tr], ax=ax2, palette="viridis")
            ax2.set_title(f"[{code}] V7 原生因子重要性", fontsize=14, fontweight='bold')

            ax3 = plt.subplot(2, 1, 2)
            plt.sca(ax3);
            plt.title(f"[{code}] 因子博弈沙盘 (100% 免疫 Volume 瘫痪)", fontsize=14, fontweight='bold', pad=20)
            shap.summary_plot(shap_v, X_s[-250:], feature_names=selected_features, show=False)
            plt.tight_layout();
            plt.savefig(os.path.join(report_dir, f"{code}_V7_TX_SHAP.png"), dpi=150, bbox_inches='tight');
            plt.close(fig)
            print(f"   ✅ [{code}] TX 纯价战车炼制完毕！")
        except Exception as e:
            print(f"   ❌ [{code}] 失败: {e}")

    return {"status": "completed", "stocks": tickers, "factors": selected_features, "model_dir": model_dir, "report_dir": report_dir}


if __name__ == "__main__": train()
