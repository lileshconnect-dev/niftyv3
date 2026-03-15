from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, emit
from pymongo import MongoClient
import yfinance as yf
import numpy as np
from datetime import datetime
import threading
import time
import hashlib
import os

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'nifty50secret2024xyz')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

MONGO_URI = os.environ.get('MONGO_URI', '')
client = MongoClient(MONGO_URI)
db = client['niftypulse']
users_col = db['users']

NIFTY_CASH  = 100000
GLOBAL_CASH = 100000
CRYPTO_CASH = 100000

# ── Indian Stocks ─────────────────────────────────────────────────────────────
NIFTY_TICKERS = [
    'RELIANCE.NS','TCS.NS','HDFCBANK.NS','INFY.NS','ICICIBANK.NS',
    'HINDUNILVR.NS','ITC.NS','SBIN.NS','BHARTIARTL.NS','KOTAKBANK.NS',
    'LT.NS','AXISBANK.NS','ASIANPAINT.NS','MARUTI.NS','SUNPHARMA.NS',
    'TITAN.NS','BAJFINANCE.NS','NESTLEIND.NS','WIPRO.NS','ULTRACEMCO.NS',
    'POWERGRID.NS','NTPC.NS','TECHM.NS','HCLTECH.NS','ADANIENT.NS',
    'BAJAJFINSV.NS','ONGC.NS','JSWSTEEL.NS','TATASTEEL.NS','COALINDIA.NS',
    'HINDALCO.NS','DRREDDY.NS','CIPLA.NS','DIVISLAB.NS','APOLLOHOSP.NS',
    'EICHERMOT.NS','HEROMOTOCO.NS','BAJAJ-AUTO.NS','TATACONSUM.NS','BRITANNIA.NS',
    'GRASIM.NS','INDUSINDBK.NS','M&M.NS','ADANIPORTS.NS',
    'SBILIFE.NS','HDFCLIFE.NS','BPCL.NS','IOC.NS','TATAPOWER.NS','PIDILITIND.NS',
    'PAYTM.NS','ATGL.NS'
]

NIFTY_NAMES = {
    'RELIANCE.NS':'Reliance Industries','TCS.NS':'Tata Consultancy Services',
    'HDFCBANK.NS':'HDFC Bank','INFY.NS':'Infosys','ICICIBANK.NS':'ICICI Bank',
    'HINDUNILVR.NS':'Hindustan Unilever','ITC.NS':'ITC Ltd','SBIN.NS':'State Bank of India',
    'BHARTIARTL.NS':'Bharti Airtel','KOTAKBANK.NS':'Kotak Mahindra Bank',
    'LT.NS':'Larsen & Toubro','AXISBANK.NS':'Axis Bank','ASIANPAINT.NS':'Asian Paints',
    'MARUTI.NS':'Maruti Suzuki','SUNPHARMA.NS':'Sun Pharma','TITAN.NS':'Titan Company',
    'BAJFINANCE.NS':'Bajaj Finance','NESTLEIND.NS':'Nestle India','WIPRO.NS':'Wipro',
    'ULTRACEMCO.NS':'UltraTech Cement','POWERGRID.NS':'Power Grid Corp','NTPC.NS':'NTPC Ltd',
    'TECHM.NS':'Tech Mahindra','HCLTECH.NS':'HCL Technologies','ADANIENT.NS':'Adani Enterprises',
    'BAJAJFINSV.NS':'Bajaj Finserv','ONGC.NS':'ONGC','JSWSTEEL.NS':'JSW Steel',
    'TATASTEEL.NS':'Tata Steel','COALINDIA.NS':'Coal India','HINDALCO.NS':'Hindalco Industries',
    'DRREDDY.NS':'Dr. Reddys Labs','CIPLA.NS':'Cipla','DIVISLAB.NS':'Divis Laboratories',
    'APOLLOHOSP.NS':'Apollo Hospitals','EICHERMOT.NS':'Eicher Motors','HEROMOTOCO.NS':'Hero MotoCorp',
    'BAJAJ-AUTO.NS':'Bajaj Auto','TATACONSUM.NS':'Tata Consumer','BRITANNIA.NS':'Britannia Industries',
    'GRASIM.NS':'Grasim Industries','INDUSINDBK.NS':'IndusInd Bank','M&M.NS':'Mahindra & Mahindra',
    'ADANIPORTS.NS':'Adani Ports','SBILIFE.NS':'SBI Life Insurance','HDFCLIFE.NS':'HDFC Life',
    'BPCL.NS':'BPCL','IOC.NS':'Indian Oil Corp','TATAPOWER.NS':'Tata Power',
    'PIDILITIND.NS':'Pidilite Industries','PAYTM.NS':'Paytm (One97)','ATGL.NS':'Adani Total Gas'
}

# ── Global Stocks ─────────────────────────────────────────────────────────────
GLOBAL_TICKERS = [
    'AAPL','TSLA','GOOGL','MSFT','AMZN','NVDA',
    'JPM','BAC','GS','V','MA',
    '005930.KS','TM','HSBC','BABA'
]

GLOBAL_NAMES = {
    'AAPL':'Apple Inc','TSLA':'Tesla Inc','GOOGL':'Alphabet (Google)',
    'MSFT':'Microsoft','AMZN':'Amazon','NVDA':'NVIDIA',
    'JPM':'JPMorgan Chase','BAC':'Bank of America','GS':'Goldman Sachs',
    'V':'Visa Inc','MA':'Mastercard',
    '005930.KS':'Samsung Electronics','TM':'Toyota Motor',
    'HSBC':'HSBC Holdings','BABA':'Alibaba Group'
}

# ── Crypto ────────────────────────────────────────────────────────────────────
CRYPTO_TICKERS = [
    'BTC-USD','ETH-USD','BNB-USD','SOL-USD','XRP-USD','DOGE-USD'
]

CRYPTO_NAMES = {
    'BTC-USD':'Bitcoin','ETH-USD':'Ethereum','BNB-USD':'BNB',
    'SOL-USD':'Solana','XRP-USD':'XRP','DOGE-USD':'Dogecoin'
}

ALL_NAMES = {**NIFTY_NAMES, **GLOBAL_NAMES, **CRYPTO_NAMES}

nifty_cache  = {}
global_cache = {}
crypto_cache = {}
connected_users = 0
fetch_lock = threading.Lock()

# ── DB helpers ────────────────────────────────────────────────────────────────
def get_user(username):
    u = users_col.find_one({'username': username}, {'_id': 0})
    if not u: return None
    # ── Migrate old field names to new format ──────────────────────────────────
    changed = False
    if 'nifty_cash' not in u:
        u['nifty_cash']         = float(u.get('cash', NIFTY_CASH))
        u['nifty_portfolio']    = u.get('portfolio', {})
        u['nifty_transactions'] = u.get('transactions', [])
        u['global_cash']        = float(GLOBAL_CASH)
        u['global_portfolio']   = {}
        u['global_transactions']= []
        u['crypto_cash']        = float(CRYPTO_CASH)
        u['crypto_portfolio']   = {}
        u['crypto_transactions']= []
        changed = True
    if changed:
        users_col.update_one({'username': username}, {'$set': u, '$unset': {'cash':1,'portfolio':1,'transactions':1}})
    return u

def save_user(u):
    users_col.update_one({'username': u['username']}, {'$set': u}, upsert=True)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def new_user_doc(username, pw):
    return {
        'username': username,
        'password': hash_pw(pw),
        # Indian wallet
        'nifty_cash': float(NIFTY_CASH),
        'nifty_portfolio': {},
        'nifty_transactions': [],
        # Global wallet
        'global_cash': float(GLOBAL_CASH),
        'global_portfolio': {},
        'global_transactions': [],
        # Crypto wallet
        'crypto_cash': float(CRYPTO_CASH),
        'crypto_portfolio': {},
        'crypto_transactions': [],
        'joined': datetime.now().strftime("%d %b %Y")
    }

# ── Analysis ──────────────────────────────────────────────────────────────────
def calculate_rsi(prices, period=14):
    if len(prices) < period + 1: return 50
    deltas = np.diff(prices)
    gains  = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0: return 100
    return round(float(100 - (100 / (1 + avg_gain / avg_loss))), 2)

def moving_average(prices, w):
    if len(prices) < w: return None
    return round(float(np.mean(prices[-w:])), 2)

def predict_next(prices):
    if len(prices) < 5: return None
    x = np.arange(len(prices))
    c = np.polyfit(x, np.array(prices), 1)
    return round(float(np.polyval(c, len(prices))), 2)

def get_signal(prices, rsi, cur, pred):
    ma7  = moving_average(prices, 7)
    ma21 = moving_average(prices, 21)
    score = 0; reasons = []
    if rsi < 35:   score += 2; reasons.append("RSI oversold")
    elif rsi > 65: score -= 2; reasons.append("RSI overbought")
    if ma7 and ma21:
        if ma7 > ma21: score += 1; reasons.append("MA7 > MA21 bullish")
        else:          score -= 1; reasons.append("MA7 < MA21 bearish")
    if pred and cur:
        pct = ((pred - cur) / cur) * 100
        if pct > 1:    score += 2; reasons.append(f"Predicted +{pct:.1f}%")
        elif pct < -1: score -= 2; reasons.append(f"Predicted {pct:.1f}%")
    if score >= 3:    return {"action":"STRONG BUY","color":"strong-buy","reasons":reasons}
    elif score >= 1:  return {"action":"BUY","color":"buy","reasons":reasons}
    elif score <= -3: return {"action":"STRONG SELL","color":"strong-sell","reasons":reasons}
    elif score <= -1: return {"action":"SELL","color":"sell","reasons":reasons}
    else:             return {"action":"HOLD","color":"hold","reasons":reasons}

def fetch_one(ticker, names):
    try:
        hist = yf.Ticker(ticker).history(period="60d", interval="1d")
        if hist is None or hist.empty: return None
        prices = [float(p) for p in hist['Close'].tolist() if p is not None and not np.isnan(p)]
        if len(prices) < 5: return None
        # Candlestick data (OHLC)
        ohlc = []
        for i, row in hist.tail(30).iterrows():
            ohlc.append({
                'x': str(i.date()),
                'o': round(float(row['Open']), 4),
                'h': round(float(row['High']), 4),
                'l': round(float(row['Low']), 4),
                'c': round(float(row['Close']), 4),
            })
        cur  = round(prices[-1], 4)
        prev = round(prices[-2], 4) if len(prices) > 1 else cur
        chg  = round(cur - prev, 4)
        chgp = round((chg / prev) * 100, 2) if prev else 0
        rsi  = calculate_rsi(prices)
        pred = predict_next(prices)
        sig  = get_signal(prices, rsi, cur, pred)
        return {
            "ticker":    ticker,
            "name":      names.get(ticker, ticker),
            "price":     cur,
            "change":    chg,
            "changePct": chgp,
            "rsi":       rsi,
            "ma7":       moving_average(prices, 7),
            "ma21":      moving_average(prices, 21),
            "ma50":      moving_average(prices, 50),
            "predicted": pred,
            "signal":    sig,
            "sparkline": [round(p,4) for p in prices[-10:]],
            "chart":     [round(p,4) for p in prices[-30:]],
            "dates":     [str(d.date()) for d in hist.index[-30:]],
            "ohlc":      ohlc,
            "high52":    round(max(prices), 4),
            "low52":     round(min(prices), 4),
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None

def fetch_loop():
    while True:
        # Indian
        for t in NIFTY_TICKERS:
            try:
                d = fetch_one(t, NIFTY_NAMES)
                if d:
                    with fetch_lock: nifty_cache[t] = d
            except: pass
            time.sleep(0.3)
        # Global
        for t in GLOBAL_TICKERS:
            try:
                d = fetch_one(t, GLOBAL_NAMES)
                if d:
                    with fetch_lock: global_cache[t] = d
            except: pass
            time.sleep(0.3)
        # Crypto
        for t in CRYPTO_TICKERS:
            try:
                d = fetch_one(t, CRYPTO_NAMES)
                if d:
                    with fetch_lock: crypto_cache[t] = d
            except: pass
            time.sleep(0.3)
        try:
            with fetch_lock:
                socketio.emit('stock_update', {
                    'nifty':  list(nifty_cache.values()),
                    'global': list(global_cache.values()),
                    'crypto': list(crypto_cache.values()),
                })
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Updated {len(nifty_cache)} nifty, {len(global_cache)} global, {len(crypto_cache)} crypto")
        except Exception as e:
            print(f"Emit error: {e}")
        time.sleep(30)

# ── Auth routes ───────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('index.html', username=session['user'])

@app.route('/stock/<market>/<ticker>')
def stock_detail(market, ticker):
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('stock.html', username=session['user'], market=market)

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        d = request.get_json()
        u = d.get('username','').strip().lower()
        p = d.get('password','')
        user = get_user(u)
        if user and user['password'] == hash_pw(p):
            session['user'] = u
            return jsonify({"ok": True})
        return jsonify({"ok": False, "msg": "Invalid username or password"})
    return render_template('auth.html')

@app.route('/register', methods=['POST'])
def register():
    d = request.get_json()
    u = d.get('username','').strip().lower()
    p = d.get('password','')
    if not u or not p:  return jsonify({"ok":False,"msg":"Fill all fields"})
    if len(u) < 3:      return jsonify({"ok":False,"msg":"Username must be 3+ characters"})
    if len(p) < 4:      return jsonify({"ok":False,"msg":"Password must be 4+ characters"})
    if get_user(u):     return jsonify({"ok":False,"msg":"Username already taken"})
    save_user(new_user_doc(u, p))
    session['user'] = u
    return jsonify({"ok": True})

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# ── Stock APIs ────────────────────────────────────────────────────────────────
@app.route('/api/stocks')
def api_stocks():
    if 'user' not in session: return jsonify({}), 401
    with fetch_lock:
        return jsonify({
            'nifty':  list(nifty_cache.values()),
            'global': list(global_cache.values()),
            'crypto': list(crypto_cache.values()),
        })

@app.route('/api/stock/<market>/<ticker>')
def api_stock_detail(market, ticker):
    if 'user' not in session: return jsonify({}), 401
    with fetch_lock:
        if market == 'nifty':
            key = ticker if ticker.endswith('.NS') else ticker+'.NS'
            data = nifty_cache.get(key)
            if not data: data = fetch_one(key, NIFTY_NAMES)
        elif market == 'global':
            data = global_cache.get(ticker)
            if not data: data = fetch_one(ticker, GLOBAL_NAMES)
        else:
            key = ticker if '-USD' in ticker else ticker+'-USD'
            data = crypto_cache.get(key)
            if not data: data = fetch_one(key, CRYPTO_NAMES)
    return jsonify(data or {})

# ── Portfolio API ─────────────────────────────────────────────────────────────
def build_portfolio(u, market):
    portfolio_key    = f'{market}_portfolio'
    cash_key         = f'{market}_cash'
    tx_key           = f'{market}_transactions'
    starting         = NIFTY_CASH if market=='nifty' else GLOBAL_CASH if market=='global' else CRYPTO_CASH
    cache            = nifty_cache if market=='nifty' else global_cache if market=='global' else crypto_cache
    names            = NIFTY_NAMES if market=='nifty' else GLOBAL_NAMES if market=='global' else CRYPTO_NAMES

    portfolio_list = []; total_invested = 0; total_current = 0
    for ticker, pos in u.get(portfolio_key, {}).items():
        with fetch_lock:
            cur_price = cache.get(ticker, {}).get('price', pos['avg_price'])
        invested = pos['qty'] * pos['avg_price']
        current  = pos['qty'] * cur_price
        pnl      = current - invested
        pnl_pct  = (pnl / invested * 100) if invested else 0
        total_invested += invested; total_current += current
        portfolio_list.append({
            'ticker':    ticker,
            'name':      names.get(ticker, ticker),
            'qty':       round(pos['qty'], 6),
            'avg_price': round(pos['avg_price'], 4),
            'cur_price': round(cur_price, 4),
            'invested':  round(invested, 2),
            'current':   round(current, 2),
            'pnl':       round(pnl, 2),
            'pnl_pct':   round(pnl_pct, 2),
        })
    return {
        'cash':           round(u.get(cash_key, 0), 2),
        'portfolio':      portfolio_list,
        'total_invested': round(total_invested, 2),
        'total_current':  round(total_current, 2),
        'total_pnl':      round(total_current - total_invested, 2),
        'transactions':   u.get(tx_key, [])[-30:],
        'starting':       starting,
    }

@app.route('/api/portfolio/<market>')
def api_portfolio(market):
    if 'user' not in session: return jsonify({}), 401
    u = get_user(session['user'])
    return jsonify(build_portfolio(u, market))

# ── Trade API ─────────────────────────────────────────────────────────────────
@app.route('/api/trade', methods=['POST'])
def api_trade():
    if 'user' not in session: return jsonify({"ok":False,"msg":"Login required"}), 401
    d      = request.get_json()
    ticker = d.get('ticker')
    action = d.get('action')
    market = d.get('market','nifty')
    amount = float(d.get('amount', 0))   # buy by amount in currency

    cache = nifty_cache if market=='nifty' else global_cache if market=='global' else crypto_cache
    names = NIFTY_NAMES if market=='nifty' else GLOBAL_NAMES if market=='global' else CRYPTO_NAMES

    portfolio_key = f'{market}_portfolio'
    cash_key      = f'{market}_cash'
    tx_key        = f'{market}_transactions'

    u = get_user(session['user'])
    with fetch_lock:
        stock = cache.get(ticker)
    if not stock: return jsonify({"ok":False,"msg":"Stock data not ready yet, wait 1 min"})

    price = stock['price']
    # Calculate qty from amount
    qty = round(amount / price, 6)
    total = round(price * qty, 2)

    portfolio = u.get(portfolio_key, {})
    cash      = u.get(cash_key, 0)

    if action == 'buy':
        if cash < total:
            return jsonify({"ok":False,"msg":f"Need {total:,.2f} but only {cash:,.2f} available"})
        cash -= total
        if ticker in portfolio:
            pos = portfolio[ticker]; new_qty = pos['qty'] + qty
            pos['avg_price'] = (pos['avg_price']*pos['qty'] + price*qty) / new_qty
            pos['qty'] = new_qty
        else:
            portfolio[ticker] = {'qty': qty, 'avg_price': price}
    elif action == 'sell':
        sell_qty = qty
        if ticker not in portfolio or portfolio[ticker]['qty'] < sell_qty - 0.000001:
            return jsonify({"ok":False,"msg":"Not enough to sell"})
        cash += total
        portfolio[ticker]['qty'] = round(portfolio[ticker]['qty'] - sell_qty, 6)
        if portfolio[ticker]['qty'] <= 0.000001:
            del portfolio[ticker]

    txs = u.get(tx_key, [])
    txs.append({
        'action': action.upper(),
        'ticker': ticker,
        'name':   names.get(ticker, ticker),
        'qty':    round(qty, 6),
        'price':  price,
        'total':  total,
        'time':   datetime.now().strftime("%d %b %H:%M")
    })
    save_user({**u, cash_key: cash, portfolio_key: portfolio, tx_key: txs})
    sym = '₹' if market=='nifty' else '$'
    return jsonify({"ok":True, "cash": round(cash,2), "msg": f"{action.upper()} {round(qty,4)} × {ticker} @ {sym}{price:,.2f}"})

# ── Leaderboard ───────────────────────────────────────────────────────────────
@app.route('/api/leaderboard/<market>')
def api_leaderboard(market):
    cache    = nifty_cache if market=='nifty' else global_cache if market=='global' else crypto_cache
    starting = NIFTY_CASH if market=='nifty' else GLOBAL_CASH if market=='global' else CRYPTO_CASH
    port_key = f'{market}_portfolio'
    cash_key = f'{market}_cash'

    board = []
    for u in users_col.find({}, {'_id': 0}):
        # handle old field names for nifty
        if market == 'nifty' and cash_key not in u:
            cash      = float(u.get('cash', starting))
            portfolio = u.get('portfolio', {})
            tx        = u.get('transactions', [])
        else:
            cash      = u.get(cash_key, starting)
            portfolio = u.get(port_key, {})
            tx        = u.get(f'{market}_transactions', [])

        total = cash
        for ticker, pos in portfolio.items():
            with fetch_lock:
                cur = cache.get(ticker, {}).get('price', pos['avg_price'])
            total += pos['qty'] * cur
        pnl = total - starting
        board.append({
            'username':    u['username'],
            'total_value': round(total, 2),
            'pnl':         round(pnl, 2),
            'pnl_pct':     round((pnl/starting)*100, 2),
            'trades':      len(tx),
            'joined':      u.get('joined', '')
        })
    board.sort(key=lambda x: x['total_value'], reverse=True)
    for i, b in enumerate(board): b['rank'] = i+1
    return jsonify(board)

# ── Socket ────────────────────────────────────────────────────────────────────
@socketio.on('connect')
def on_connect():
    global connected_users
    connected_users += 1
    emit('user_count', {'count': connected_users}, broadcast=True)

@socketio.on('disconnect')
def on_disconnect():
    global connected_users
    connected_users = max(0, connected_users-1)
    emit('user_count', {'count': connected_users}, broadcast=True)

if __name__ == '__main__':
    t = threading.Thread(target=fetch_loop, daemon=True)
    t.start()
    port = int(os.environ.get('PORT', 5000))
    print(f"NiftyPulse v4 -> http://localhost:{port}")
    socketio.run(app, debug=False, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
