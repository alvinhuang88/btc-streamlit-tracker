import streamlit as st
import requests
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time
import json

# Page configuration
st.set_page_config(
    page_title="Real-time BTC/USD Tracker",
    page_icon="₿",
    layout="wide"
)

# Initialize session state for data storage
if 'price_data' not in st.session_state:
    st.session_state.price_data = []
if 'last_update' not in st.session_state:
    st.session_state.last_update = None
if 'aws_api_url' not in st.session_state:
    st.session_state.aws_api_url = ""
if 'aws_api_enabled' not in st.session_state:
    st.session_state.aws_api_enabled = False

def send_to_aws_api(price_data):
    """Send price data to AWS API Gateway"""
    if not st.session_state.aws_api_enabled or not st.session_state.aws_api_url:
        return False
    
    try:
        # Format data as requested: [bid price, bid size, ask price, ask size, trade price, trade size]
        payload = [
            price_data['bid_price'],
            price_data['bid_size'],
            price_data['ask_price'],
            price_data['ask_size'],
            price_data['trade_price'],
            price_data['trade_size']
        ]
        
        # Send POST request to AWS API Gateway
        response = requests.post(
            st.session_state.aws_api_url,
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        response.raise_for_status()
        return True
        
    except requests.exceptions.RequestException as e:
        st.error(f"Error sending to AWS API: {str(e)}")
        return False
    except Exception as e:
        st.error(f"Unexpected error with AWS API: {str(e)}")
        return False

def get_btc_price():
    """Fetch current BTC/USD price and order book data from Coinbase API"""
    try:
        # Get ticker data (price, bid, ask, volume)
        ticker_url = "https://api.exchange.coinbase.com/products/BTC-USD/ticker"
        ticker_response = requests.get(ticker_url, timeout=5)
        ticker_response.raise_for_status()
        ticker_data = ticker_response.json()
        
        # Get order book data for bid/ask sizes
        book_url = "https://api.exchange.coinbase.com/products/BTC-USD/book?level=1"
        book_response = requests.get(book_url, timeout=5)
        book_response.raise_for_status()
        book_data = book_response.json()
        
        current_time = datetime.now()
        
        # Extract bid and ask data from order book (level 1 gives best bid/ask)
        best_bid = book_data['bids'][0] if book_data['bids'] else ['0', '0']
        best_ask = book_data['asks'][0] if book_data['asks'] else ['0', '0']
        
        price_point = {
            'timestamp': current_time,
            'trade_price': float(ticker_data['price']),  # Last trade price
            'trade_size': float(ticker_data['size']),    # Last trade size
            'bid_price': float(best_bid[0]),             # Best bid price
            'bid_size': float(best_bid[1]),              # Best bid size
            'ask_price': float(best_ask[0]),             # Best ask price
            'ask_size': float(best_ask[1]),              # Best ask size
            'volume': float(ticker_data['volume'])       # 24h volume
        }
        
        return price_point
    
    except Exception as e:
        st.error(f"Error fetching data: {str(e)}")
        return None

def update_data():
    """Update the price data and maintain rolling window"""
    new_data = get_btc_price()
    
    if new_data:
        st.session_state.price_data.append(new_data)
        st.session_state.last_update = datetime.now()
        
        # Send to AWS API Gateway if enabled
        aws_success = send_to_aws_api(new_data)
        
        # Keep only last 100 data points to prevent memory issues
        if len(st.session_state.price_data) > 100:
            st.session_state.price_data = st.session_state.price_data[-100:]
        
        return True, aws_success
    return False, False

def create_chart():
    """Create the real-time price chart"""
    if not st.session_state.price_data:
        return None
    
    df = pd.DataFrame(st.session_state.price_data)
    
    fig = go.Figure()
    
    # Add trade price line
    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['trade_price'],
        mode='lines+markers',
        name='Trade Price',
        line=dict(color='orange', width=2),
        marker=dict(size=4)
    ))
    
    # Add bid/ask spread
    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['bid_price'],
        mode='lines',
        name='Bid Price',
        line=dict(color='green', width=1, dash='dash'),
        opacity=0.6
    ))
    
    fig.add_trace(go.Scatter(
        x=df['timestamp'],
        y=df['ask_price'],
        mode='lines',
        name='Ask Price',
        line=dict(color='red', width=1, dash='dash'),
        opacity=0.6
    ))
    
    fig.update_layout(
        title="Real-time BTC/USD Price & Order Book",
        xaxis_title="Time",
        yaxis_title="Price (USD)",
        height=500,
        showlegend=True,
        xaxis=dict(
            showgrid=True,
            gridcolor='lightgray'
        ),
        yaxis=dict(
            showgrid=True,
            gridcolor='lightgray',
            tickformat='$,.2f'
        ),
        plot_bgcolor='white'
    )
    
    return fig

def display_metrics():
    """Display current price metrics"""
    if not st.session_state.price_data:
        return
    
    latest = st.session_state.price_data[-1]
    
    # Calculate price change if we have enough data
    price_change = 0
    price_change_pct = 0
    
    if len(st.session_state.price_data) >= 2:
        previous = st.session_state.price_data[-2]
        price_change = latest['trade_price'] - previous['trade_price']
        price_change_pct = (price_change / previous['trade_price']) * 100
    
    # First row - Main price metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Trade Price",
            value=f"${latest['trade_price']:,.2f}",
            delta=f"${price_change:+.2f}" if price_change != 0 else None
        )
    
    with col2:
        st.metric(
            label="Trade Size",
            value=f"{latest['trade_size']:.4f} BTC"
        )
    
    with col3:
        st.metric(
            label="24h Volume",
            value=f"{latest['volume']:,.2f} BTC"
        )
    
    with col4:
        spread = latest['ask_price'] - latest['bid_price']
        spread_pct = (spread / latest['trade_price']) * 100
        st.metric(
            label="Spread",
            value=f"${spread:.2f}",
            delta=f"{spread_pct:.3f}%"
        )
    
    # Second row - Order book data
    st.markdown("### Order Book")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Bid Price",
            value=f"${latest['bid_price']:,.2f}"
        )
    
    with col2:
        st.metric(
            label="Bid Size",
            value=f"{latest['bid_size']:.4f} BTC"
        )
    
    with col3:
        st.metric(
            label="Ask Price",
            value=f"${latest['ask_price']:,.2f}"
        )
    
    with col4:
        st.metric(
            label="Ask Size",
            value=f"{latest['ask_size']:.4f} BTC"
        )

# Main app layout
st.title("₿ Real-time BTC/USD Tracker")
st.markdown("Live Bitcoin price data from Coinbase API")

# AWS API Configuration Section
st.sidebar.header("🔗 AWS API Gateway Configuration")
aws_url_input = st.sidebar.text_input(
    "AWS API Gateway URL:",
    value=st.session_state.aws_api_url,
    placeholder="https://your-api-id.execute-api.region.amazonaws.com/stage/endpoint",
    help="Enter your AWS API Gateway endpoint URL"
)

aws_enabled = st.sidebar.checkbox(
    "Enable AWS API calls",
    value=st.session_state.aws_api_enabled,
    help="Send data to AWS API Gateway with each update"
)

# Update session state
if aws_url_input != st.session_state.aws_api_url:
    st.session_state.aws_api_url = aws_url_input
if aws_enabled != st.session_state.aws_api_enabled:
    st.session_state.aws_api_enabled = aws_enabled

# Show AWS API status
if st.session_state.aws_api_enabled and st.session_state.aws_api_url:
    st.sidebar.success("✅ AWS API configured and enabled")
elif st.session_state.aws_api_enabled and not st.session_state.aws_api_url:
    st.sidebar.error("❌ AWS API enabled but URL not provided")
else:
    st.sidebar.info("ℹ️ AWS API disabled")

# Data format info
if st.session_state.aws_api_enabled:
    st.sidebar.markdown("""
    **Data Format Sent to AWS:**
    ```json
    [bid_price, bid_size, ask_price, ask_size, trade_price, trade_size]
    ```
    """)

# Control panel
col1, col2, col3 = st.columns([2, 1, 1])

with col1:
    if st.button("🔄 Start/Update Data", type="primary"):
        data_success, aws_success = update_data()
        if data_success:
            if st.session_state.aws_api_enabled:
                if aws_success:
                    st.success("✅ Data updated and sent to AWS API!")
                else:
                    st.warning("⚠️ Data updated but AWS API call failed")
            else:
                st.success("✅ Data updated successfully!")
        else:
            st.error("❌ Failed to fetch data")

with col2:
    auto_refresh = st.checkbox("Auto-refresh", value=False)

with col3:
    if st.button("🗑️ Clear Data"):
        st.session_state.price_data = []
        st.session_state.last_update = None
        st.success("Data cleared!")

# Display last update time
if st.session_state.last_update:
    st.write(f"Last updated: {st.session_state.last_update.strftime('%H:%M:%S')}")

# Auto-refresh logic
if auto_refresh:
    # Auto-refresh every 5 seconds
    placeholder = st.empty()
    
    with placeholder.container():
        data_success, aws_success = update_data()
        if data_success:
            # Display current metrics
            display_metrics()
            
            # Show AWS API status if enabled
            if st.session_state.aws_api_enabled:
                if aws_success:
                    st.info("✅ Data sent to AWS API successfully")
                else:
                    st.warning("⚠️ AWS API call failed")
            
            # Display chart
            chart = create_chart()
            if chart:
                st.plotly_chart(chart, use_container_width=True)
            
            # Show data table
            if st.session_state.price_data:
                st.subheader("Recent Price Data")
                df = pd.DataFrame(st.session_state.price_data)
                df['timestamp'] = df['timestamp'].dt.strftime('%H:%M:%S')
                st.dataframe(df.tail(10), use_container_width=True)
    
    # Wait and refresh
    time.sleep(5)
    st.rerun()

else:
    # Manual mode - display current data
    display_metrics()
    
    chart = create_chart()
    if chart:
        st.plotly_chart(chart, use_container_width=True)
    else:
        st.info("Click 'Start/Update Data' to begin fetching BTC price data")
    
    # Show data table
    if st.session_state.price_data:
        st.subheader("Recent Price Data")
        df = pd.DataFrame(st.session_state.price_data)
        df['timestamp'] = df['timestamp'].dt.strftime('%H:%M:%S')
        st.dataframe(df.tail(10), use_container_width=True)

# Footer
st.markdown("---")
st.markdown("Data provided by Coinbase API | Updates every 5 seconds when auto-refresh is enabled")