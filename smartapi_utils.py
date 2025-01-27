import streamlit as st
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2
import os
import pandas as pd
import pyotp

# Angel One Credentials
ANGEL_API_KEY = os.getenv('ANGEL_API_KEY')
ANGEL_CLIENT_ID = os.getenv('ANGEL_CLIENT_ID')
ANGEL_PASSWORD = os.getenv('ANGEL_PASSWORD')
ANGEL_TOTP_KEY = os.getenv('ANGEL_TOTP_KEY')

def generate_totp(totp_key):
    """Generate TOTP using the provided key"""
    totp = pyotp.TOTP(totp_key)
    return totp.now()

def login_to_smartapi():
    """Login to SmartAPI and return the session object"""
    try:
        obj = SmartConnect(api_key=ANGEL_API_KEY)
        totp = generate_totp(ANGEL_TOTP_KEY)
        data = obj.generateSession(ANGEL_CLIENT_ID, ANGEL_PASSWORD, totp)
        refreshToken = data['data']['refreshToken']
        feedToken = obj.getfeedToken()
        return obj, feedToken
    except Exception as e:
        st.error(f"Error logging in to SmartAPI: {e}")
        return None, None

def place_order(obj, symbol, transaction_type, quantity, price):
    """Place an order using SmartAPI"""
    try:
        order_params = {
            "variety": "NORMAL",
            "tradingsymbol": symbol,
            "symboltoken": "3045",  # Example token, replace with actual token
            "transactiontype": transaction_type,
            "exchange": "NSE",
            "ordertype": "LIMIT",
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": price,
            "squareoff": "0",
            "stoploss": "0",
            "quantity": quantity
        }
        order_id = obj.placeOrder(order_params)
        st.success(f"Order placed successfully. Order ID: {order_id}")
    except Exception as e:
        st.error(f"Error placing order: {e}")

def get_smartapi_portfolio(obj):
    """Fetch and display SmartAPI portfolio details"""
    try:
        portfolio = obj.position()
        if 'data' in portfolio:
            return pd.DataFrame(portfolio['data'])
        else:
            st.warning("No portfolio data available.")
            return None
    except Exception as e:
        st.error(f"Error fetching portfolio: {e}")
        return None

def display_smartapi_portfolio():
    """Display SmartAPI portfolio in a new tab"""
    st.header("SmartAPI Portfolio")
    obj, _ = login_to_smartapi()
    if obj:
        portfolio_df = get_smartapi_portfolio(obj)
        if portfolio_df is not None:
            st.dataframe(portfolio_df, use_container_width=True)

def start_websocket(feed_token, client_id):
    """Start SmartWebSocketV2 for seamless connection"""
    try:
        ss = SmartWebSocketV2(feed_token, client_id)
        
        def on_data(wsapp, message):
            print("Ticks: {}".format(message))
        
        def on_open(wsapp):
            print("WebSocket opened")
        
        def on_close(wsapp):
            print("WebSocket closed")
        
        ss.on_data = on_data
        ss.on_open = on_open
        ss.on_close = on_close
        
        ss.connect()
    except Exception as e:
        st.error(f"Error starting WebSocket: {e}")

