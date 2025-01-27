import streamlit as st
from datetime import datetime, timedelta
from modules.data_handler import fetch_historical_data
from modules.strategy import calculate_indicators, generate_signals
from modules.dashboards.strategy_dashboard import display_strategy_dashboard
from modules.dashboards.portfolio_dashboard import display_portfolio_dashboard
from modules.dashboards.backtest_dashboard import display_backtest_dashboard
from modules.dashboards.paper_trading_dashboard import display_paper_trading

def main():
    st.set_page_config(page_title="Algo Trading Dashboard", layout="wide")
    
    # Sidebar inputs
    st.sidebar.title("Trading Parameters")
    symbol = st.sidebar.text_input("Symbol", value="SBIN.NS")
    
    # Date range
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30)
    
    # Fetch data
    df = fetch_historical_data(symbol, start_date, end_date)
    
    if df is not None and not df.empty:
        # Calculate indicators
        df = calculate_indicators(df)
        # Generate signals
        df = generate_signals(df)
        
        # Display tabs
        tab1, tab2, tab3, tab4 = st.tabs([
            "Strategy Dashboard", 
            "Portfolio Analysis", 
            "Backtest Analysis",
            "Paper Trading"
        ])
        
        with tab1:
            display_strategy_dashboard(df, symbol)
        
        with tab2:
            display_portfolio_dashboard(df, symbol)
            
        with tab3:
            display_backtest_dashboard(df, symbol)
            
        with tab4:
            display_paper_trading(df, symbol)
    else:
        st.error("No data available for the selected symbol")

if __name__ == "__main__":
    main() 