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

STARTING_CASH = 100000

NIFTY50 = [
    'RELIANCE.NS','TCS.NS','HDFCBANK.NS','INFY.NS','ICICIBANK.NS',
    'HINDUNILVR.NS','ITC.NS','SBIN.NS','BHARTIARTL.NS','KOTAKBANK.NS',
    'LT.NS','AXISBANK.NS','ASIANPAINT.NS','MARUTI.NS','SUNPHARMA.NS',
    'TITAN.NS','BAJFINANCE.NS','NESTLEIND.NS','WIPRO.NS','ULTRACEMCO.NS',
    'POWERGRID.NS','NTPC.NS','TECHM.NS','HCLTECH.NS','ADANIENT.NS',
    'BAJAJFINSV.NS','ONGC.NS','JSWSTEEL.NS','TATASTEEL.NS','COALINDIA.NS',
    'HINDALCO.NS','DRREDDY.NS','CIPLA.NS','DIVISLAB.NS','APOLLOHOSP.NS',
    'EICHERMOT.NS','HEROMOTOCO.NS','BAJAJ-AUTO.NS','TATACONSUM.NS','BRITANNIA.NS',
    'GRASIM.NS','INDUSINDBK.NS','M&M.NS','ADANIPORTS.NS',
    'SBILIFE.NS','HDFCLIFE.NS','BPCL.NS','IOC.NS','TATAPOWER.NS','PIDILITIND.NS'
]

STOCK_NAMES = {
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
    'BPCL.NS':'BPCL','IOC.NS':'Indian Oil Corp','TATAPOWER.NS':'Tata Power','PIDILITIND.NS':'Pidilite Industries'
}

stock_cache = {}
connected_users = 0
fetch_lock = threading.Lock()

def get_user(username):
    return users_col.find_one({'username': username}, {'_id': 0})

def save_user(u):
    users_col.update_one({'username': u['username']}, {'$set': u}, upsert=True)

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

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
    ma7 = moving_average(prices, 7)
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
    if score >= 3:    return {"action":"STRONG BUY","color":"strong-buy","reasons":reasons,"score":score}
    elif score >= 1:  return {"action":"BUY","color":"buy","reasons":reasons,"score":score}
    elif score <= -3: return {"action":"STRONG SELL","color":"strong-sell","reasons":reasons,"score":score}
    elif score <= -1: return {"action":"SELL","color":"sell","reasons":reasons,"score":score}
    else:             return {"action":"HOLD","color":"hold","reasons":reasons,"score":score}

def fetch_stock(ticker):
    try:
        hist = yf.Ticker(ticker).history(period="60d", interval="1d")
        if hist is None or hist.empty: return None
        prices = [float(p) for p in hist['Close'].tolist() if p is not None and not np.isnan(p)]
        if len(prices) < 5: return None
        cur  = round(prices[-1], 2)
        prev = round(prices[-2], 2) if len(prices) > 1 else cur
        chg  = round(cur - prev, 2)
        chgp = round((chg / prev) * 100, 2) if prev else 0
        rsi  = calculate_rsi(prices)
        pred = predict_next(prices)
        sig  = get_signal(prices, rsi, cur, pred)
        dates = [str(d.date()) for d in hist.index[-30:]]
        chart = [round(float(p), 2) for p in prices[-30:]]
        return {
            "ticker": ticker, "name": STOCK_NAMES.get(ticker, ticker.replace('.NS','')),
            "price": cur, "change": chg, "changePct": chgp, "rsi": rsi,
            "ma7": moving_average(prices,7), "ma21": moving_average(prices,21),
            "ma50": moving_average(prices,50), "predicted": pred, "signal": sig,
            "sparkline": [round(p,2) for p in prices[-10:]],
            "chart": chart, "dates": dates,
            "high52": round(max(prices),2), "low52": round(min(prices),2),
            "timestamp": datetime.now().strftime("%H:%M:%S"),
        }
    except Exception as e:
        print(f"Error {ticker}: {e}")
        return None

def fetch_loop():
    while True:
        for ticker in NIFTY50:
            try:
                d = fetch_stock(ticker)
                if d:
                    with fetch_lock:
                        stock_cache[ticker] = d
            except Exception as e:
                print(f"Skipping {ticker}: {e}")
            time.sleep(0.5)
        try:
            with fetch_lock:
                data = list(stock_cache.values())
            if data:
                socketio.emit('stock_update', {'stocks': data})
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Updated {len(data)} stocks")
        except Exception as e:
            print(f"Emit error: {e}")
        time.sleep(30)

@app.route('/')
def index():
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('index.html', username=session['user'])

@app.route('/stock/<ticker>')
def stock_detail(ticker):
    if 'user' not in session: return redirect(url_for('login'))
    return render_template('stock.html', username=session['user'])

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
    save_user({
        'username': u, 'password': hash_pw(p),
        'cash': float(STARTING_CASH), 'portfolio': {},
        'transactions': [], 'joined': datetime.now().strftime("%d %b %Y")
    })
    session['user'] = u
    return jsonify({"ok": True})

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/api/stocks')
def api_stocks():
    if 'user' not in session: return jsonify([]), 401
    with fetch_lock:
        return jsonify(list(stock_cache.values()))

@app.route('/api/stock/<ticker>')
def api_stock_detail(ticker):
    if 'user' not in session: return jsonify({}), 401
    key = ticker if ticker.endswith('.NS') else ticker + '.NS'
    with fetch_lock:
        data = stock_cache.get(key)
    if not data:
        data = fetch_stock(key)
        if data:
            with fetch_lock:
                stock_cache[key] = data
    return jsonify(data or {})

@app.route('/api/portfolio')
def api_portfolio():
    if 'user' not in session: return jsonify({}), 401
    u = get_user(session['user'])
    portfolio_list = []; total_invested = 0; total_current = 0
    for ticker, pos in u['portfolio'].items():
        with fetch_lock:
            cur_price = stock_cache.get(ticker, {}).get('price', pos['avg_price'])
        invested = pos['qty'] * pos['avg_price']
        current  = pos['qty'] * cur_price
        pnl      = current - invested
        pnl_pct  = (pnl / invested * 100) if invested else 0
        total_invested += invested; total_current += current
        portfolio_list.append({
            'ticker': ticker, 'name': STOCK_NAMES.get(ticker, ticker.replace('.NS','')),
            'qty': pos['qty'], 'avg_price': round(pos['avg_price'],2),
            'cur_price': round(cur_price,2), 'invested': round(invested,2),
            'current': round(current,2), 'pnl': round(pnl,2), 'pnl_pct': round(pnl_pct,2),
        })
    return jsonify({
        'cash': round(u['cash'],2), 'portfolio': portfolio_list,
        'total_invested': round(total_invested,2), 'total_current': round(total_current,2),
        'total_pnl': round(total_current-total_invested,2),
        'transactions': u['transactions'][-30:]
    })

@app.route('/api/trade', methods=['POST'])
def api_trade():
    if 'user' not in session: return jsonify({"ok":False,"msg":"Login required"}), 401
    d = request.get_json()
    ticker = d.get('ticker'); action = d.get('action'); qty = int(d.get('qty',1))
    u = get_user(session['user'])
    with fetch_lock:
        stock = stock_cache.get(ticker)
    if not stock: return jsonify({"ok":False,"msg":"Stock data not ready yet, wait 1 min"})
    price = stock['price']; total = round(price * qty, 2)
    portfolio = u['portfolio']; cash = u['cash']
    if action == 'buy':
        if cash < total:
            return jsonify({"ok":False,"msg":f"Need ₹{total:,.2f} but only ₹{cash:,.2f} available"})
        cash -= total
        if ticker in portfolio:
            pos = portfolio[ticker]; new_qty = pos['qty'] + qty
            pos['avg_price'] = (pos['avg_price']*pos['qty'] + price*qty) / new_qty
            pos['qty'] = new_qty
        else:
            portfolio[ticker] = {'qty': qty, 'avg_price': price}
    elif action == 'sell':
        if ticker not in portfolio or portfolio[ticker]['qty'] < qty:
            return jsonify({"ok":False,"msg":"Not enough shares to sell"})
        cash += total
        portfolio[ticker]['qty'] -= qty
        if portfolio[ticker]['qty'] == 0: del portfolio[ticker]
    transactions = u['transactions']
    transactions.append({
        'action': action.upper(), 'ticker': ticker,
        'name': STOCK_NAMES.get(ticker, ticker), 'qty': qty,
        'price': price, 'total': total, 'time': datetime.now().strftime("%d %b %H:%M")
    })
    save_user({**u, 'cash': cash, 'portfolio': portfolio, 'transactions': transactions})
    return jsonify({"ok":True, "cash": round(cash,2), "msg": f"{action.upper()} {qty} x {ticker.replace('.NS','')} @ Rs.{price:,.2f}"})

@app.route('/api/leaderboard')
def api_leaderboard():
    board = []
    for u in users_col.find({}, {'_id': 0}):
        total = u['cash']
        for ticker, pos in u['portfolio'].items():
            with fetch_lock:
                cur = stock_cache.get(ticker, {}).get('price', pos['avg_price'])
            total += pos['qty'] * cur
        pnl = total - STARTING_CASH
        board.append({
            'username': u['username'], 'total_value': round(total,2),
            'pnl': round(pnl,2), 'pnl_pct': round((pnl/STARTING_CASH)*100,2),
            'trades': len(u.get('transactions',[])), 'joined': u.get('joined','—')
        })
    board.sort(key=lambda x: x['total_value'], reverse=True)
    for i, b in enumerate(board): b['rank'] = i+1
    return jsonify(board)

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
    print(f"NiftyPulse -> http://localhost:{port}")
    socketio.run(app, debug=False, host='0.0.0.0', port=port, allow_unsafe_werkzeug=True)
