import yfinance as yf
import requests
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
import os
import time
import pandas as pd
import numpy as np

# --- CONFIGURATION ---
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

class EnhancedDayTrader:
    def __init__(self, ticker):
        self.ticker = ticker
        try:
            self.company_name = yf.Ticker(ticker).info.get('shortName', ticker)
        except:
            self.company_name = ticker

    def get_working_model_and_response(self, prompt):
        """Scanner strategy to find available Gemini model"""
        try:
            all_models = list(genai.list_models())
        except Exception as e:
            print(f"CRITICAL ERROR: Could not list models. Error: {e}")
            return "ERROR: API Key invalid or service down."

        text_models = []
        for m in all_models:
            if 'generateContent' in m.supported_generation_methods:
                model_name = m.name.replace('models/', '')
                text_models.append(model_name)

        def sort_priority(name):
            if 'gemma' in name: return 0
            if 'lite' in name: return 1
            if 'flash' in name and '2.0' not in name: return 2
            if 'flash' in name: return 3
            return 4

        text_models.sort(key=sort_priority)

        for model_name in text_models:
            if text_models.index(model_name) == 0:
                print(f"--- Attempting primary model: {model_name} ---")
            
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                print(f"SUCCESS: Connected to {model_name}!")
                return response.text.strip()
            except:
                pass
                
        return "ERROR: Tried all available models and none worked."

    def calculate_technical_indicators(self):
        """Calculate EMAs, RSI, MACD for technical analysis"""
        try:
            # Get 4-hour data for day trading (last 30 days to have enough data)
            stock = yf.Ticker(self.ticker)
            df = stock.history(period="30d", interval="1h")
            
            if df.empty:
                return None
            
            # Calculate EMAs
            df['EMA_22'] = df['Close'].ewm(span=22, adjust=False).mean()
            df['EMA_30'] = df['Close'].ewm(span=30, adjust=False).mean()
            df['EMA_48'] = df['Close'].ewm(span=48, adjust=False).mean()
            df['EMA_60'] = df['Close'].ewm(span=60, adjust=False).mean()
            df['EMA_100'] = df['Close'].ewm(span=100, adjust=False).mean()
            df['EMA_200'] = df['Close'].ewm(span=200, adjust=False).mean()
            
            # Calculate RSI
            delta = df['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            df['RSI'] = 100 - (100 / (1 + rs))
            
            # Calculate MACD
            df['EMA_12'] = df['Close'].ewm(span=12, adjust=False).mean()
            df['EMA_26'] = df['Close'].ewm(span=26, adjust=False).mean()
            df['MACD'] = df['EMA_12'] - df['EMA_26']
            df['MACD_Signal'] = df['MACD'].ewm(span=9, adjust=False).mean()
            df['MACD_Histogram'] = df['MACD'] - df['MACD_Signal']
            
            # Get latest values
            latest = df.iloc[-1]
            previous = df.iloc[-2]
            
            # Determine trend based on EMA alignment
            price = latest['Close']
            ema_bullish = (price > latest['EMA_22'] > latest['EMA_30'] > 
                          latest['EMA_48'] > latest['EMA_60'])
            ema_bearish = (price < latest['EMA_22'] < latest['EMA_30'] < 
                          latest['EMA_48'] < latest['EMA_60'])
            
            # Detect candlestick patterns (simplified)
            body = abs(latest['Close'] - latest['Open'])
            upper_shadow = latest['High'] - max(latest['Close'], latest['Open'])
            lower_shadow = min(latest['Close'], latest['Open']) - latest['Low']
            
            candle_pattern = "Neutral"
            if body > 0:
                if lower_shadow > 2 * body and upper_shadow < body:
                    candle_pattern = "Hammer (Bullish Reversal)"
                elif upper_shadow > 2 * body and lower_shadow < body:
                    candle_pattern = "Shooting Star (Bearish Reversal)"
                elif abs(latest['Close'] - latest['Open']) < 0.1 * (latest['High'] - latest['Low']):
                    candle_pattern = "Doji (Indecision)"
            
            # Support and Resistance (using recent swing high/low)
            recent_20 = df.tail(20)
            resistance = recent_20['High'].max()
            support = recent_20['Low'].min()
            
            return {
                'current_price': price,
                'previous_close': previous['Close'],
                'high_24h': df.tail(24)['High'].max(),
                'low_24h': df.tail(24)['Low'].min(),
                'volume': latest['Volume'],
                'avg_volume': df['Volume'].tail(20).mean(),
                
                # EMAs
                'ema_22': latest['EMA_22'],
                'ema_30': latest['EMA_30'],
                'ema_48': latest['EMA_48'],
                'ema_200': latest['EMA_200'],
                'ema_alignment': 'BULLISH' if ema_bullish else ('BEARISH' if ema_bearish else 'MIXED'),
                
                # RSI
                'rsi': latest['RSI'],
                'rsi_signal': 'OVERSOLD' if latest['RSI'] < 30 else ('OVERBOUGHT' if latest['RSI'] > 70 else 'NEUTRAL'),
                
                # MACD
                'macd': latest['MACD'],
                'macd_signal': latest['MACD_Signal'],
                'macd_histogram': latest['MACD_Histogram'],
                'macd_crossover': 'BULLISH' if (latest['MACD'] > latest['MACD_Signal'] and 
                                               previous['MACD'] < previous['MACD_Signal']) else 
                                 ('BEARISH' if (latest['MACD'] < latest['MACD_Signal'] and 
                                               previous['MACD'] > previous['MACD_Signal']) else 'NONE'),
                
                # Patterns
                'candle_pattern': candle_pattern,
                'resistance': resistance,
                'support': support,
                
                # Price action
                'price_change_pct': ((price - previous['Close']) / previous['Close']) * 100,
                'distance_from_ema_200': ((price - latest['EMA_200']) / latest['EMA_200']) * 100
            }
            
        except Exception as e:
            print(f"Technical Analysis Error: {e}")
            return None

    def get_stable_news(self):
        """Fetch latest news"""
        if not NEWS_API_KEY:
            print("Warning: Missing NewsAPI Key")
            return []
        url = f"https://newsapi.org/v2/everything?q={self.company_name}&apiKey={NEWS_API_KEY}&sortBy=publishedAt&language=en"
        try:
            response = requests.get(url)
            data = response.json()
            articles = data.get('articles', [])[:3]
            return [f"{a['title']} - {a['description']}" for a in articles]
        except Exception as e:
            print(f"News API Error: {e}")
            return []

    def run_analysis(self):
        print(f"\n{'='*60}")
        print(f"ANALYZING {self.ticker}")
        print(f"{'='*60}")
        
        # 1. Get Technical Data
        tech_data = self.calculate_technical_indicators()
        if not tech_data:
            print("❌ Could not fetch technical data. Skipping.")
            return
        
        price = tech_data['current_price']
        print(f"💰 Current Price: ${price:.2f} ({tech_data['price_change_pct']:+.2f}%)")
        print(f"📊 24h Range: ${tech_data['low_24h']:.2f} - ${tech_data['high_24h']:.2f}")
        
        # 2. Get News
        news = self.get_stable_news()
        news_text = "\n".join(news) if news else "No recent news found."
        
        # 3. Create comprehensive analysis prompt
        prompt = f"""
You are an elite day trader with 20 years of experience. Analyze this stock for a 4-hour maximum hold time.

STOCK: {self.ticker}
CURRENT PRICE: ${price:.2f}

=== TECHNICAL INDICATORS ===
Price Change: {tech_data['price_change_pct']:+.2f}%
EMA Alignment: {tech_data['ema_alignment']}
- EMA 22: ${tech_data['ema_22']:.2f}
- EMA 200: ${tech_data['ema_200']:.2f}
- Distance from 200 EMA: {tech_data['distance_from_ema_200']:+.2f}%

RSI: {tech_data['rsi']:.1f} ({tech_data['rsi_signal']})

MACD: {tech_data['macd']:.3f}
MACD Signal: {tech_data['macd_signal']:.3f}
MACD Crossover: {tech_data['macd_crossover']}

Candlestick Pattern: {tech_data['candle_pattern']}
Support Level: ${tech_data['support']:.2f}
Resistance Level: ${tech_data['resistance']:.2f}

Volume: {tech_data['volume']:,.0f} (Avg: {tech_data['avg_volume']:,.0f})

=== LATEST NEWS ===
{news_text}

=== YOUR TASK ===
Based on BOTH technical indicators AND news sentiment, provide a day trading setup.

Your response MUST follow this EXACT format:

DIRECTION: [LONG/SHORT/WAIT]
CONFIDENCE: [HIGH/MEDIUM/LOW]
ENTRY: $[specific price]
STOP LOSS: $[specific price]
TAKE PROFIT: $[specific price]
HOLD TIME: [estimate in hours]

TECHNICAL REASONING: [2-3 sentences explaining the technical setup]
NEWS IMPACT: [1-2 sentences on how news affects the trade]
KEY RISK: [1 sentence on the main risk factor]

Be direct. No disclaimers. Assume I understand the risks.
"""
        
        advice = self.get_working_model_and_response(prompt)
        
        print(f"\n{'='*60}")
        print("🤖 AI TRADING ADVICE")
        print(f"{'='*60}")
        print(advice)
        print(f"{'='*60}\n")

        # 4. Send Email if strong signal
        if "DIRECTION: LONG" in advice or "DIRECTION: SHORT" in advice:
            if "CONFIDENCE: HIGH" in advice or "CONFIDENCE: MEDIUM" in advice:
                self.send_notification(advice, tech_data)
            else:
                print("⚠️  Low confidence signal. No email sent.")
        else:
            print("⏸️  WAIT signal. No email sent.")

    def send_notification(self, advice, tech_data):
        """Send email with enhanced formatting"""
        if not EMAIL_SENDER or not EMAIL_PASSWORD:
            print("-> Email credentials missing. Skipping email.")
            return
        
        email_body = f"""
🚨 TRADE ALERT: {self.ticker} 🚨

Current Price: ${tech_data['current_price']:.2f}
Change: {tech_data['price_change_pct']:+.2f}%

{advice}

---
Technical Summary:
• EMA Trend: {tech_data['ema_alignment']}
• RSI: {tech_data['rsi']:.1f} ({tech_data['rsi_signal']})
• MACD: {tech_data['macd_crossover']}
• Pattern: {tech_data['candle_pattern']}

---
Generated at: {time.strftime('%Y-%m-%d %H:%M:%S UTC')}
⚠️ This is automated analysis. Always do your own research.
        """
        
        msg = MIMEText(email_body)
        msg['Subject'] = f"🔥 Trade Setup: {self.ticker}"
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.send_message(msg)
            print("✅ Email notification sent!")
        except Exception as e:
            print(f"❌ Failed to send email: {e}")

if __name__ == "__main__":
    # --- YOUR WATCHLIST ---
    my_portfolio = ["HOOD", "TSLA", "NVDA", "GOOGL", "UNH"]
    
    print(f"\n🚀 Starting Enhanced Day Trading Analysis")
    print(f"📋 Watchlist: {', '.join(my_portfolio)}")
    print(f"⏰ Scan Time: {time.strftime('%Y-%m-%d %H:%M:%S UTC')}\n")
    
    for ticker in my_portfolio:
        bot = EnhancedDayTrader(ticker)
        bot.run_analysis()
        time.sleep(5)  # Rate limit protection
    
    print("\n✅ Scan Complete!")
