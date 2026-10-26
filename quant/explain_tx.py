"""TX 因子解释。"""

import os
import datetime
import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
import catboost as cb
import matplotlib.pyplot as plt
import seaborn as sns
import shap
import akshare as ak
import warnings

warnings.filterwarnings('ignore')
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

TICKERS_RAW = ['688313', '300308', '300857', '300502', '688008', '688041', '300059', '601899', '601918']
FEATURE_COLS = [
    'Relative_Strength', 'Return_5', 'BIAS_20', 'BIAS_60',
    'Vol_Ratio', 'Norm_ATR_14', 'Entity_Ratio', 'Boll_Width',
    'Realized_Vol_20', 'PV_Corr_10', 'Overnight_Return',
    'CMF_20', 'Trend_Strength_20'
]
OUTPUT_DIR = "factor_reports_tx_v4.4"

def get_market_baseline_tx():
    df_market = ak.stock_zh_index_daily_tx(symbol="sh000001")
    df_market.rename(columns={'date': 'date', 'close': 'Close'}, inplace=True)
    df_market['date'] = pd.to_datetime(df_market['date'])
    df_market['Close'] = pd.to_numeric(df_market['Close'], errors='coerce')
    df_market['Market_PctChg'] = df_market['Close'].pct_change().fillna(0)
    df_market.set_index('date', inplace=True)
    return df_market[['Market_PctChg']]

def build_features(df, df_market):
    col_mapping = {
        '日期': 'date', 'date': 'date', 'time': 'date', '开盘': 'Open', 'open': 'Open',
        '收盘': 'Close', 'close': 'Close', '最高': 'High', 'high': 'High', '最低': 'Low', 'low': 'Low',
        '成交量': 'Volume', 'volume': 'Volume', 'vol': 'Volume', 'amount': 'Volume',
        '涨跌幅': 'PctChg', 'pct_chg': 'PctChg', 'pctChg': 'PctChg'
    }
    df = df.rename(columns=col_mapping)
    if 'PctChg' not in df.columns: df['PctChg'] = df['Close'].pct_change().fillna(0) * 100
    for c in ['Open', 'High', 'Low', 'Close', 'Volume', 'PctChg']: df[c] = pd.to_numeric(df[c], errors='coerce')
    df['date'] = pd.to_datetime(df['date'])
    df['PctChg'] = df['PctChg'] / 100.0
    df.set_index('date', inplace=True)
    df = df.join(df_market, how='left').ffill()

    df['Relative_Strength'] = df['PctChg'] - df['Market_PctChg'].fillna(0)
    df['MA20'], df['MA60'] = df['Close'].rolling(20).mean(), df['Close'].rolling(60).mean()
    df['BIAS_20'], df['BIAS_60'] = (df['Close'] - df['MA20']) / (df['MA20'] + 1e-8), (df['Close'] - df['MA60']) / (df['MA60'] + 1e-8)
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
    df['Trend_Strength_20'] = (df['Close'] - df['Close'].shift(20)) / (df['High'].rolling(20).max() - df['Low'].rolling(20).min() + 1e-8)
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    return df.dropna()

def generate_reports():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df_market = get_market_baseline_tx()
    today_str = datetime.datetime.now().strftime("%Y%m%d")

    for raw_code in TICKERS_RAW:
        try:
            sym = f"sh{raw_code}" if raw_code.startswith('6') else f"sz{raw_code}"
            df_raw = ak.stock_zh_a_hist_tx(symbol=sym, start_date="20230101", end_date=today_str, adjust="qfq")
            if df_raw is None or len(df_raw) < 40: continue

            df = build_features(df_raw, df_market)
            X = df[FEATURE_COLS].values[-250:]
            scaler = joblib.load(f"models_tx/{raw_code}_scaler.pkl")
            X_scaled = scaler.transform(X)

            # 恢复动态权重读取！
            meta_model = joblib.load(f"models_tx/{raw_code}_meta.pkl")
            expert_names = ['XGBoost', 'LightGBM', 'CatBoost', 'Transformer']
            if hasattr(meta_model, 'coef_'):
                raw_coefs = np.abs(meta_model.coef_[0])
                weights_pct = (raw_coefs / (np.sum(raw_coefs) + 1e-8)) * 100
            else: weights_pct = [25.0, 25.0, 25.0, 25.0]

            lgb_model = joblib.load(f"models_tx/{raw_code}_lgb.pkl")
            cat_model = cb.CatBoostClassifier()
            cat_model.load_model(f"models_tx/{raw_code}_cat.cbm")
            tree_imp_combined = ((lgb_model.feature_importances_ / np.sum(lgb_model.feature_importances_)) * 100 + (cat_model.get_feature_importance() / np.sum(cat_model.get_feature_importance())) * 100) / 2

            explainer = shap.TreeExplainer(lgb_model)
            shap_values = explainer.shap_values(X_scaled)
            if isinstance(shap_values, list): shap_values = shap_values[1]
            mean_abs_shap = np.abs(shap_values).mean(axis=0)

            df_csv = pd.DataFrame({'因子名称': FEATURE_COLS, 'Tree分裂贡献度(%)': np.round(tree_imp_combined, 2), 'SHAP平均边际影响': np.round(mean_abs_shap, 4)}).sort_values(by='SHAP平均边际影响', ascending=False)
            df_csv.to_csv(os.path.join(OUTPUT_DIR, f"{raw_code}_tx_v4.4_factor_analysis.csv"), index=False, encoding='utf-8-sig')

            fig = plt.figure(figsize=(18, 12))
            ax1 = plt.subplot(2, 2, 1)
            ax1.pie(weights_pct, labels=expert_names, autopct='%1.1f%%', startangle=140, explode=(0.05,) * 4, shadow=True, colors=sns.color_palette('Set2')[0:4])
            ax1.set_title(f"[{raw_code}] 动态加权模型分布 (TX-V4.4)", fontsize=14, fontweight='bold')

            ax2 = plt.subplot(2, 2, 2)
            tree_ranking = sorted(zip(FEATURE_COLS, tree_imp_combined), key=lambda x: x[1], reverse=False)
            sns.barplot(x=[x[1] for x in tree_ranking], y=[x[0] for x in tree_ranking], ax=ax2, palette="magma")
            ax2.set_title(f"[{raw_code}] 因子使用频率 (Tree Importance)", fontsize=14, fontweight='bold')

            ax3 = plt.subplot(2, 1, 2)
            plt.sca(ax3)
            plt.title(f"[{raw_code}] 因子涨跌博弈极值分布 (SHAP Values)", fontsize=14, fontweight='bold', pad=20)
            shap.summary_plot(shap_values, X_scaled, feature_names=FEATURE_COLS, show=False)

            plt.tight_layout()
            plt.savefig(os.path.join(OUTPUT_DIR, f"{raw_code}_TX_V4.4_SHAP_Dashboard.png"), dpi=150, bbox_inches='tight')
            plt.close(fig)
        except Exception: pass

if __name__ == "__main__":
    generate_reports()