"""BS 因子解释。"""

import os
import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
import catboost as cb
import matplotlib.pyplot as plt
import seaborn as sns
import shap
import baostock as bs
import warnings

warnings.filterwarnings('ignore')
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']
plt.rcParams['axes.unicode_minus'] = False

TICKERS_RAW = ['688313', '300308', '300857', '300502', '688008', '688041', '300059', '601899', '601918']
FEATURE_COLS = [
    'Relative_Strength', 'Turn', 'Return_5', 'BIAS_20', 'BIAS_60',
    'Vol_Ratio', 'Norm_ATR_14', 'Entity_Ratio', 'Price_Cost_Bias',
    'Boll_Width', 'Realized_Vol_20', 'PV_Corr_10', 'Overnight_Return'
]
OUTPUT_DIR = "factor_reports_v4.3"

def format_bs_ticker(code): return f"sh.{code}" if code.startswith('6') else f"sz.{code}"

def get_market_baseline_bs():
    rs = bs.query_history_k_data_plus("sh.000001", "date,pctChg", start_date="2023-01-01", frequency="d", adjustflag="2")
    data_list = []
    while (rs.error_code == '0') & rs.next(): data_list.append(rs.get_row_data())
    df_market = pd.DataFrame(data_list, columns=rs.fields)
    df_market.rename(columns={'pctChg': 'Market_PctChg'}, inplace=True)
    df_market['Market_PctChg'] = pd.to_numeric(df_market['Market_PctChg'], errors='coerce') / 100.0
    df_market.set_index('date', inplace=True)
    return df_market

def build_features(df, df_market):
    df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume', 'amount': 'Amount', 'turn': 'Turn', 'pctChg': 'PctChg'}, inplace=True)
    for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'Amount', 'Turn', 'PctChg']: df[col] = pd.to_numeric(df[col], errors='coerce')
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
    df['Realized_Vol_20'] = df['PctChg'].rolling(20).std() * np.sqrt(252)
    df['PV_Corr_10'] = df['Close'].rolling(10).corr(df['Volume']).fillna(0)
    df['Overnight_Return'] = df['Open'] / (df['Prev_Close'] + 1e-8) - 1
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    return df.dropna()

def generate_reports():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    bs.login()
    df_market = get_market_baseline_bs()

    for raw_code in TICKERS_RAW:
        try:
            sym = format_bs_ticker(raw_code)
            rs = bs.query_history_k_data_plus(sym, "date,open,high,low,close,volume,amount,turn,pctChg", start_date="2023-01-01", frequency="d", adjustflag="2")
            data_list = []
            while (rs.error_code == '0') & rs.next(): data_list.append(rs.get_row_data())
            df_raw = pd.DataFrame(data_list, columns=rs.fields)
            if len(df_raw) < 40: continue

            df = build_features(df_raw, df_market)
            X = df[FEATURE_COLS].values[-250:]
            scaler = joblib.load(f"models/{raw_code}_scaler.pkl")
            X_scaled = scaler.transform(X)

            # 恢复动态权重读取！
            meta_model = joblib.load(f"models/{raw_code}_meta.pkl")
            expert_names = ['XGBoost', 'LightGBM', 'CatBoost', 'Transformer']
            if hasattr(meta_model, 'coef_'):
                raw_coefs = np.abs(meta_model.coef_[0])
                weights_pct = (raw_coefs / (np.sum(raw_coefs) + 1e-8)) * 100
            else: weights_pct = [25.0, 25.0, 25.0, 25.0]

            lgb_model = joblib.load(f"models/{raw_code}_lgb.pkl")
            cat_model = cb.CatBoostClassifier()
            cat_model.load_model(f"models/{raw_code}_cat.cbm")
            tree_imp_combined = ((lgb_model.feature_importances_ / np.sum(lgb_model.feature_importances_)) * 100 + (cat_model.get_feature_importance() / np.sum(cat_model.get_feature_importance())) * 100) / 2

            explainer = shap.TreeExplainer(lgb_model)
            shap_values = explainer.shap_values(X_scaled)
            if isinstance(shap_values, list): shap_values = shap_values[1]

            fig = plt.figure(figsize=(18, 12))
            ax1 = plt.subplot(2, 2, 1)
            ax1.pie(weights_pct, labels=expert_names, autopct='%1.1f%%', startangle=140, explode=(0.05, 0.05, 0.05, 0.05), shadow=True, colors=sns.color_palette('Set2')[0:4])
            ax1.set_title(f"[{raw_code}] 动态加权模型分布", fontsize=14, fontweight='bold')

            ax2 = plt.subplot(2, 2, 2)
            tree_ranking = sorted(zip(FEATURE_COLS, tree_imp_combined), key=lambda x: x[1], reverse=False)
            sns.barplot(x=[x[1] for x in tree_ranking], y=[x[0] for x in tree_ranking], ax=ax2, palette="magma")
            ax2.set_title(f"[{raw_code}] 底层专家因子偏好 (Tree)", fontsize=14, fontweight='bold')

            ax3 = plt.subplot(2, 1, 2)
            plt.sca(ax3)
            plt.title(f"[{raw_code}] 因子涨跌博弈分布 (SHAP Values)", fontsize=14, fontweight='bold', pad=20)
            shap.summary_plot(shap_values, X_scaled, feature_names=FEATURE_COLS, show=False)

            plt.tight_layout()
            plt.savefig(os.path.join(OUTPUT_DIR, f"{raw_code}_V4.3_SHAP_Dashboard.png"), dpi=150, bbox_inches='tight')
            plt.close(fig)
        except Exception: pass
    bs.logout()

if __name__ == "__main__":
    generate_reports()