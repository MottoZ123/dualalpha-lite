import os
import time
import datetime
import warnings
import pandas as pd
import numpy as np
import akshare as ak
import baostock as bs
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import xgboost as xgb
import lightgbm as lgb
import catboost as cb
import torch
import torch.nn as nn
import torch.optim as optim
from tqdm import tqdm

warnings.filterwarnings('ignore')

# 🌟 限制 PyTorch 线程数，防止 CPU 算力踩踏
torch.set_num_threads(4)

# ==========================================
# ⚙️ 核心配置 (路线 A：尾盘埋伏 T+5 | 满血架构 | TQDM版)
# ==========================================
TICKERS_RAW = ['600522', '002335', '000657', '601899']
TRAIN_WINDOW_DAYS = 250
STEP_SIZE_DAYS = 5  # 🌟 步长放大 5 倍！大幅缩减训练次数，加快进度
FRICTION_COST = 0.0  # 继续保持零税费，纯净验收预测威力
SEQ_LEN = 10

PROB_B = 0.53
PROB_A = 0.58
PROB_S = 0.65
MAX_SINGLE_POS = 0.8
BIAS_MAIN = 1.3

# 🧱 V6-BS 纯净量价因子
FEATURES_BS = [
    'Relative_Strength_20', 'MACD_Hist_Norm', 'Z_Score_20',
    'ATR_Ratio_14_60', 'Vol_Surge_60', 'Price_VWAP_Bias',
    'MFI_14', 'Return_5', 'Return_20'
]

# 🧱 V7-TX 纯价格免疫因子
FEATURES_TX = [
    'Relative_Strength_20', 'MACD_Hist_Norm', 'Z_Score_20',
    'ATR_Ratio_14_60', 'Price_EMA_Bias_20', 'Return_5', 'Return_20',
    'Williams_R_14', 'CCI_14', 'Candle_Shape'
]


def calculate_tiered_gradient_weight(prob, sector_bias):
    if prob < PROB_B: return 0.0

    def convex_map(p, p_min, p_max, w_min, w_max, alpha=2.0):
        x = np.clip((p - p_min) / (p_max - p_min), 0.0, 1.0)
        shape = (np.exp(alpha * x) - 1.0) / (np.exp(alpha) - 1.0)
        return w_min + shape * (w_max - w_min)

    if prob < PROB_A:
        base_w = convex_map(prob, PROB_B, PROB_A, 0.15, 0.30)
    elif prob < PROB_S:
        base_w = convex_map(prob, PROB_A, PROB_S, 0.30, 0.55)
    else:
        base_w = convex_map(prob, PROB_S, 0.85, 0.55, MAX_SINGLE_POS)
    return np.clip(base_w * sector_bias, 0.0, MAX_SINGLE_POS)


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


def build_features(df, df_market, source):
    col_mapping = {
        '日期': 'date', 'time': 'date', '开盘': 'Open', 'open': 'Open',
        '收盘': 'Close', 'close': 'Close', '最高': 'High', 'high': 'High', '最低': 'Low', 'low': 'Low',
        '成交量': 'Volume', 'volume': 'Volume', 'amount': 'Amount', '成交额': 'Amount'
    }
    df = df.rename(columns=col_mapping).loc[:, ~df.columns.duplicated()]
    for c in ['Open', 'High', 'Low', 'Close', 'Volume', 'Amount']:
        if c in df.columns: df[c] = pd.to_numeric(df[c], errors='coerce')

    df.index = pd.to_datetime(df['date'])
    df = df.join(df_market, how='left').ffill()

    df['Return_5'] = df['Close'] / (df['Close'].shift(5) + 1e-8) - 1
    df['Return_20'] = df['Close'] / (df['Close'].shift(20) + 1e-8) - 1
    df['Relative_Strength_20'] = df['Return_20'] - df['Market_PctChg'].fillna(0).rolling(20).sum()
    ema12, ema26 = df['Close'].ewm(span=12, adjust=False).mean(), df['Close'].ewm(span=26, adjust=False).mean()
    df['MACD_Hist_Norm'] = ((ema12 - ema26) - (ema12 - ema26).ewm(span=9, adjust=False).mean()) / (df['Close'] + 1e-8)
    df['MA20'] = df['Close'].rolling(20).mean()
    df['Z_Score_20'] = (df['Close'] - df['MA20']) / (df['Close'].rolling(20).std() + 1e-8)
    df['Prev_Close'] = df['Close'].shift(1).fillna(df['Close'])
    df['TR'] = df[['High', 'Prev_Close']].max(axis=1) - df[['Low', 'Prev_Close']].min(axis=1)
    df['ATR_Ratio_14_60'] = df['TR'].rolling(14).mean() / (df['TR'].rolling(60).mean() + 1e-8)

    if source == 'BS':
        df['Vol_Surge_60'] = df['Volume'] / (df['Volume'].rolling(60).mean() + 1e-8)
        df['Price_VWAP_Bias'] = df['Close'] / (
                    (df['Amount'].rolling(20).sum() / (df['Volume'].rolling(20).sum() + 1e-8)) + 1e-8) - 1
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        pf = np.where(tp > tp.shift(1), tp * df['Volume'], 0).flatten()
        nf = np.where(tp < tp.shift(1), tp * df['Volume'], 0).flatten()
        df['MFI_14'] = 100 - (100 / (1 + pd.Series(pf, index=df.index).rolling(14).sum() / (
                    pd.Series(nf, index=df.index).rolling(14).sum() + 1e-8)))
    else:
        df['Price_EMA_Bias_20'] = df['Close'] / df['Close'].ewm(span=20, adjust=False).mean() - 1
        highest_14 = df['High'].rolling(14).max()
        lowest_14 = df['Low'].rolling(14).min()
        df['Williams_R_14'] = (highest_14 - df['Close']) / (highest_14 - lowest_14 + 1e-8) * -100
        tp = (df['High'] + df['Low'] + df['Close']) / 3
        df['CCI_14'] = (tp - tp.rolling(14).mean()) / (0.015 * tp.rolling(14).std() + 1e-8)
        df['Candle_Shape'] = (df['Close'] - df['Low']) / (df['High'] - df['Low'] + 1e-8)

    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    return df.dropna()


def fetch_all_historical_data(source):
    print(f"\n📥 [{source}] 开始连接数据库拉取全量 6 年数据...", flush=True)
    global_data = {}
    if source == 'TX':
        df_market = ak.stock_zh_index_daily_tx(symbol="sh000001")
        df_market.rename(columns={'date': 'date', 'close': 'Close'}, inplace=True)
        df_market['date'] = pd.to_datetime(df_market['date'])
        df_market.set_index('date', inplace=True)
        df_market['Market_PctChg'] = df_market['Close'].pct_change().fillna(0)
        for code in TICKERS_RAW:
            sym = f"sh{code}" if code.startswith('6') else f"sz{code}"
            df_raw = ak.stock_zh_a_hist_tx(symbol=sym, start_date="20180101", adjust="qfq")
            if not df_raw.empty: global_data[code] = build_features(df_raw, df_market[['Market_PctChg']], 'TX')
            print(f"   -> [{code}] 数据清洗完毕", flush=True)
    elif source == 'BS':
        bs.login()
        rs_m = bs.query_history_k_data_plus("sh.000001", "date,pctChg", start_date="2018-01-01", frequency="d",
                                            adjustflag="2")
        data_list = []
        while (rs_m.error_code == '0') & rs_m.next(): data_list.append(rs_m.get_row_data())
        df_market = pd.DataFrame(data_list, columns=rs_m.fields)
        df_market['Market_PctChg'] = pd.to_numeric(df_market['pctChg'], errors='coerce') / 100.0
        df_market.set_index(pd.to_datetime(df_market['date']), inplace=True)
        for code in TICKERS_RAW:
            sym = f"sh.{code}" if code.startswith('6') else f"sz.{code}"
            rs = bs.query_history_k_data_plus(sym, "date,open,high,low,close,volume,amount,pctChg",
                                              start_date="2018-01-01", frequency="d", adjustflag="2")
            data_list = []
            while (rs.error_code == '0') & rs.next(): data_list.append(rs.get_row_data())
            df_raw = pd.DataFrame(data_list, columns=rs.fields)
            if not df_raw.empty: global_data[code] = build_features(df_raw, df_market[['Market_PctChg']], 'BS')
            print(f"   -> [{code}] 数据清洗完毕", flush=True)
        bs.logout()
    return global_data


def train_and_predict(df, current_test_dates, features):
    test_start, test_end = current_test_dates[0], current_test_dates[-1]
    df_train = df[df.index < test_start].tail(TRAIN_WINDOW_DAYS)
    df_test = df[(df.index >= test_start) & (df.index <= test_end)]
    df_test_extended = df[df.index <= test_end].tail(len(df_test) + SEQ_LEN)

    if len(df_train) < 100 or len(df_test) == 0: return {}

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(df_train[features].values)
    X_test_scaled = scaler.transform(df_test_extended[features].values)

    # 🌟 重构目标锚点：今天买入，5天后卖出，因此模型需要预判 5 天后的涨跌！
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

    meta_model = LogisticRegression(C=1.0)
    meta_model.fit(meta_X_train, y_train_aligned)
    raw_coefs = np.abs(meta_model.coef_[0])
    weights = raw_coefs / (np.sum(raw_coefs) + 1e-8)
    final_probs = np.dot(meta_X_test, weights)

    predictions = {}
    for i, date in enumerate(df_test.index):
        if i < len(final_probs): predictions[date] = final_probs[i]

    return predictions


def execute_engine(source):
    global_data = fetch_all_historical_data(source)
    features = FEATURES_BS if source == 'BS' else FEATURES_TX
    valid_keys = list(global_data.keys())
    all_dates = global_data[valid_keys[0]].index.sort_values()
    backtest_dates = all_dates[TRAIN_WINDOW_DAYS:]

    records = []

    # 🌟 步长更改为 STEP_SIZE_DAYS (5)，大幅减少推演循环！
    for i in tqdm(range(0, len(backtest_dates), STEP_SIZE_DAYS), desc=f"🚀 [{source}] 满血战车 T+5 滚推", ncols=100):
        decision_date = backtest_dates[i]
        for code in TICKERS_RAW:
            df = global_data[code]
            if decision_date not in df.index: continue
            preds = train_and_predict(df, [decision_date], features)
            prob = preds.get(decision_date, 0.5)

            loc = df.index.get_loc(decision_date)
            # 🌟 T+5 结算锚点：今天尾盘买入，5个交易日后的尾盘卖出
            if loc + STEP_SIZE_DAYS < len(df):
                close_today = df.iloc[loc]['Close']
                close_target = df.iloc[loc + STEP_SIZE_DAYS]['Close']
                ret = (close_target - close_today) / close_today
                records.append({"Date": decision_date, "Code": code, "Prob": prob, "Ret": ret})

    df_res = pd.DataFrame(records)
    df_res['Signal'] = (df_res['Prob'] >= PROB_B).astype(int)
    df_res['Weight'] = df_res.apply(
        lambda x: calculate_tiered_gradient_weight(x['Prob'], BIAS_MAIN) if x['Signal'] == 1 else 0, axis=1)
    df_res['Net_Ret'] = df_res['Weight'] * df_res['Ret']

    dft = df_res[df_res['Signal'] == 1].copy()
    win_rate = len(dft[dft['Ret'] > 0]) / len(dft) if len(dft) > 0 else 0
    total_prof = dft['Net_Ret'].sum() * 100

    report = f"\n\n==================== ⚡ [{source} 满血 AI 集成 | 尾盘真 T+5] ====================\n"
    report += f"🎯 选股出击: {len(dft):4d} 次 | 💰 累计无税净利: {total_prof:8.2f}% | ⚖️ T+5波段胜率: {win_rate * 100:5.1f}%\n"
    report += "-" * 60 + "\n"
    for code, group in dft.groupby('Code'):
        c_win = len(group[group['Ret'] > 0]) / len(group)
        c_profit = group['Net_Ret'].sum() * 100
        tag = " 🌟" if c_profit > 10 else (" 🚨" if c_profit < -5 else "")
        report += f"| **{code}** | 波段胜率: {c_win * 100:5.1f}% | 累计收益: {c_profit:8.2f}% {tag} |\n"
    report += "==========================================================================\n"
    print(report, flush=True)


if __name__ == "__main__":
    start = time.time()
    print("🌟 满血版双擎启动！【单线稳定突击 + T+5极速滚推 + TQDM可视化雷达】\n", flush=True)

    for source in ['TX', 'BS']:
        execute_engine(source)

    print(f"\n⏱️ 总耗时: {(time.time() - start) / 60:.2f} 分钟", flush=True)