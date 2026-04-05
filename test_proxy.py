import requests
import os

proxy_url = "http://mix35348HGX08:plNY9n1t@130.49.79.178:8080"

print(f"Testing Proxy: {proxy_url}")

proxies = {
    "http": proxy_url,
    "https": proxy_url,
}

try:
    print("⏳ Connecting...", flush=True)
    # Test with a public IP checker
    response = requests.get("https://httpbin.org/ip", proxies=proxies, timeout=10)
    print("✅ Proxy Works!")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"❌ Proxy Failed: {e}")
