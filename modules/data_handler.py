import yfinance as yf
import pandas as pd
import streamlit as st

def fetch_historical_data(symbol, start_date, end_date, interval='5m'):
    """Fetch historical data with 5-minute intervals"""
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(
            start=start_date,
            end=end_date,
            interval=interval
        )
        
        df = df.reset_index()
        df['Datetime'] = pd.to_datetime(df['Datetime']).dt.tz_localize(None)
        
        # Filter market hours
        df['time'] = df['Datetime'].dt.time
        market_start = pd.to_datetime('09:15:00').time()
        market_end = pd.to_datetime('15:30:00').time()
        df = df[
            (df['time'] >= market_start) & 
            (df['time'] <= market_end)
        ]
        
        df = df.drop('time', axis=1)
        return df
        
    except Exception as e:
        st.error(f"Error fetching historical data: {str(e)}")
        return None 