import yfinance as yf
import requests
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
import os
import sys
import time

# --- CONFIGURATION ---
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

# Configure Gemini
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

class SmartTrader:
    def __init__(self, ticker):
        self.ticker = ticker
        try:
            self.company_name = yf.Ticker(ticker).info.get('shortName', ticker)
        except:
            self.company_name = ticker

    def get_working_model_and_response(self, prompt):
        """
        The 'Scanner' Strategy:
        1. Fetches ALL models available to your API key.
        2. Filters for models that support 'generateContent'.
        3. Prioritizes models known to have available quota (Gemma, Flash Lite).
        4. Tries them one by one until successful.
        """
        try:
            all_models = list(genai.list_models())
        except Exception as e:
            print(f"CRITICAL ERROR: Could not list models. Check API Key. Error: {e}")
            return "ERROR: API Key invalid or service down."

        # Filter: Keep only models that can generate text
        text_models = []
        for m in all_models:
            if 'generateContent' in m.supported_generation_methods:
                # Strip 'models/' prefix for cleaner usage
                model_name = m.name.replace('models/', '')
                text_models.append(model_name)

        # OPTIMIZED SORTING: Try Gemma and Lite models first to save time
        def sort_priority(name):
            if 'gemma' in name: return 0            # Best (Likely to work)
            if 'lite' in name: return 1             # Good (Low cost/quota)
            if 'flash' in name and '2.0' not in name: return 2  # Standard Flash
            if 'flash' in name: return 3            # Newer Flash (often busy)
            return 4                                # Heavy Pro models (last resort)

        text_models.sort(key=sort_priority)

        # The Loop of Hope
        for model_name in text_models:
            # Only print the first attempt to keep logs clean, unless it fails
            if text_models.index(model_name) == 0:
                print(f"--- Attempting primary model: {model_name} ---")
            
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                print(f"SUCCESS: Connected to {model_name}!")
                return response.text.strip()
                
            except Exception as e:
                # Silent fail and continue unless it's the last one
                pass
                
        return "ERROR: Tried all available models and none worked. Please check billing/quota."

    def get_stable_news(self):
        if not NEWS_API_KEY:
            print("Error: Missing NewsAPI Key")
            return []
        url = f"https://newsapi.org/v2/everything?q={self.company_name}&apiKey={NEWS_API_KEY}&sortBy=publishedAt&language=en"
        try:
            response = requests.get(url)
            data = response.json()
            articles = data.get('articles', [])[:3] # Limit to 3 articles per stock to save tokens
            return [f"{a['title']} - {a['description']}" for a in articles]
        except Exception as e:
            print(f"News API Error: {e}")
            return []

    def run_analysis(self):
        print(f"\n=== Analyzing {self.ticker} ===")
        
        # 1. Get Price
        price = "Unavailable"
        try:
            stock = yf.Ticker(self.ticker)
            p = stock.history(period="1d")['Close'].iloc[-1]
            price = f"${p:.2f}"
            print(f"Current Price: {price}")
        except:
            print("Warning: Price fetch failed.")

        # 2. Get News
        news = self.get_stable_news()
        if not news:
            print("No news found. Skipping.")
            return

        news_text = "\n".join(news)
        
        # 3. Ask Gemini (Updated Prompt for Explanation)
        prompt = f"""
        You are a senior Wall Street stock analyst. 
        I am looking at stock: {self.ticker} (Price: {price}).
        
        Here is the latest news:
        {news_text}
        
        Based STRICTLY on this news, determine the sentiment.
        
        Your response must follow this exact format:
        ACTION: [BUY, SELL, or HOLD]
        REASON: [Provide a clear, 2-3 sentence explanation of why based on the news provided. Mention specific positive or negative events.]
        """
        
        advice = self.get_working_model_and_response(prompt)
        print(f"Gemini Advice: {advice}")

        # 4. Send Email
        if "BUY" in advice or "SELL" in advice:
            self.send_notification(advice)
        else:
            print("No strong signal. No email sent.")

    def send_notification(self, advice):
        if not EMAIL_SENDER or not EMAIL_PASSWORD:
            print("-> Email credentials missing. Skipping email.")
            return
        msg = MIMEText(f"Gemini Bot Advice for {self.ticker}:\n\n{advice}")
        msg['Subject'] = f"Stock Alert: {self.ticker}"
        msg['From'] = EMAIL_SENDER
        msg['To'] = EMAIL_RECEIVER

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(EMAIL_SENDER, EMAIL_PASSWORD)
                server.send_message(msg)
            print("-> Email notification sent!")
        except Exception as e:
            print(f"-> Failed to send email: {e}")

if __name__ == "__main__":
    # --- EDIT THIS LIST TO CHECK YOUR STOCKS ---
    my_portfolio = ["GOOGL", "IBKR", "TSLA", "NVDA", "UNH"]
    
    print(f"Starting Daily Scan for: {my_portfolio}")
    
    for ticker in my_portfolio:
        bot = SmartTrader(ticker)
        bot.run_analysis()
        # Wait 5 seconds between stocks so we don't hit rate limits
        time.sleep(5)
