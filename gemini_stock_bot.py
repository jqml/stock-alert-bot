import yfinance as yf
import requests
import google.generativeai as genai
import smtplib
from email.mime.text import MIMEText
import os
import sys

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

    def get_model(self):
        """
        Automatically finds a working, FREE model to avoid 404 and 429 errors.
        """
        try:
            # Ask Google what models are available for this Key
            available_models = [m.name for m in genai.list_models()]
            print(f"DEBUG: Available models: {available_models}")
            
            # Priority list: NEWEST STABLE FLASH models first.
            # We removed '2.0-flash' because it causes Quota (429) errors.
            candidates = [
                'models/gemini-2.5-flash',       # Best new model
                'models/gemini-flash-latest',    # Generic stable alias
                'models/gemini-1.5-flash',       # Old reliable
                'models/gemini-1.5-flash-latest'
            ]

            for candidate in candidates:
                if candidate in available_models:
                    print(f"-> Selected Model: {candidate}")
                    model_name = candidate.replace('models/', '')
                    return genai.GenerativeModel(model_name)
            
            # Fallback: If exact matches fail, look for ANY 'flash' model that isn't '2.0'
            # This is a safety net for regional weirdness
            for m in available_models:
                if 'flash' in m and '2.0' not in m and 'exp' not in m:
                    print(f"-> Fallback Selected: {m}")
                    return genai.GenerativeModel(m.replace('models/', ''))

            print("-> Warning: No standard Flash model found. Forcing 'gemini-2.5-flash'")
            return genai.GenerativeModel('gemini-2.5-flash')

        except Exception as e:
            print(f"Model Selection Error: {e}")
            return genai.GenerativeModel('gemini-2.5-flash')

    def get_stable_news(self):
        if not NEWS_API_KEY:
            print("Error: Missing NewsAPI Key")
            return []
        url = f"https://newsapi.org/v2/everything?q={self.company_name}&apiKey={NEWS_API_KEY}&sortBy=publishedAt&language=en"
        try:
            response = requests.get(url)
            data = response.json()
            articles = data.get('articles', [])[:5]
            return [f"{a['title']} - {a['description']}" for a in articles]
        except Exception as e:
            print(f"News API Error: {e}")
            return []

    def ask_gemini_for_advice(self, news_list, current_price):
        if not GEMINI_API_KEY:
            return "ERROR", "Missing Gemini API Key"
        if not news_list:
            return "NEUTRAL", "No news found."
        
        news_text = "\n".join(news_list)
        price_info = f"${current_price}" if current_price else "Unavailable"
        
        prompt = f"""
        You are a senior Wall Street stock analyst. 
        I am looking at stock: {self.ticker} (Price: {price_info}).
        Here is the latest news:
        {news_text}
        Based STRICTLY on this news, determine the sentiment.
        Reply with ONLY one of these words: BUY, SELL, or HOLD.
        Then, add a dash and a 1-sentence reason.
        """
        try:
            model = self.get_model()
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            return "ERROR", str(e)

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

    def run_analysis(self):
        print(f"--- Running Analysis for {self.ticker} ---")
        price = None
        try:
            stock = yf.Ticker(self.ticker)
            price = stock.history(period="1d")['Close'].iloc[-1]
            print(f"Current Price: ${price:.2f}")
        except Exception as e:
            print(f"Warning: Could not fetch price. Proceeding with News only.")

        news = self.get_stable_news()
        advice = self.ask_gemini_for_advice(news, price)
        print(f"Gemini Says: {advice}")

        if "BUY" in advice or "SELL" in advice:
            self.send_notification(advice)
        else:
            print("No strong signal.")

if __name__ == "__main__":
    bot = SmartTrader("TSLA")
    bot.run_analysis()
