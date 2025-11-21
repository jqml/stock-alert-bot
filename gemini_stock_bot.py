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
        Automatically finds a working model to avoid 404 errors.
        """
        try:
            # Ask Google what models are available for this Key
            available = [m.name for m in genai.list_models()]
            print(f"DEBUG: Available models: {available}")
            
            # Try to find the best free one
            if 'models/gemini-1.5-flash' in available:
                print("Using: gemini-1.5-flash")
                return genai.GenerativeModel('gemini-1.5-flash')
            elif 'models/gemini-1.5-flash-latest' in available:
                print("Using: gemini-1.5-flash-latest")
                return genai.GenerativeModel('gemini-1.5-flash-latest')
            elif 'models/gemini-pro' in available:
                print("Using: gemini-pro")
                return genai.GenerativeModel('gemini-pro')
            else:
                print("Warning: Could not find standard model. Trying default 'gemini-1.5-flash'.")
                return genai.GenerativeModel('gemini-1.5-flash')
        except Exception as e:
            print(f"Model Error: {e}")
            return genai.GenerativeModel('gemini-1.5-flash')

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
