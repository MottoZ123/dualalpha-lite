import os
import time
import datetime
import warnings
import pandas as pd
import numpy as np
import akshare as ak
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import xgboost as xgb
import lightgbm as lgb
import catboost as cb
import torch
import torch.nn as nn
import torch.optim as optim

warnings.filterwarnings('ignore')

# ==========================================
# ⚙️ 核心配置 (海陆空全阵营 - 15只精选标的)
# ==========================================
# 包含科创板、创业板、主板标的 (已取并集并去重)
TICKERS_RAW = [
    '688257', '688820', '688002', '688008', '688809', '688387', '688313',  # 科创板
    '300857', '300502', '300308',  # 创业板
    '600522', '002335', '000657', '601899', '601918'  # 主板
]

TRAIN_WINDOW_DAYS = 250
STEP_SIZE_DAYS = 3
FRICTION_COST = 0.002
SEQ_LEN = 10

# 🌟 档位阈值与风控红线
PROB_B = 0.53
PROB_A = 0.58
PROB_S = 0.65
MAX_SINGLE_POS = 0.8  # 单支股票绝对上限 80%

# 🌟 公平测试权重：统一使用 1.3 黄金梯度
BIAS_TX = {"科技成长阵营": 1.3, "主板阵营": 1.3}
BIAS_BS = {"科技成长阵营": 1.3, "主板阵营": 1.3}

FEATURE_COLS_TX = [
    'Relative_Strength', 'Return_5', 'BIAS_20', 'BIAS_60',
    'Vol_Ratio', 'Norm_ATR_14', 'Entity_Ratio', 'Boll_Width',
    'Realized_Vol_20', 'PV_Corr_10', 'Overnight_Return',
    'CMF_20', 'Trend_Strength_20'
]

FEATURE_COLS_BS = [
    'Relative_Strength', 'Turn', 'Return_5', 'BIAS_20', 'BIAS_60',
    'Vol_Ratio', 'Norm_ATR_14', 'Entity_Ratio', 'Price_Cost_Bias',
    'Boll_Width', 'Realized_Vol_20', 'PV_Corr_10', 'Overnight_Return'
]

def get_sector(code):
    # 🌟 智能识别阵营
    return "科技成长阵营" if code.startswith('688') or code.startswith('300') else "主板阵营"

# ==========================================
# 📈 核心逻辑：分段连续的指数凸函数仓位管理
# ==========================================
def calculate_tiered_gradient_weight(prob, sector_bias):
    """非线性分段梯度加仓函数（采用指数凸函数避免多项式震荡）"""
    if prob < PROB_B:
        return 0.0

    def convex_map(p, p_min, p_max, w_min, w_max, alpha=2.0):
        x = np.clip((p - p_min) / (p_max - p_min), 0.0, 1.0)
        shape = (np.exp(alpha * x) - 1.0) / (np.exp(alpha) - 1.0)
        return w_min + shape * (w_max - w_min)

    if prob < PROB_A:
        base_w = convex_map(prob, PROB_B, PROB_A, 0.15, 0.30)
    elif prob < PROB_S:
        base_w = convex_map(prob, PROB_A, PROB_S, 0.30, 0.55)
    else:
        # S 档以上的最高上限视为 0.85 概率
        base_w = convex_map(prob, PROB_S, 0.85, 0.55, MAX_SINGLE_POS)

    return np.clip(base_w * sector_bias, 0.0, MAX_SINGLE_POS)


def get_tier_label(prob):
    if prob >= PROB_S: return "S"
    elif prob >= PROB_A: return "A"
    elif prob >= PROB_B: return "B"
    else: return "CD"


# ==========================================
# 🧠 深度学习组件与特征工程
# ==========================================
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
        out = self.transformer(x)
        return self.sigmoid(self.fc(out[:, -1, :]))


def create_sequences(data, labels, seq_length=10):
    xs, ys = [], []
    for i in range(len(data) - seq_length):
        xs.append(data[i:(i + seq_length)])
        ys.append(labels[i + seq_length])
    return np.array(xs), np.array(ys)


def build_features(df, df_market):
    col_mapping = {
        '日期': 'date', 'date': 'date', 'time': 'date',
        '开盘': 'Open', 'open': 'Open', '收盘': 'Close', 'close': 'Close',
        '最高': 'High', 'high': 'High', '最低': 'Low', 'low': 'Low',
        '成交量': 'Volume', 'volume': 'Volume', 'vol': 'Volume',
        '成交额': 'Amount', 'amount': 'Amount', '换手率': 'Turn', 'turn': 'Turn',
        '涨跌幅': 'PctChg', 'pct_chg': 'PctChg', 'pctChg': 'PctChg'
    }
    df = df.rename(columns={k: v for k, v in col_mapping.items() if k in df.columns})

    if 'Volume' not in df.columns and 'Amount' in df.columns:
        df['Volume'] = df['Amount']
    elif 'Amount' not in df.columns and 'Volume' in df.columns:
        df['Amount'] = df['Volume']
    elif 'Volume' not in df.columns and 'Amount' not in df.columns:
        df['Volume'], df['Amount'] = 1.0, 1.0
    if 'Turn' not in df.columns: df['Turn'] = 1.0

    for col in ['Open', 'High', 'Low', 'Close', 'Volume', 'Amount']:
        if col in df.columns: df[col] = pd.to_numeric(df[col], errors='coerce')

    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    df['Amount'] = df['Amount'].fillna(df['Close'] * df['Volume'])

    if 'PctChg' not in df.columns:
        df['PctChg'] = df['Close'].pct_change().fillna(0)
    else:
        df['PctChg'] = pd.to_numeric(df['PctChg'], errors='coerce') / 100.0
        df['PctChg'] = df['PctChg'].fillna(0)

    df = df.join(df_market, how='left')
    df['Market_PctChg'] = df['Market_PctChg'].fillna(0)
    df['Relative_Strength'] = df['PctChg'] - df['Market_PctChg']

    df['MA20'], df['MA60'] = df['Close'].rolling(20).mean(), df['Close'].rolling(60).mean()
    df['BIAS_20'], df['BIAS_60'] = (df['Close'] - df['MA20']) / (df['MA20'] + 1e-8), (df['Close'] - df['MA60']) / (df['MA60'] + 1e-8)
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
    clv = ((df['Close'] - df['Low']) - (df['High'] - df['Close'])) / df['HL_Range']
    df['CMF_20'] = (clv * df['Volume']).rolling(20).sum() / (df['Volume'].rolling(20).sum() + 1e-8)
    df['Trend_Strength_20'] = (df['Close'] - df['Close'].shift(20)) / (df['High'].rolling(20).max() - df['Low'].rolling(20).min() + 1e-8)
    df['Price_Cost_Bias'] = df['Close'] / ((df['Amount'] / (df['Volume'] + 1e-8)) + 1e-8) - 1

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    return df.dropna()


def fetch_all_historical_data():
    print("📥 正在拉取全局历史数据 (并集扩编: 15只新标的)...")
    try:
        print("   -> 📡 正在拉取大盘基准数据 (沪深300)...")
        df_market = ak.stock_zh_index_daily_tx(symbol="sz399300")
        df_market.rename(columns={'date': 'date', 'close': 'Close'}, inplace=True)
        df_market['date'] = pd.to_datetime(df_market['date'])
        df_market.set_index('date', inplace=True)
        df_market['Market_PctChg'] = df_market['Close'].pct_change().fillna(0)
    except Exception as e:
        print(f"❌ 大盘数据拉取失败: {e}")
        return None

    global_data = {}
    for code in TICKERS_RAW:
        sym = f"sh{code}" if code.startswith('6') else f"sz{code}"
        print(f"   -> 📡 正在拉取个股数据: {code} ...")
        for attempt in range(3):
            try:
                time.sleep(1.5)  # 🛡️ 防反爬休眠
                df_raw = ak.stock_zh_a_hist_tx(symbol=sym, start_date="20220101",
                                               end_date=datetime.datetime.now().strftime("%Y%m%d"), adjust="qfq")
                if not df_raw.empty:
                    global_data[code] = build_features(df_raw, df_market[['Market_PctChg']])
                break
            except Exception as e:
                if attempt == 2:
                    print(f"❌ {code} 数据拉取彻底失败: {e}")
                else:
                    print(f"      ⚠️ {code} 拉取超时，尝试重连...")
                    time.sleep(3)

    print("✅ 所有历史数据准备完毕！\n" + "=" * 60)
    return global_data


def train_and_predict_isolated(df, current_test_dates, features):
    predictions = {}
    test_start, test_end = current_test_dates[0], current_test_dates[-1]

    df_train = df[df.index < test_start].tail(TRAIN_WINDOW_DAYS)
    df_test = df[(df.index >= test_start) & (df.index <= test_end)]
    df_test_extended = df[df.index <= test_end].tail(len(df_test) + SEQ_LEN)

    if len(df_train) < 100 or len(df_test) == 0: return {}

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(df_train[features].values)
    X_test_scaled = scaler.transform(df_test_extended[features].values)

    y_train_raw = (df_train['Close'].shift(-STEP_SIZE_DAYS) > df_train['Close']).astype(int).values
    X_train_scaled, y_train_raw = X_train_scaled[:-STEP_SIZE_DAYS], y_train_raw[:-STEP_SIZE_DAYS]

    X_seq_train, y_seq_train = create_sequences(X_train_scaled, y_train_raw, SEQ_LEN)
    X_train_trees = X_train_scaled[SEQ_LEN:]
    y_train_aligned = y_train_raw[SEQ_LEN:]

    if len(X_train_trees) == 0 or len(X_seq_train) == 0: return {}

    m_xgb = xgb.XGBClassifier(n_estimators=50, max_depth=3, learning_rate=0.05, n_jobs=4, verbosity=0)
    m_lgb = lgb.LGBMClassifier(n_estimators=50, max_depth=3, learning_rate=0.05, n_jobs=4, verbose=-1)
    m_cat = cb.CatBoostClassifier(iterations=50, depth=3, learning_rate=0.05, verbose=0)

    m_xgb.fit(X_train_trees, y_train_aligned)
    m_lgb.fit(X_train_trees, y_train_aligned)
    m_cat.fit(X_train_trees, y_train_aligned)

    p_xgb_train = m_xgb.predict_proba(X_train_trees)[:, 1]
    p_lgb_train = m_lgb.predict_proba(X_train_trees)[:, 1]
    p_cat_train = m_cat.predict_proba(X_train_trees)[:, 1]

    device = torch.device("cpu")
    tf_model = StockTransformer(input_size=len(features), seq_len=SEQ_LEN).to(device)
    optimizer = optim.Adam(tf_model.parameters(), lr=0.01)
    criterion = nn.BCELoss()

    X_t = torch.FloatTensor(X_seq_train).to(device)
    y_t = torch.FloatTensor(y_seq_train).unsqueeze(1).to(device)
    tf_model.train()
    for _ in range(5):
        optimizer.zero_grad()
        loss = criterion(tf_model(X_t), y_t)
        loss.backward()
        optimizer.step()

    tf_model.eval()
    with torch.no_grad():
        p_tf_train = tf_model(X_t).cpu().numpy().flatten()

    X_test_trees = X_test_scaled[SEQ_LEN:]
    X_seq_test, _ = create_sequences(X_test_scaled, np.zeros(len(X_test_scaled)), SEQ_LEN)
    if len(X_test_trees) == 0: return {}

    p_xgb_test = m_xgb.predict_proba(X_test_trees)[:, 1]
    p_lgb_test = m_lgb.predict_proba(X_test_trees)[:, 1]
    p_cat_test = m_cat.predict_proba(X_test_trees)[:, 1]
    with torch.no_grad():
        p_tf_test = tf_model(torch.FloatTensor(X_seq_test).to(device)).cpu().numpy().flatten()

    meta_X_train = np.column_stack((p_xgb_train, p_lgb_train, p_cat_train, p_tf_train))
    meta_X_test = np.column_stack((p_xgb_test, p_lgb_test, p_cat_test, p_tf_test))

    meta_model = LogisticRegression()
    meta_model.fit(meta_X_train, y_train_aligned)
    raw_coefs = np.abs(meta_model.coef_[0])
    weights = raw_coefs / (np.sum(raw_coefs) + 1e-8)

    final_probs = np.dot(meta_X_test, weights)

    for i, date in enumerate(df_test.index):
        if i < len(final_probs): predictions[date] = final_probs[i]

    return predictions


def run_backtest():
    global_data = fetch_all_historical_data()
    if not global_data or len(global_data) == 0:
        print("❌ 全局数据为空！回测终止。")
        return

    valid_keys = list(global_data.keys())
    all_dates = global_data[valid_keys[0]].index.sort_values()
    backtest_dates = all_dates[TRAIN_WINDOW_DAYS:]

    if len(backtest_dates) == 0: return

    print(f"\n🚀 启动跨板块火力侦察回测 (共 15 只并集标的)")
    print("=" * 70)

    records = []
    total_steps = len(backtest_dates) // STEP_SIZE_DAYS + 1

    for i in range(0, len(backtest_dates), STEP_SIZE_DAYS):
        window = backtest_dates[i: i + STEP_SIZE_DAYS]
        decision_date = window[0]

        current_step = i // STEP_SIZE_DAYS + 1
        print(f"🔄 [推演进度 {current_step}/{total_steps}] 结算决策日: {decision_date.date()} ...", flush=True)

        for code in TICKERS_RAW:
            if code not in global_data: continue
            df = global_data[code]

            preds_tx = train_and_predict_isolated(df, window, FEATURE_COLS_TX)
            preds_bs = train_and_predict_isolated(df, window, FEATURE_COLS_BS)

            if decision_date not in df.index: continue
            loc = df.index.get_loc(decision_date)
            if loc + STEP_SIZE_DAYS < len(df):
                open_raw = df.iloc[loc + 1]['Open']
                close_raw = df.iloc[loc + STEP_SIZE_DAYS]['Close']
                net_profit = ((close_raw * (1 - FRICTION_COST)) - (open_raw * (1 + FRICTION_COST))) / (
                        open_raw * (1 + FRICTION_COST))

                prob_tx = preds_tx.get(decision_date, 0.5)
                prob_bs = preds_bs.get(decision_date, 0.5)
                records.append({
                    "Date": decision_date, "Code": code, "Sector": get_sector(code),
                    "Prob_TX": prob_tx, "Tier_TX": get_tier_label(prob_tx),
                    "Prob_BS": prob_bs, "Tier_BS": get_tier_label(prob_bs),
                    "Raw_Ret": net_profit
                })

    if not records: return
    df_res = pd.DataFrame(records)

    # 🌟 核心：Top2 强制过滤，不满 B 档坚决空仓
    df_res['Rank_TX'] = df_res.groupby('Date')['Prob_TX'].rank(ascending=False, method='first')
    df_res['Rank_BS'] = df_res.groupby('Date')['Prob_BS'].rank(ascending=False, method='first')

    df_res['Signal_TX'] = ((df_res['Rank_TX'] <= 2) & (df_res['Prob_TX'] >= PROB_B)).astype(int)
    df_res['Signal_BS'] = ((df_res['Rank_BS'] <= 2) & (df_res['Prob_BS'] >= PROB_B)).astype(int)

    df_res['Bias_TX'] = df_res['Sector'].map(BIAS_TX)
    df_res['Bias_BS'] = df_res['Sector'].map(BIAS_BS)

    # 🌟 核心：凸函数梯度加仓
    df_res['Weight_TX'] = df_res.apply(
        lambda x: calculate_tiered_gradient_weight(x['Prob_TX'], x['Bias_TX']) if x['Signal_TX'] == 1 else 0, axis=1)
    df_res['Weight_BS'] = df_res.apply(
        lambda x: calculate_tiered_gradient_weight(x['Prob_BS'], x['Bias_BS']) if x['Signal_BS'] == 1 else 0, axis=1)

    df_res['Net_Ret_TX'] = df_res['Weight_TX'] * df_res['Raw_Ret']
    df_res['Net_Ret_BS'] = df_res['Weight_BS'] * df_res['Raw_Ret']

    # --- 最终成绩单打印函数 ---
    def print_tiered_summary(name, group_key):
        prob_col = f"Prob_{group_key}"
        tier_col = f"Tier_{group_key}"
        signal_col = f"Signal_{group_key}"
        weight_col = f"Weight_{group_key}"
        net_col = f"Net_Ret_{group_key}"

        # 提取真实发生交易的记录 (排除了 C/D 档，且是 Top2)
        dft_all = df_res[df_res[signal_col] == 1].copy()
        if len(dft_all) == 0: return

        total_profit = dft_all[net_col].sum() * 100
        win_rate_all = len(dft_all[dft_all['Raw_Ret'] > 0]) / len(dft_all)

        print(f"\n{'=' * 20} {name} 战术深度复盘 {'=' * 20}")
        print(
            f"🎯 选股出击: {len(dft_all):4d} 次 | 💰 账户净利贡献: {total_profit:8.2f}% | ⚖️ 整体胜率: {win_rate_all * 100:5.1f}%")
        print("-" * 60)

        # 1. 拆解各档位战斗力
        for tier in ["S", "A", "B"]:
            dft = dft_all[dft_all[tier_col] == tier]
            if len(dft) == 0: continue
            win_rate = len(dft[dft['Raw_Ret'] > 0]) / len(dft)
            t_profit = dft[net_col].sum() * 100
            avg_pos = dft[weight_col].mean() * 100
            print(
                f"[{tier}档信号] 出击 {len(dft):3d} 次 | 🎯 档位胜率: {win_rate * 100:5.1f}% | 🔋 均配仓位: {avg_pos:4.1f}% | 💸 赚取利润: {t_profit:8.2f}%")

        print("-" * 60)
        # 2. 个股细分贡献榜
        print(f"| 代码 | 板块 | 总出击 | 胜率 | 平均实战仓位 | 累计收益(%) |")
        print(f"| :--- | :--- | :---: | :---: | :---: | :---: |")
        for code, group in dft_all.groupby('Code'):
            c_win = len(group[group['Raw_Ret'] > 0]) / len(group)
            c_profit = group[net_col].sum() * 100
            c_pos = group[weight_col].mean() * 100
            tag = " 🌟" if c_profit > 15 else (" 🚨" if c_profit < -5 else "")
            print(
                f"| **{code}** | {group['Sector'].iloc[0][:2]} | {len(group):4d} | {c_win * 100:4.1f}% | {c_pos:5.1f}% | {c_profit:8.2f}{tag} |")

    print("\n\n" + "★" * 70)
    print("🏆 跨板块扩展实战测试单 (15只精锐)")
    print("★" * 70)
    print_tiered_summary("🔴 A组: TX 资金趋势流", "TX")
    print_tiered_summary("🔵 B组: BS 暴力超跌流", "BS")


if __name__ == "__main__":
    start_time = time.time()
    run_backtest()
    print(f"\n⏱️ 耗时: {(time.time() - start_time) / 60:.2f} 分钟")