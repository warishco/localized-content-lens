import json
import os

import requests
from dotenv import load_dotenv

# Load the API key from a private .env file so it is never committed.
load_dotenv()
API_KEY = os.getenv("SEARCHAPI_KEY")

if not API_KEY or API_KEY == "your_searchapi_key_here":
    raise ValueError("Please set SEARCHAPI_KEY in your .env file.")

# Part 2: Prove one request works before writing any loops.
keyword = "best CRM for small business"

url = "https://www.searchapi.io/api/v1/search"
params = {
    "engine": "google",
    "q": keyword,
    "api_key": API_KEY,
}

response = requests.get(url, params=params, timeout=30)

print("Status code:", response.status_code)
print("URL (redacted):", response.url.replace(API_KEY, "REDACTED"))

data = response.json()
print(json.dumps(data, indent=2)[:5000])
