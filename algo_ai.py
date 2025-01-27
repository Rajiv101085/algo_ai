# app.py
import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import time
import requests
from bs4 import BeautifulSoup
import json
import brotli
import mplfinance as mpf
from lightweight_charts import Chart
import streamlit.components.v1 as components

# Constants
INDICES = {
    "NIFTY 50": "^NSEI",
    "BANK NIFTY": "^NSEBANK",
    "FINNIFTY": "NIFTY_FIN_SERVICE.NS"
}

SYMBOL_NAMES = {
    "^NSEI": {"name": "NIFTY 50", "lot_size": 75},
    "^NSEBANK": {"name": "BANK NIFTY", "lot_size": 30},
    "NIFTY_FIN_SERVICE.NS": {"name": "FINNIFTY", "lot_size": 65}
}

def get_data(symbol, period='1d', interval='5m'):
    """Fetch data from yfinance"""
    try:
        stock = yf.Ticker(symbol)
        data = stock.history(period=period, interval=interval)
        return data if not data.empty else None
    except Exception as e:
        st.error(f"Error fetching data: {e}")
        return None

def calculate_rsi(prices, period=14):
    """Calculate RSI"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(prices):
    """Calculate MACD"""
    exp1 = prices.ewm(span=12, adjust=False).mean()
    exp2 = prices.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal, macd - signal

def calculate_indicators(df):
    """Calculate all technical indicators"""
    if df is None or df.empty:
        return None
    
    try:
        # Get MA and EMA length from session state or set default
        if 'ma_length' not in st.session_state:
            st.session_state.ma_length = 10
        if 'ema_length' not in st.session_state:
            st.session_state.ema_length = 10
            
        # Calculate MA and EMA with dynamic lengths
        df[f'MA{st.session_state.ma_length}'] = df['Close'].rolling(window=st.session_state.ma_length).mean()
        df[f'EMA{st.session_state.ema_length}'] = df['Close'].ewm(span=st.session_state.ema_length, adjust=False).mean()
        
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
        
        # Fill NaN values
        df = df.fillna(method='bfill')
        
        return df
    except Exception as e:
        st.error(f"Error calculating indicators: {str(e)}")
        return None

def generate_signals(df):
    """Generate trading signals based on EMA-MA crossover strategy"""
    if df is None or df.empty:
        return None
    
    try:
        # Initialize signal columns
        df['Signal'] = 'HOLD'
        df['Trade'] = None
        last_trade = None
        
        ma_col = f'MA{st.session_state.ma_length}'
        ema_col = f'EMA{st.session_state.ema_length}'
        
        # Get previous values for crossover detection
        df['Prev_MA'] = df[ma_col].shift(1)
        df['Prev_EMA'] = df[ema_col].shift(1)
        
        # Determine crossovers (EMA crossing MA)
        df['EMA_Cross_Above_MA'] = (df[ema_col] > df[ma_col]) & (df['Prev_EMA'] <= df['Prev_MA'])
        df['EMA_Cross_Below_MA'] = (df[ema_col] < df[ma_col]) & (df['Prev_EMA'] >= df['Prev_MA'])
        
        # Generate signals based on crossovers
        for i in range(1, len(df)):
            # Buy signal: EMA crosses above MA
            if df['EMA_Cross_Above_MA'].iloc[i] and last_trade != 'BUY':
                df.iloc[i, df.columns.get_loc('Signal')] = 'BUY'
                df.iloc[i, df.columns.get_loc('Trade')] = 'ENTRY'
                last_trade = 'BUY'
            
            # Sell signal: EMA crosses below MA
            elif df['EMA_Cross_Below_MA'].iloc[i] and last_trade != 'SELL':
                df.iloc[i, df.columns.get_loc('Signal')] = 'SELL'
                df.iloc[i, df.columns.get_loc('Trade')] = 'ENTRY'
                last_trade = 'SELL'
            
            # Exit long position
            elif last_trade == 'BUY' and df['EMA_Cross_Below_MA'].iloc[i]:
                df.iloc[i, df.columns.get_loc('Signal')] = 'SELL'
                df.iloc[i, df.columns.get_loc('Trade')] = 'EXIT'
                last_trade = None
            
            # Exit short position
            elif last_trade == 'SELL' and df['EMA_Cross_Above_MA'].iloc[i]:
                df.iloc[i, df.columns.get_loc('Signal')] = 'BUY'
                df.iloc[i, df.columns.get_loc('Trade')] = 'EXIT'
                last_trade = None
        
        # Clean up temporary columns
        df = df.drop(['Prev_MA', 'Prev_EMA', 'EMA_Cross_Above_MA', 'EMA_Cross_Below_MA'], axis=1)
        return df
        
    except Exception as e:
        st.error(f"Error generating signals: {str(e)}")
        return None

def plot_chart(df, title):
    """Create interactive chart using Plotly"""
    fig = go.Figure()

    # Add candlestick chart
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name='Price'
    ))

    # Add MA and EMA
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df[f'MA{st.session_state.ma_length}'],
        name=f'MA{st.session_state.ma_length}',
        line=dict(color='blue')
    ))

    fig.add_trace(go.Scatter(
        x=df.index,
        y=df[f'EMA{st.session_state.ema_length}'],
        name=f'EMA{st.session_state.ema_length}',
        line=dict(color='orange')
    ))

    # Add buy/sell signals
    buy_signals = df[df['Signal'] == 'BUY']
    sell_signals = df[df['Signal'] == 'SELL']

    fig.add_trace(go.Scatter(
        x=buy_signals.index,
        y=buy_signals['Low'] * 0.999,  # Slightly below the candle
        mode='markers',
        name='Buy Signal',
        marker=dict(
            symbol='triangle-up',
            size=12,
            color='green',
        )
    ))

    fig.add_trace(go.Scatter(
        x=sell_signals.index,
        y=sell_signals['High'] * 1.001,  # Slightly above the candle
        mode='markers',
        name='Sell Signal',
        marker=dict(
            symbol='triangle-down',
            size=12,
            color='red',
        )
    ))

    # Update layout
    fig.update_layout(
        title=title,
        yaxis_title='Price',
        xaxis_title='Time',
        template='plotly_white',
        height=600,
        xaxis_rangeslider_visible=False
    )

    return fig

def display_metrics(df):
    """Display key metrics without trade type"""
    if df is None or df.empty:
        return
        
    try:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Price", f"₹{df['Close'].iloc[-1]:.2f}",
                     f"{df['Close'].iloc[-1] - df['Close'].iloc[-2]:.2f}")
        
        with col2:
            if 'RSI' in df.columns:
                rsi_value = df['RSI'].iloc[-1]
                rsi_status = "Overbought" if rsi_value > 70 else "Oversold" if rsi_value < 30 else "Normal"
                st.metric("RSI", f"{rsi_value:.2f}", rsi_status)
            else:
                st.metric("RSI", "N/A")
        
        with col3:
            if 'MACD' in df.columns and 'Signal_Line' in df.columns:
                macd_value = df['MACD'].iloc[-1]
                macd_signal = df['Signal_Line'].iloc[-1]
                macd_status = "Bullish" if macd_value > macd_signal else "Bearish"
                st.metric("MACD", f"{macd_value:.2f}", macd_status)
            else:
                st.metric("MACD", "N/A")
        
        with col4:
            if 'Signal' in df.columns:
                st.metric("Signal", df['Signal'].iloc[-1])
            else:
                st.metric("Signal", "N/A")
                
    except Exception as e:
        st.error(f"Error displaying metrics: {str(e)}")

def get_nearest_strike(spot_price, step=50):
    """Get the nearest strike price"""
    return round(spot_price / step) * step

def get_nse_option_chain(symbol):
    """Fetch NSE option chain data"""
    try:
        # Convert yfinance symbol to NSE symbol
        nse_symbol = {
            "^NSEI": "NIFTY",
            "^NSEBANK": "BANKNIFTY",
            "NIFTY_FIN_SERVICE.NS": "FINNIFTY"
        }.get(symbol)
        
        if not nse_symbol:
            st.error(f"Invalid symbol for options: {symbol}")
            return None, None

        # NSE API URL
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={nse_symbol}"
        
        # Headers to mimic browser request
        headers = {
            'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'accept-encoding': 'gzip, deflate, br',
            'accept-language': 'en-US,en;q=0.9'
        }
        
        # First get the cookie
        session = requests.Session()
        session.get("https://www.nseindia.com", headers=headers)
        
        # Now get the option chain data
        response = session.get(url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            if 'records' not in data:
                return None, None
                
            records = data['records']['data']
            current_price = data['records']['underlyingValue']
            
            options_data = []
            for record in records:
                expiry = record['expiryDate']
                strike = record['strikePrice']
                
                # Process CE data
                if 'CE' in record:
                    ce = record['CE']
                    options_data.append({
                        'type': 'CE',
                        'expiry': expiry,
                        'strike': strike,
                        'ltp': ce['lastPrice'],
                        'change': ce['change'],
                        'volume': ce['totalTradedVolume'],
                        'oi': ce['openInterest'],
                        'iv': ce['impliedVolatility']
                    })
                
                # Process PE data
                if 'PE' in record:
                    pe = record['PE']
                    options_data.append({
                        'type': 'PE',
                        'expiry': expiry,
                        'strike': strike,
                        'ltp': pe['lastPrice'],
                        'change': pe['change'],
                        'volume': pe['totalTradedVolume'],
                        'oi': pe['openInterest'],
                        'iv': pe['impliedVolatility']
                    })
            
            return pd.DataFrame(options_data), current_price
            
        return None, None
    except Exception as e:
        st.error(f"Error fetching option chain: {str(e)}")
        return None, None

def calculate_greeks(row, spot_price, risk_free_rate=0.05, time_to_expiry=None):
    """Calculate option Greeks using Black-Scholes model"""
    from scipy.stats import norm
    import numpy as np
    
    try:
        S = spot_price  # Current stock price
        K = row['strike']  # Strike price
        r = risk_free_rate  # Risk-free rate
        σ = row['iv'] / 100  # Implied volatility (convert from percentage)
        t = time_to_expiry.days / 365 if time_to_expiry else 0.1  # Time to expiry in years
        
        # Calculate d1 and d2
        d1 = (np.log(S/K) + (r + σ**2/2)*t) / (σ*np.sqrt(t))
        d2 = d1 - σ*np.sqrt(t)
        
        # Calculate Greeks
        if row['type'] == 'CE':
            delta = norm.cdf(d1)
            theta = (-S*σ*norm.pdf(d1))/(2*np.sqrt(t)) - r*K*np.exp(-r*t)*norm.cdf(d2)
            gamma = norm.pdf(d1)/(S*σ*np.sqrt(t))
            vega = S*np.sqrt(t)*norm.pdf(d1)
        else:  # PE
            delta = -norm.cdf(-d1)
            theta = (-S*σ*norm.pdf(d1))/(2*np.sqrt(t)) + r*K*np.exp(-r*t)*norm.cdf(-d2)
            gamma = norm.pdf(d1)/(S*σ*np.sqrt(t))
            vega = S*np.sqrt(t)*norm.pdf(d1)
            
        return pd.Series({
            'delta': delta,
            'gamma': gamma,
            'theta': theta,
            'vega': vega
        })
    except Exception as e:
        return pd.Series({
            'delta': None,
            'gamma': None,
            'theta': None,
            'vega': None
        })

def analyze_option_chain(options_df, spot_price):
    """Analyze option chain and generate trading signals"""
    if options_df is None or options_df.empty:
        return None
        
    # Get nearest expiry
    nearest_expiry = options_df['expiry'].min()
    expiry_date = pd.to_datetime(nearest_expiry)
    time_to_expiry = expiry_date - pd.Timestamp.now()
    
    # Filter for nearest expiry
    current_options = options_df[options_df['expiry'] == nearest_expiry].copy()
    
    # Calculate Greeks
    greeks = current_options.apply(
        lambda row: calculate_greeks(row, spot_price, time_to_expiry=time_to_expiry),
        axis=1
    )
    current_options = pd.concat([current_options, greeks], axis=1)
    
    # Calculate PCR (Put-Call Ratio)
    ce_oi = current_options[current_options['type'] == 'CE']['oi'].sum()
    pe_oi = current_options[current_options['type'] == 'PE']['oi'].sum()
    pcr = pe_oi / ce_oi if ce_oi > 0 else 0
    
    # Generate trading signals
    current_options['signal'] = 'NEUTRAL'
    
    # Bullish signals
    bullish_conditions = (
        (current_options['type'] == 'CE') &
        (current_options['delta'] > 0.5) &
        (current_options['gamma'] > 0.02) &
        (current_options['volume'] > current_options['volume'].mean()) &
        (current_options['oi'] > current_options['oi'].mean())
    )
    
    # Bearish signals
    bearish_conditions = (
        (current_options['type'] == 'PE') &
        (current_options['delta'].abs() > 0.5) &
        (current_options['gamma'] > 0.02) &
        (current_options['volume'] > current_options['volume'].mean()) &
        (current_options['oi'] > current_options['oi'].mean())
    )
    
    current_options.loc[bullish_conditions, 'signal'] = 'BUY'
    current_options.loc[bearish_conditions, 'signal'] = 'SELL'
    
    return current_options, pcr

def format_option_name(row, symbol_info):
    """Format option name like 'BANKNIFTY 30 JAN 49000 PUT'"""
    expiry_date = pd.to_datetime(row['expiry']).strftime('%d %b').upper()
    option_type = 'CALL' if row['type'] == 'CE' else 'PUT'
    return f"{symbol_info['name']} {expiry_date} {int(row['strike'])} {option_type}"

def display_options_analysis(df, symbol):
    """Display options chain analysis"""
    st.header("Options Chain Analysis")
    options_df, current_price = get_nse_option_chain(symbol)
    if options_df is not None and current_price is not None:
        analyzed_options, pcr = analyze_option_chain(options_df, current_price)
        if analyzed_options is not None:
            st.metric("Put-Call Ratio (PCR)", f"{pcr:.2f}")
            st.dataframe(analyzed_options, use_container_width=True)
    else:
        st.warning("Unable to fetch options data")

def get_current_signal(spot_price):
    """Get current market signal based on technical and options data"""
    # Implement your signal generation logic here
    # This is a placeholder return
    return {
        'macd_trend': 'Bullish',
        'rsi': 55.5,
        'volume_trend': 'Above Average',
        'atm_iv': 15.5,
        'pcr': 1.2,
        'max_pain': spot_price,
        'signal': 'BUY',
        'strike': f"₹{get_nearest_strike(spot_price):,.2f}",
        'option_type': 'CE',
        'entry_price': spot_price,
        'stop_loss': spot_price * 0.7,
        'target1': spot_price * 1.3,
        'target2': spot_price * 1.5
    }

def format_trade_signal(row, spot_price, symbol_info):
    """Format trade signal with option details"""
    strike = get_nearest_strike(spot_price)
    expiry_date = pd.Timestamp.now().strftime('%d %b').upper()
    
    if row['Signal'] == 'BUY':
        option_type = 'CE' if row['Trade'] == 'ENTRY' else 'PE'
    else:  # SELL
        option_type = 'PE' if row['Trade'] == 'ENTRY' else 'CE'
    
    return pd.Series({
        'Time': row.name.strftime('%H:%M:%S'),
        'Symbol': symbol_info['name'],
        'Price': f"₹{row['Close']:.2f}",
        'Signal': row['Signal'],
        'Trade': row['Trade'],
        'Option': f"{symbol_info['name']} {expiry_date} {strike} {option_type}",
        'Strike': strike,
        'Type': option_type,
        'RSI': f"{row['RSI']:.2f}"
    })

def get_option_symbol(spot_price, signal_type, symbol):
    """Get the appropriate option symbol based on signal and price"""
    try:
        # Get the nearest expiry options data
        options_df, _ = get_nse_option_chain(symbol)
        if options_df is None:
            return None
            
        # Get current week's expiry
        current_expiry = options_df['expiry'].min()
        
        # Get ATM strike price
        atm_strike = get_nearest_strike(spot_price)
        
        # For BUY signal, use CE options; for SELL signal, use PE options
        option_type = 'CE' if signal_type == 'BUY' else 'PE'
        
        # Convert symbol to NSE format
        nse_symbol = {
            "^NSEI": "NIFTY",
            "^NSEBANK": "BANKNIFTY",
            "NIFTY_FIN_SERVICE.NS": "FINNIFTY"
        }.get(symbol)
        
        # Format expiry date
        expiry_str = pd.to_datetime(current_expiry).strftime('%d%b%y').upper()
        
        # Construct option symbol
        option_symbol = f"{nse_symbol}{expiry_str}{atm_strike}{option_type}"
        
        return option_symbol
    except Exception as e:
        st.error(f"Error getting option symbol: {str(e)}")
        return None

def get_option_details(symbol, strike, option_type, expiry):
    """Get detailed option information"""
    try:
        options_df, _ = get_nse_option_chain(symbol)
        if options_df is None:
            return None
            
        # Filter for specific option
        option = options_df[
            (options_df['strike'] == strike) & 
            (options_df['type'] == option_type) & 
            (options_df['expiry'] == expiry)
        ]
        
        if not option.empty:
            return option.iloc[0]
        return None
    except Exception as e:
        st.error(f"Error getting option details: {str(e)}")
        return None

def display_strategy_dashboard(df, symbol):
    """Display detailed technical strategy dashboard with options"""
    st.header("Technical Strategy Dashboard")
    
    # Create columns for key metrics
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.subheader("Trend Indicators")
        ma_col = f'MA{st.session_state.ma_length}'
        ema_col = f'EMA{st.session_state.ema_length}'
        current_price = df['Close'].iloc[-1]
        
        # Trend Status
        trend = "Bullish" if df[ma_col].iloc[-1] > df[ema_col].iloc[-1] else "Bearish"
        trend_strength = abs(df[ma_col].iloc[-1] - df[ema_col].iloc[-1]) / df[ema_col].iloc[-1] * 100
        
        st.metric("Trend Direction", trend)
        st.metric("Trend Strength", f"{trend_strength:.2f}%")
        st.metric("Price vs MA", f"{((current_price - df[ma_col].iloc[-1])/df[ma_col].iloc[-1]*100):.2f}%")
        st.metric("Price vs EMA", f"{((current_price - df[ema_col].iloc[-1])/df[ema_col].iloc[-1]*100):.2f}%")

    with col2:
        st.subheader("Momentum Indicators")
        # RSI Analysis
        rsi = df['RSI'].iloc[-1]
        rsi_condition = "Overbought" if rsi > 70 else "Oversold" if rsi < 30 else "Neutral"
        
        # MACD Analysis
        macd = df['MACD'].iloc[-1]
        signal = df['Signal_Line'].iloc[-1]
        macd_hist = df['MACD_Hist'].iloc[-1]
        macd_condition = "Bullish" if macd > signal else "Bearish"
        
        st.metric("RSI", f"{rsi:.2f}", rsi_condition)
        st.metric("MACD", f"{macd:.2f}", macd_condition)
        st.metric("MACD Histogram", f"{macd_hist:.2f}")
        st.metric("Signal Line", f"{signal:.2f}")

    with col3:
        st.subheader("Trading Signals")
        # Get latest signal
        latest_signal = df['Signal'].iloc[-1]
        signal_time = df.index[-1]
        
        # Count signals
        buy_signals = len(df[df['Signal'] == 'BUY'])
        sell_signals = len(df[df['Signal'] == 'SELL'])
        
        st.metric("Current Signal", latest_signal)
        st.metric("Signal Time", signal_time.strftime('%H:%M:%S'))
        st.metric("Buy Signals Today", buy_signals)
        st.metric("Sell Signals Today", sell_signals)

    # Display Recent Signals Table with Options
    st.subheader("Recent Trading Signals with Options")
    signals_df = df[df['Signal'] != 'HOLD'].copy()
    if not signals_df.empty:
        # Add basic signal information
        signals_df['Time'] = signals_df.index.strftime('%H:%M:%S')
        signals_df['Price'] = signals_df['Close'].round(2)
        signals_df['RSI'] = signals_df['RSI'].round(2)
        signals_df['MACD'] = signals_df['MACD'].round(2)
        
        # Add option information
        signals_df['Option Symbol'] = signals_df.apply(
            lambda row: get_option_symbol(row['Price'], row['Signal'], symbol), 
            axis=1
        )
        
        # Calculate potential returns
        signals_df['Spot Return'] = None
        for i in range(len(signals_df)-1):
            if signals_df['Signal'].iloc[i] == 'BUY':
                signals_df['Spot Return'].iloc[i] = (
                    signals_df['Price'].iloc[i+1] - signals_df['Price'].iloc[i]
                ) / signals_df['Price'].iloc[i] * 100
            elif signals_df['Signal'].iloc[i] == 'SELL':
                signals_df['Spot Return'].iloc[i] = (
                    signals_df['Price'].iloc[i] - signals_df['Price'].iloc[i+1]
                ) / signals_df['Price'].iloc[i] * 100
        
        # Create detailed signals table
        detailed_signals = []
        for _, row in signals_df.iterrows():
            signal_dict = {
                'Time': row['Time'],
                'Signal': row['Signal'],
                'Spot Price': row['Price'],
                'Option Symbol': row['Option Symbol'],
                'RSI': row['RSI'],
                'MACD': row['MACD']
            }
            
            # Get option details if available
            if row['Option Symbol']:
                strike = float(row['Option Symbol'][-7:-2])  # Extract strike from symbol
                option_type = row['Option Symbol'][-2:]      # Extract CE/PE from symbol
                expiry = pd.to_datetime(row['Time']).date()  # Use signal date for expiry
                
                option_data = get_option_details(symbol, strike, option_type, expiry)
                if option_data is not None:
                    signal_dict.update({
                        'Option LTP': option_data['ltp'],
                        'IV': f"{option_data['iv']:.1f}%",
                        'Volume': option_data['volume'],
                        'OI': option_data['oi'],
                        'Delta': f"{option_data.get('delta', 0):.3f}",
                        'Theta': f"{option_data.get('theta', 0):.3f}"
                    })
            
            detailed_signals.append(signal_dict)
        
        # Display detailed signals table
        if detailed_signals:
            st.dataframe(pd.DataFrame(detailed_signals).tail(10), use_container_width=True)

    # Option Chain Summary
    st.subheader("Option Chain Summary")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("ATM Strike", get_nearest_strike(df['Close'].iloc[-1]))
        
    with col2:
        options_df, _ = get_nse_option_chain(symbol)
        if options_df is not None:
            total_ce_oi = options_df[options_df['type'] == 'CE']['oi'].sum()
            total_pe_oi = options_df[options_df['type'] == 'PE']['oi'].sum()
            pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 0
            st.metric("Put-Call Ratio", f"{pcr:.2f}")
            
    with col3:
        if options_df is not None:
            # Calculate max pain
            def calculate_pain(strike_price):
                ce_pain = options_df[
                    (options_df['type'] == 'CE') & 
                    (options_df['strike'] <= strike_price)
                ]['oi'].sum() * (strike_price - df['Close'].iloc[-1])
                
                pe_pain = options_df[
                    (options_df['type'] == 'PE') & 
                    (options_df['strike'] >= strike_price)
                ]['oi'].sum() * (df['Close'].iloc[-1] - strike_price)
                
                return ce_pain + pe_pain
            
            strikes = options_df['strike'].unique()
            pain_values = {strike: calculate_pain(strike) for strike in strikes}
            max_pain = min(pain_values.items(), key=lambda x: x[1])[0]
            st.metric("Max Pain", max_pain)

    # Strategy Performance
    st.subheader("Strategy Performance")
    col1, col2 = st.columns(2)
    
    with col1:
        # Calculate win rate
        completed_trades = signals_df[signals_df['Spot Return'].notna()]
        winning_trades = len(completed_trades[completed_trades['Spot Return'] > 0])
        total_trades = len(completed_trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        st.metric("Win Rate", f"{win_rate:.1f}%")
        st.metric("Total Trades", total_trades)
        
    with col2:
        # Calculate average return
        avg_return = completed_trades['Spot Return'].mean() if not completed_trades.empty else 0
        max_return = completed_trades['Spot Return'].max() if not completed_trades.empty else 0
        
        st.metric("Average Return", f"{avg_return:.2f}%")
        st.metric("Best Trade", f"{max_return:.2f}%")

    # Strategy Rules
    st.subheader("Strategy Rules")
    st.markdown("""
    #### Entry Rules
    - **Buy Signal (Long):**
        - MA crosses above EMA
        - MACD above Signal Line
        - RSI between 30-70
        
    - **Sell Signal (Short):**
        - MA crosses below EMA
        - MACD below Signal Line
        - RSI between 30-70
        
    #### Exit Rules
    - **Technical Exit:**
        - Opposite crossover signal
        - RSI overbought (>70) or oversold (<30)
        - MACD crossover in opposite direction
        
    - **Risk Management:**
        - Stop Loss: 2% from entry
        - Target 1: 3% from entry
        - Target 2: 5% from entry
        - Trailing Stop: Using MA/EMA levels
    """)

class PaperTrade:
    def __init__(self, entry_price, quantity, trade_type, option_symbol, strike, option_type, timestamp):
        self.entry_price = entry_price
        self.exit_price = None
        self.quantity = quantity
        self.trade_type = trade_type  # BUY or SELL
        self.option_symbol = option_symbol
        self.strike = strike
        self.option_type = option_type  # CE or PE
        self.entry_time = timestamp
        self.exit_time = None
        self.pnl = 0
        self.status = "OPEN"
        self.exit_reason = None
        self.trailing_sl = None
        self.target1 = None
        self.target2 = None

def process_auto_trade(latest_signal, df, symbol, quantity):
    """Process auto trading logic based on signals and strategy rules"""
    spot_price = df['Close'].iloc[-1]
    signal_time = latest_signal.name
    
    # Get ATM strike price
    strike = get_nearest_strike(spot_price)
    
    # Get MA and EMA column names
    ma_col = f'MA{st.session_state.ma_length}'
    ema_col = f'EMA{st.session_state.ema_length}'
    
    # Get current technical indicators
    ma = df[ma_col].iloc[-1]
    ema = df[ema_col].iloc[-1]
    rsi = df['RSI'].iloc[-1]
    macd = df['MACD'].iloc[-1]
    signal_line = df['Signal_Line'].iloc[-1]
    
    # Get previous values for crossover detection
    prev_ma = df[ma_col].iloc[-2]
    prev_ema = df[ema_col].iloc[-2]
    
    # Determine crossovers
    ma_cross_above_ema = ma > ema and prev_ma <= prev_ema  # Bullish crossover
    ma_cross_below_ema = ma < ema and prev_ma >= prev_ema  # Bearish crossover
    
    # Determine option type based on signal
    option_type = 'CE' if latest_signal['Signal'] == 'BUY' else 'PE'
    option_symbol = f"{SYMBOL_NAMES[symbol]['name']} {pd.Timestamp.now().strftime('%d %b').upper()} {strike} {option_type}"
    
    # Check for open positions
    open_trades = [t for t in st.session_state.paper_trades if t.status == "OPEN"]
    
    if latest_signal['Trade'] == 'ENTRY':
        # Only enter if no open positions and conditions are met
        if not open_trades:
            # Entry conditions based on MA-EMA cross strategy
            if option_type == 'CE':
                valid_entry = (
                    ma_cross_above_ema and  # MA crosses above EMA
                    macd > signal_line and  # MACD confirmation
                    30 < rsi < 70  # RSI not extreme
                )
            else:  # PE
                valid_entry = (
                    ma_cross_below_ema and  # MA crosses below EMA
                    macd < signal_line and  # MACD confirmation
                    30 < rsi < 70  # RSI not extreme
                )
            
            if valid_entry:
                new_trade = PaperTrade(
                    entry_price=spot_price,
                    quantity=quantity,
                    trade_type=latest_signal['Signal'],
                    option_symbol=option_symbol,
                    strike=strike,
                    option_type=option_type,
                    timestamp=signal_time
                )
                
                # Set risk management levels
                sl_percent = 0.02  # 2% as per strategy
                target1_percent = 0.03  # 3% for T1
                target2_percent = 0.05  # 5% for T2
                
                if option_type == 'CE':
                    new_trade.stop_loss = spot_price * (1 - sl_percent)
                    new_trade.target1 = spot_price * (1 + target1_percent)
                    new_trade.target2 = spot_price * (1 + target2_percent)
                else:  # PE
                    new_trade.stop_loss = spot_price * (1 + sl_percent)
                    new_trade.target1 = spot_price * (1 - target1_percent)
                    new_trade.target2 = spot_price * (1 - target2_percent)
                
                new_trade.trailing_sl = new_trade.stop_loss
                
                st.session_state.paper_trades.append(new_trade)
                return f"Entered {latest_signal['Signal']} position: {option_symbol} at ₹{spot_price:,.2f}"
            return f"Entry conditions not met based on MA{st.session_state.ma_length}-EMA{st.session_state.ema_length} cross strategy"
    
    elif open_trades:
        current_trade = open_trades[0]
        exit_reason = None
        should_exit = False
        
        # Exit conditions based on MA-EMA cross strategy
        if current_trade.option_type == 'CE':
            # Exit conditions for CE
            technical_exit = (
                ma_cross_below_ema or  # MA crosses below EMA
                macd < signal_line or  # MACD crosses below Signal line
                rsi > 70  # RSI overbought
            )
        else:  # PE
            # Exit conditions for PE
            technical_exit = (
                ma_cross_above_ema or  # MA crosses above EMA
                macd > signal_line or  # MACD crosses above Signal line
                rsi < 30  # RSI oversold
            )
        
        # 1. Check technical exit conditions
        if technical_exit:
            should_exit = True
            exit_reason = f"Technical Exit (MA{st.session_state.ma_length}-EMA{st.session_state.ema_length} Cross)"
        
        # 2. Check stop loss
        elif (current_trade.option_type == 'CE' and spot_price <= current_trade.trailing_sl) or \
             (current_trade.option_type == 'PE' and spot_price >= current_trade.trailing_sl):
            should_exit = True
            exit_reason = "Stop Loss Hit"
        
        # 3. Check targets
        elif (current_trade.option_type == 'CE' and spot_price >= current_trade.target2) or \
             (current_trade.option_type == 'PE' and spot_price <= current_trade.target2):
            should_exit = True
            exit_reason = "Target Hit"
        
        # 4. Trail stop loss using MA and EMA
        elif current_trade.option_type == 'CE' and spot_price > current_trade.entry_price:
            new_sl = min(ma, ema, spot_price * 0.98)  # Use the lower of MA/EMA or 2% below price
            if new_sl > current_trade.trailing_sl:
                current_trade.trailing_sl = new_sl
        elif current_trade.option_type == 'PE' and spot_price < current_trade.entry_price:
            new_sl = max(ma, ema, spot_price * 1.02)  # Use the higher of MA/EMA or 2% above price
            if new_sl < current_trade.trailing_sl:
                current_trade.trailing_sl = new_sl
        
        # Execute exit if conditions are met
        if should_exit:
            current_trade.exit_price = spot_price
            current_trade.exit_time = signal_time
            # Calculate P&L based on option type
            if current_trade.option_type == 'CE':
                current_trade.pnl = (spot_price - current_trade.entry_price) * current_trade.quantity
            else:  # PE
                current_trade.pnl = (current_trade.entry_price - spot_price) * current_trade.quantity
            current_trade.status = "CLOSED"
            current_trade.exit_reason = exit_reason
            return f"Exited {current_trade.option_symbol} at ₹{spot_price:,.2f}, P&L: ₹{current_trade.pnl:,.2f}, Reason: {exit_reason}"
    
    return None

def display_paper_trading(df, symbol):
    """Display paper trading dashboard with automated execution"""
    st.title("Paper Trading Dashboard")
    
    # Initialize session state
    if 'paper_trades' not in st.session_state:
        st.session_state.paper_trades = []
    if 'last_signal_time' not in st.session_state:
        st.session_state.last_signal_time = None
    
    # Settings
    st.sidebar.subheader("Strategy Settings")
    st.session_state.ma_length = st.sidebar.number_input(
        "MA Length", 
        min_value=1, 
        value=10,
        key='paper_trading_ma'
    )
    st.session_state.ema_length = st.sidebar.number_input(
        "EMA Length", 
        min_value=1, 
        value=10,
        key='paper_trading_ema'
    )
    
    st.sidebar.subheader("Paper Trading Settings")
    lot_size = SYMBOL_NAMES[symbol]['lot_size']
    num_lots = st.sidebar.number_input(
        "Number of Lots", 
        min_value=1, 
        value=1,
        key='paper_trading_lots'
    )
    quantity = lot_size * num_lots
    auto_trade = st.sidebar.checkbox(
        "Enable Auto Trading", 
        value=True,
        key='paper_trading_auto'
    )
    
    # Current Market Status
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Spot Price", f"₹{df['Close'].iloc[-1]:,.2f}")
    with col2:
        st.metric("Lot Size", lot_size)
    with col3:
        st.metric("Trading Quantity", quantity)
    with col4:
        st.metric("Auto Trading", "Enabled" if auto_trade else "Disabled")
    
    # Get latest signals from strategy
    signals = df[df['Signal'] != 'HOLD'].copy()
    
    # Process new signals automatically
    if auto_trade and not signals.empty:
        latest_signal = signals.iloc[-1]
        signal_time = latest_signal.name
        
        # Check if this is a new signal
        if (st.session_state.last_signal_time is None or 
            signal_time > st.session_state.last_signal_time):
            
            # Process the trade
            result = process_auto_trade(latest_signal, df, symbol, quantity)
            if result:
                st.success(result)
            
            st.session_state.last_signal_time = signal_time
            
            # Force streamlit to rerun to update the display
            st.rerun()
    
    # Display Current Position
    st.subheader("Current Position")
    open_trades = [trade for trade in st.session_state.paper_trades if trade.status == "OPEN"]
    if open_trades:
        current_trade = open_trades[0]
        current_price = df['Close'].iloc[-1]
        
        # Calculate unrealized P&L
        if current_trade.option_type == 'CE':
            unrealized_pnl = (current_price - current_trade.entry_price) * current_trade.quantity
        else:  # PE
            unrealized_pnl = (current_trade.entry_price - current_price) * current_trade.quantity
        
        # Check if we need to update the position
        latest_signal_for_position = signals[signals.index > current_trade.entry_time].iloc[-1] if len(signals[signals.index > current_trade.entry_time]) > 0 else None
        
        if latest_signal_for_position is not None:
            result = process_auto_trade(latest_signal_for_position, df, symbol, quantity)
            if result:
                st.warning(result)
                st.rerun()
        
        position_data = {
            'Option Contract': current_trade.option_symbol,
            'Type': f"{current_trade.trade_type} {current_trade.option_type}",
            'Quantity': current_trade.quantity,
            'Entry Price': f"₹{current_trade.entry_price:,.2f}",
            'Current Price': f"₹{current_price:,.2f}",
            'Unrealized P&L': f"₹{unrealized_pnl:,.2f}",
            'Entry Time': current_trade.entry_time.strftime('%Y-%m-%d %H:%M:%S'),
            'Stop Loss': f"₹{current_trade.trailing_sl:,.2f}" if current_trade.trailing_sl is not None else "Not Set",
            'Target': f"₹{current_trade.target2:,.2f}" if current_trade.target2 is not None else "Not Set"
        }
        
        st.dataframe(pd.DataFrame([position_data]), use_container_width=True)
    else:
        st.info("No open positions")
    
    # Trade History with Cumulative P&L
    st.subheader("Trade History")
    closed_trades = [trade for trade in st.session_state.paper_trades if trade.status == "CLOSED"]
    if closed_trades:
        trade_history = []
        total_pnl = 0
        winning_trades = 0
        
        for trade in closed_trades:
            total_pnl += trade.pnl
            trade_history.append({
                'Option Contract': trade.option_symbol,
                'Type': f"{trade.trade_type} {trade.option_type}",
                'Quantity': trade.quantity,
                'Entry Price': f"₹{trade.entry_price:,.2f}",
                'Exit Price': f"₹{trade.exit_price:,.2f}",
                'P&L': f"₹{trade.pnl:,.2f}",
                'Cumulative P&L': f"₹{total_pnl:,.2f}",
                'Entry Time': trade.entry_time.strftime('%Y-%m-%d %H:%M:%S'),
                'Exit Time': trade.exit_time.strftime('%Y-%m-%d %H:%M:%S'),
                'Exit Reason': trade.exit_reason
            })
            if trade.pnl > 0:
                winning_trades += 1
        
        # Display trade history with sorting and filtering
        trade_df = pd.DataFrame(trade_history)
        st.dataframe(trade_df, use_container_width=True)
        
        # Trading Statistics
        st.subheader("Trading Statistics")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("Total P&L", f"₹{total_pnl:,.2f}")
        with col2:
            win_rate = (winning_trades / len(closed_trades)) * 100
            st.metric("Win Rate", f"{win_rate:.1f}%")
        with col3:
            avg_pnl = total_pnl / len(closed_trades)
            st.metric("Average P&L per Trade", f"₹{avg_pnl:,.2f}")
        with col4:
            st.metric("Total Trades", len(closed_trades))
        
        # P&L Chart
        st.subheader("Cumulative P&L Chart")
        pnl_fig = go.Figure()
        pnl_fig.add_trace(go.Scatter(
            x=[trade['Exit Time'] for trade in trade_history],
            y=[float(trade['Cumulative P&L'].replace('₹', '').replace(',', '')) for trade in trade_history],
            mode='lines+markers',
            name='Cumulative P&L'
        ))
        pnl_fig.update_layout(
            title='Cumulative P&L Over Time',
            xaxis_title='Time',
            yaxis_title='P&L (₹)',
            height=400
        )
        st.plotly_chart(pnl_fig, use_container_width=True)
    else:
        st.info("No trade history")

def calculate_portfolio_metrics(trades):
    """Calculate portfolio performance metrics"""
    if not trades:
        return {}
    
    total_trades = len(trades)
    closed_trades = [t for t in trades if t.status == "CLOSED"]
    total_pnl = sum(t.pnl for t in closed_trades)
    winning_trades = len([t for t in closed_trades if t.pnl > 0])
    
    metrics = {
        'Total Trades': total_trades,
        'Closed Trades': len(closed_trades),
        'Open Trades': len([t for t in trades if t.status == "OPEN"]),
        'Total P&L': total_pnl,
        'Win Rate': (winning_trades / len(closed_trades)) * 100 if closed_trades else 0,
        'Average P&L': total_pnl / len(closed_trades) if closed_trades else 0,
        'Best Trade': max((t.pnl for t in closed_trades), default=0),
        'Worst Trade': min((t.pnl for t in closed_trades), default=0),
        'Average Duration': sum((t.exit_time - t.entry_time).total_seconds() for t in closed_trades) / len(closed_trades) if closed_trades else 0
    }
    
    return metrics

def export_trade_data(filtered_df, report_date):
    """Export trade data to CSV and generate detailed report"""
    
    # Format trade data for CSV export
    export_df = filtered_df.copy()
    
    # Format datetime columns
    export_df['Entry Time'] = export_df['Entry Time'].dt.strftime('%Y-%m-%d %H:%M:%S')
    export_df['Exit Time'] = export_df['Exit Time'].fillna('Active').apply(
        lambda x: x.strftime('%Y-%m-%d %H:%M:%S') if x != 'Active' else x
    )
    
    # Format numeric columns
    export_df['Entry Price'] = export_df['Entry Price'].apply(lambda x: f'₹{x:,.2f}')
    export_df['Exit Price'] = export_df['Exit Price'].fillna('Active').apply(
        lambda x: f'₹{x:,.2f}' if x != 'Active' else x
    )
    export_df['P&L'] = export_df['P&L'].apply(lambda x: f'₹{x:,.2f}' if pd.notnull(x) else 'N/A')
    
    # Calculate summary metrics
    total_trades = len(export_df)
    closed_trades = len(export_df[export_df['Status'] == 'CLOSED'])
    winning_trades = len(export_df[export_df['P&L'].str.contains('-') == False])
    total_pnl = sum([float(x.replace('₹', '').replace(',', '')) 
                    for x in export_df['P&L'] if x != 'N/A'])
    
    # Generate detailed report
    report = f"""
    Trading Performance Report - {report_date.strftime('%Y-%m-%d')}
    ===============================================

    Summary Statistics:
    ------------------
    Total Trades: {total_trades}
    Closed Trades: {closed_trades}
    Open Trades: {total_trades - closed_trades}
    Winning Trades: {winning_trades}
    Win Rate: {(winning_trades/closed_trades*100):.2f}% (of closed trades)
    Total P&L: ₹{total_pnl:,.2f}
    Average P&L per Trade: ₹{(total_pnl/closed_trades):,.2f}

    Trade Distribution:
    ------------------
    Buy Trades: {len(export_df[export_df['Type'] == 'BUY'])}
    Sell Trades: {len(export_df[export_df['Type'] == 'SELL'])}

    Performance Metrics:
    ------------------
    Best Trade: {export_df[export_df['Status'] == 'CLOSED']['P&L'].max()}
    Worst Trade: {export_df[export_df['Status'] == 'CLOSED']['P&L'].min()}
    
    Active Positions:
    ----------------
    {export_df[export_df['Status'] == 'OPEN'].to_string(index=False) if len(export_df[export_df['Status'] == 'OPEN']) > 0 else 'No active positions'}
    """
    
    return export_df, report

def display_portfolio_dashboard(df, symbol):
    """Display portfolio analysis dashboard"""
    st.title("Portfolio Dashboard")
    
    if 'paper_trades' not in st.session_state:
        st.session_state.paper_trades = []
    
    # Portfolio Summary
    st.header("Portfolio Summary")
    col1, col2, col3 = st.columns(3)
    
    # Calculate daily P&L
    today = pd.Timestamp.now(tz='Asia/Kolkata').date()
    today_trades = [t for t in st.session_state.paper_trades 
                   if t.status == "CLOSED" and t.exit_time.date() == today]
    daily_pnl = sum(t.pnl for t in today_trades)
    
    with col1:
        st.metric("Today's P&L", f"₹{daily_pnl:,.2f}")
        
    with col2:
        total_pnl = sum(t.pnl for t in st.session_state.paper_trades if t.status == "CLOSED")
        st.metric("Total P&L", f"₹{total_pnl:,.2f}")
        
    with col3:
        open_positions = len([t for t in st.session_state.paper_trades if t.status == "OPEN"])
        st.metric("Open Positions", open_positions)
    
    # Performance Metrics
    st.subheader("Performance Metrics")
    metrics = calculate_portfolio_metrics(st.session_state.paper_trades)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Win Rate", f"{metrics.get('Win Rate', 0):.1f}%")
        st.metric("Total Trades", metrics.get('Total Trades', 0))
    with col2:
        st.metric("Average P&L", f"₹{metrics.get('Average P&L', 0):,.2f}")
        st.metric("Best Trade", f"₹{metrics.get('Best Trade', 0):,.2f}")
    with col3:
        avg_duration_mins = metrics.get('Average Duration', 0) / 60
        st.metric("Avg Trade Duration", f"{avg_duration_mins:.1f} mins")
        st.metric("Worst Trade", f"₹{metrics.get('Worst Trade', 0):,.2f}")
    with col4:
        st.metric("Closed Trades", metrics.get('Closed Trades', 0))
        st.metric("Open Trades", metrics.get('Open Trades', 0))
    
    # Trade History
    st.header("Trade History")
    
    # Filter options
    col1, col2, col3 = st.columns(3)
    with col1:
        date_filter = st.date_input(
            "Date Range",
            value=(today, today),
            key='portfolio_date_filter'
        )
    with col2:
        status_filter = st.multiselect(
            "Status",
            options=["OPEN", "CLOSED"],
            default=["OPEN", "CLOSED"],
            key='portfolio_status_filter'
        )
    with col3:
        type_filter = st.multiselect(
            "Trade Type",
            options=["BUY", "SELL"],
            default=["BUY", "SELL"],
            key='portfolio_type_filter'
        )
    
    # Create trade history dataframe
    trade_history = []
    for trade in st.session_state.paper_trades:
        trade_dict = {
            'Entry Time': trade.entry_time,
            'Exit Time': trade.exit_time if trade.status == "CLOSED" else None,
            'Symbol': trade.option_symbol,
            'Type': trade.trade_type,
            'Quantity': trade.quantity,
            'Entry Price': trade.entry_price,
            'Exit Price': trade.exit_price,
            'P&L': trade.pnl,
            'Status': trade.status,
            'Exit Reason': trade.exit_reason
        }
        trade_history.append(trade_dict)
    
    trade_df = pd.DataFrame(trade_history).copy()  # Create a proper copy
    
    if not trade_df.empty:
        # Apply filters using .loc
        mask = pd.Series(True, index=trade_df.index)
        
        if date_filter:
            mask &= (trade_df['Entry Time'].dt.date >= date_filter[0]) & \
                   (trade_df['Entry Time'].dt.date <= date_filter[1])
        if status_filter:
            mask &= trade_df['Status'].isin(status_filter)
        if type_filter:
            mask &= trade_df['Type'].isin(type_filter)
        
        filtered_df = trade_df.loc[mask].copy()
        
        # Display filtered trade history
        st.dataframe(filtered_df, use_container_width=True)
    
    # Performance Charts
    st.header("Performance Analysis")
    
    if not filtered_df.empty:
        tab1, tab2, tab3 = st.tabs(["P&L Analysis", "Trade Distribution", "Time Analysis"])
        
        with tab1:
            # Cumulative P&L chart
            closed_trades = filtered_df[filtered_df['Status'] == "CLOSED"].copy()
            if not closed_trades.empty:
                closed_trades['Cumulative P&L'] = closed_trades['P&L'].cumsum()
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=closed_trades['Exit Time'],
                    y=closed_trades['Cumulative P&L'],
                    mode='lines+markers',
                    name='Cumulative P&L'
                ))
                fig.update_layout(
                    title='Cumulative P&L Over Time',
                    xaxis_title='Date',
                    yaxis_title='P&L (₹)',
                    height=400
                )
                st.plotly_chart(fig, use_container_width=True)
        
        with tab2:
            col1, col2 = st.columns(2)
            with col1:
                # Win/Loss Distribution
                win_loss = closed_trades['P&L'].apply(
                    lambda x: 'Win' if x > 0 else 'Loss'
                ).value_counts()
                
                fig = go.Figure(data=[go.Pie(
                    labels=win_loss.index,
                    values=win_loss.values,
                    hole=.3
                )])
                fig.update_layout(title='Win/Loss Distribution')
                st.plotly_chart(fig, use_container_width=True)
            
            with col2:
                # Trade Type Distribution
                trade_types = filtered_df['Type'].value_counts()
                
                fig = go.Figure(data=[go.Pie(
                    labels=trade_types.index,
                    values=trade_types.values,
                    hole=.3
                )])
                fig.update_layout(title='Trade Type Distribution')
                st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            # Trade Duration Analysis
            closed_trades['Duration'] = (
                closed_trades['Exit Time'] - closed_trades['Entry Time']
            ).dt.total_seconds() / 60  # Convert to minutes
            
            fig = go.Figure()
            fig.add_trace(go.Histogram(
                x=closed_trades['Duration'],
                nbinsx=20,
                name='Trade Duration'
            ))
            fig.update_layout(
                title='Trade Duration Distribution',
                xaxis_title='Duration (minutes)',
                yaxis_title='Number of Trades',
                height=400
            )
            st.plotly_chart(fig, use_container_width=True)
    
    # Export Options
    st.header("Export Data")
    col1, col2 = st.columns(2)
    
    with col1:
        if st.button("Export to CSV", key='portfolio_export_csv'):
            if not filtered_df.empty:
                export_df, _ = export_trade_data(filtered_df, today)
                csv = export_df.to_csv(index=False)
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name=f"trade_history_{today.strftime('%Y%m%d')}.csv",
                    mime="text/csv",
                    key='portfolio_download_csv'
                )
            else:
                st.warning("No data to export")
    
    with col2:
        if st.button("Generate Report", key='portfolio_generate_report'):
            if not filtered_df.empty:
                _, report = export_trade_data(filtered_df, today)
                st.download_button(
                    label="Download Report",
                    data=report,
                    file_name=f"trading_report_{today.strftime('%Y%m%d')}.txt",
                    mime="text/plain",
                    key='portfolio_download_report'
                )

    # Preview section
    if not filtered_df.empty:
        st.subheader("Export Preview")
        export_df, _ = export_trade_data(filtered_df, today)
        st.dataframe(export_df.head(), use_container_width=True)
        
        # Display report preview
        with st.expander("Report Preview"):
            _, report = export_trade_data(filtered_df, today)
            st.text(report)

def process_historical_signals(df, symbol):
    """Process all signals generated since market open for paper trading"""
    if 'paper_trades' not in st.session_state:
        st.session_state.paper_trades = []
    
    # Get today's market open time (9:15 AM IST)
    today = pd.Timestamp.now(tz='Asia/Kolkata').date()
    market_open = pd.Timestamp.combine(
        today, 
        pd.Timestamp('09:15:00').time()
    ).tz_localize('Asia/Kolkata')
    
    # Convert df index to IST if it's not already
    df_copy = df.copy()  # Create a copy of the original DataFrame
    if df_copy.index.tz is None:
        df_copy.index = df_copy.index.tz_localize('Asia/Kolkata')
    elif df_copy.index.tz.zone != 'Asia/Kolkata':
        df_copy.index = df_copy.index.tz_convert('Asia/Kolkata')
    
    # Filter signals since market open
    mask = (df_copy.index >= market_open) & (df_copy['Signal'] != 'HOLD')
    signals_df = df_copy.loc[mask].copy()  # Create a proper copy using .loc
    
    if not signals_df.empty:
        for idx, row in signals_df.iterrows():
            # Check if signal already processed
            if not any(t.entry_time == idx for t in st.session_state.paper_trades):
                spot_price = row['Close']
                signal_time = idx
                
                # Create paper trade and process it
                process_trade(spot_price, signal_time, row['Signal'], symbol, signals_df)

def process_trade(spot_price, signal_time, signal, symbol, signals_df):
    """Process individual trade creation and management"""
    # Get ATM strike and option details
    strike = get_nearest_strike(spot_price)
    option_type = 'CE' if signal == 'BUY' else 'PE'
    option_symbol = f"{SYMBOL_NAMES[symbol]['name']} {signal_time.strftime('%d %b').upper()} {strike} {option_type}"
    
    # Create paper trade
    new_trade = PaperTrade(
        entry_price=spot_price,
        quantity=SYMBOL_NAMES[symbol]['lot_size'],
        trade_type=signal,
        option_symbol=option_symbol,
        strike=strike,
        option_type=option_type,
        timestamp=signal_time
    )
    
    # Set risk management levels
    sl_percent = 0.02
    target1_percent = 0.03
    target2_percent = 0.05
    
    if option_type == 'CE':
        new_trade.stop_loss = spot_price * (1 - sl_percent)
        new_trade.target1 = spot_price * (1 + target1_percent)
        new_trade.target2 = spot_price * (1 + target2_percent)
    else:  # PE
        new_trade.stop_loss = spot_price * (1 + sl_percent)
        new_trade.target1 = spot_price * (1 - target1_percent)
        new_trade.target2 = spot_price * (1 - target2_percent)
    
    new_trade.trailing_sl = new_trade.stop_loss
    
    # Process exit for the trade
    next_signal_mask = signals_df.index > signal_time
    next_signal_idx = signals_df.loc[next_signal_mask].index
    
    if len(next_signal_idx) > 0:
        exit_time = next_signal_idx[0]
        exit_price = signals_df.loc[exit_time, 'Close']
        
        new_trade.exit_price = exit_price
        new_trade.exit_time = exit_time
        
        # Calculate P&L
        if new_trade.option_type == 'CE':
            new_trade.pnl = (exit_price - spot_price) * new_trade.quantity
        else:  # PE
            new_trade.pnl = (spot_price - exit_price) * new_trade.quantity
        
        new_trade.status = "CLOSED"
        new_trade.exit_reason = "Signal Reversal"
    
    st.session_state.paper_trades.append(new_trade)

def main():
    st.set_page_config(layout="wide")
    st.title("Advanced Algorithmic Trading Dashboard")
    
    # Sidebar
    st.sidebar.title("Settings")
    
    # Symbol selection
    symbol = st.sidebar.selectbox(
        "Select Index",
        options=list(INDICES.keys()),
        format_func=lambda x: x,
        key='main_symbol'
    )
    symbol = INDICES[symbol]
    
    # Strategy settings
    st.sidebar.subheader("Strategy Settings")
    st.session_state.ma_length = st.sidebar.number_input(
        "MA Length", 
        min_value=1, 
        value=10,
        key='main_ma'
    )
    st.session_state.ema_length = st.sidebar.number_input(
        "EMA Length", 
        min_value=1, 
        value=10,
        key='main_ema'
    )
    
    # Auto refresh
    auto_refresh = st.sidebar.checkbox(
        "Auto Refresh", 
        value=True,
        key='main_auto_refresh'
    )
    refresh_interval = st.sidebar.number_input(
        "Refresh Interval (seconds)", 
        min_value=5, 
        value=10,
        key='main_refresh_interval'
    )
    
    # Initialize or get last refresh time
    if 'last_refresh' not in st.session_state:
        st.session_state.last_refresh = time.time()
    
    # Check if we need to refresh
    current_time = time.time()
    should_refresh = (current_time - st.session_state.last_refresh) > refresh_interval
    
    if auto_refresh and should_refresh:
        st.session_state.last_refresh = current_time
        st.rerun()
    
    # Get data
    df = get_data(symbol)
    
    if df is not None:
        df = calculate_indicators(df)
        df = generate_signals(df)
        
        if df is not None:
            # Process historical signals first
            process_historical_signals(df, symbol)
            
            # Create tabs
            tab1, tab2, tab3, tab4 = st.tabs([
                "Chart & Signals", 
                "Paper Trading",
                "Portfolio",
                "Options Chain"
            ])
            
            with tab1:
                # Display metrics
                display_metrics(df)
                
                # Display Plotly chart
                fig = plot_chart(df, f"{symbol} - 1min")
                st.plotly_chart(fig, use_container_width=True)
                
                # Display strategy dashboard below chart
                display_strategy_dashboard(df, symbol)
            
            with tab2:
                display_paper_trading(df, symbol)
            
            with tab3:
                display_portfolio_dashboard(df, symbol)
            
            with tab4:
                display_options_analysis(df, symbol)

    # Display last refresh time
    st.sidebar.write(f"Last refreshed: {datetime.now().strftime('%H:%M:%S')}")

if __name__ == "__main__":
    main()