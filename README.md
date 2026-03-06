# 📈 NiftyPulse — Live Nifty 50 Stock Dashboard

A full-stack real-time stock market dashboard built with Python & Flask.
Trade virtual stocks, track your portfolio, and compete on the leaderboard!

## 🚀 Setup

```bash
# 1. Go to project folder
cd C:\Users\Dell\Desktop\niftyv3

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python app.py

# 4. Open browser
http://localhost:5000
```

## 📁 Folder Structure

```
niftyv3\
├── app.py              ← Main server (Flask + SocketIO + all logic)
├── requirements.txt    ← Python dependencies
├── users.json          ← Auto-created, stores all user accounts permanently
├── README.md
└── templates\
    ├── auth.html       ← Login / Register page
    ├── index.html      ← Main dashboard (Live, Predict, Portfolio, Leaderboard)
    └── stock.html      ← Individual stock detail page with chart
```

## ✨ Features

| Feature | Description |
|---------|-------------|
| 🔐 Login / Register | Accounts saved permanently in users.json |
| 📈 Live Prices | All 50 Nifty stocks in ₹ INR, updates every 30s |
| 🔮 AI Predictions | Next-day price forecast using linear regression |
| ⚡ Buy/Sell Signals | RSI + MA crossover + prediction scoring |
| 💼 Mock Trading | Start with ₹1,00,000 virtual cash |
| 📊 Stock Detail Page | Click any stock → 30-day chart with hover prices |
| 🏆 Leaderboard | All users ranked by portfolio value |
| 👥 Live Users | Shows how many people are on site right now |

## 📊 How Signals Work

| Signal | Conditions |
|--------|-----------|
| STRONG BUY | RSI < 35 + MA bullish + prediction up |
| BUY | 1–2 bullish indicators |
| HOLD | Mixed or neutral signals |
| SELL | 1–2 bearish indicators |
| STRONG SELL | RSI > 65 + MA bearish + prediction down |

## 🛠 Tech Stack

- **Flask** — Python web framework
- **Flask-SocketIO** — Real-time WebSocket communication
- **yfinance** — Yahoo Finance live stock data (NSE)
- **NumPy** — RSI calculation + linear regression
- **Chart.js** — Interactive 30-day price chart
- **Vanilla JS** — No React, pure frontend

## ⚠️ Notes

- First load takes **1–2 minutes** to fetch all 50 stocks
- Stock data refreshes every **30 seconds**
- Predictions are for educational purposes only — not financial advice
- Keep CMD window open while using the site
