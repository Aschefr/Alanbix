import urllib.request
import json

req = urllib.request.Request("http://localhost:8000/tournaments/games/4?force=true", method="DELETE")
try:
    with urllib.request.urlopen(req) as response:
        print("Status:", response.status)
        print("Data:", response.read().decode())
except urllib.error.HTTPError as e:
    print("Status:", e.code)
    print("Error:", e.read().decode())
