import pandas as pd
import streamlit as st

def calculate_indicators(df):
    """Calculate technical indicators"""
    if df is None or df.empty:
        return None
        
    try:
        ma_length = st.session_state.get('ma_length', 20)
        ema_length = st.session_state.get('ema_length', 10)
        
        # Calculate MA and EMA
        df[f'MA{ma_length}'] = df['Close'].rolling(window=ma_length).mean()
        df[f'EMA{ema_length}'] = df['Close'].ewm(span=ema_length, adjust=False).mean()
        
        # Calculate RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        # Calculate MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['MACD'] = exp1 - exp2
        df['Signal_Line'] = df['MACD'].ewm(span=9, adjust=False).mean()
        df['MACD_Hist'] = df['MACD'] - df['Signal_Line']
        
        return df
        
    except Exception as e:
        st.error(f"Error calculating indicators: {str(e)}")
        return None

def generate_signals(df):
    """Generate trading signals"""
    # ... [Previous generate_signals code] ... 