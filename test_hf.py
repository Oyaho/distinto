# -*- coding: utf-8 -*-
"""
Test script for Hugging Face ViT endpoint.
Usage: python test_hf.py [image_path]
"""

import sys
import os
import json
import urllib.request

HF_API_URL = "https://router.huggingface.co/models/felipeoya/meu-agente-de-bolsas-luxo"
HF_TOKEN   = os.getenv("HF_TOKEN", "")

image_path = sys.argv[1] if len(sys.argv) > 1 else "test.jpeg"

print("")
print("=" * 60)
print("  DISTINTO -- HF Endpoint Test")
print("=" * 60)
print("  Image : " + image_path)
print("  URL   : " + HF_API_URL)
if HF_TOKEN:
    print("  Token : SET (" + HF_TOKEN[:8] + "...)")
else:
    print("  Token : NOT SET [WARNING]")
print("=" * 60)
print("")

# ---- Read image ------------------------------------------------------------
try:
    with open(image_path, "rb") as f:
        image_bytes = f.read()
    print("[1/3] OK  Image loaded: {:,} bytes".format(len(image_bytes)))
except FileNotFoundError:
    print("[1/3] ERR File not found: " + image_path)
    sys.exit(1)

# ---- Build request ---------------------------------------------------------
headers = {
    "Content-Type": "application/octet-stream",
}
if HF_TOKEN:
    headers["Authorization"] = "Bearer " + HF_TOKEN

req = urllib.request.Request(HF_API_URL, data=image_bytes, headers=headers, method="POST")

# ---- Call HF ---------------------------------------------------------------
print("[2/3] --> Sending request to Hugging Face...")
status = None
body   = None
try:
    with urllib.request.urlopen(req, timeout=60) as resp:
        status = resp.status
        body   = resp.read().decode("utf-8")
    print("[2/3] OK  HTTP " + str(status))
except urllib.error.HTTPError as e:
    status = e.code
    body   = e.read().decode("utf-8")
    print("[2/3] ERR HTTP " + str(status))
except Exception as ex:
    print("[2/3] ERR: " + str(ex))
    sys.exit(1)

# ---- Parse & display -------------------------------------------------------
print("")
print("[3/3] Raw response:")
print("  Status : " + str(status))
print("  Body   : " + (body[:500] if body else "(empty)"))

if status == 200:
    try:
        predictions = json.loads(body)
        print("")
        print("-" * 60)
        print("  TOP PREDICTIONS")
        print("-" * 60)
        for i, p in enumerate(predictions[:5]):
            label = p.get("label", "?")
            score = float(p.get("score", 0)) * 100
            bar   = "#" * int(score / 5)
            print("  [{}] {:<35} {:6.2f}%  {}".format(i+1, label, score, bar))
        print("-" * 60)
        top_label = predictions[0]["label"]
        top_score = float(predictions[0]["score"]) * 100
        print("")
        print("  DETECTED: '{}' ({:.2f}%)".format(top_label, top_score))
        print("")
        print("  -- Cross-validation check --")
        norm = top_label.strip().lower().replace("_", " ")
        print("  Normalized label : '" + norm + "'")
        print("  Your blockchain product_name MUST contain this string.")
        print("  Example: register as '" + norm.title() + "' to guarantee the match.")
    except (json.JSONDecodeError, IndexError) as e:
        print("  ERR Could not parse JSON: " + str(e))
elif status == 503:
    print("")
    print("  WARNING: Model is loading (cold start). Wait ~30s and try again.")
    try:
        info = json.loads(body)
        eta = info.get("estimated_time", "?")
        print("  Estimated wait: " + str(eta) + "s")
    except Exception:
        pass
elif status in (401, 403):
    print("")
    print("  ERR: Authentication error.")
    print("  Set HF_TOKEN: $env:HF_TOKEN = 'hf_your_token_here'")
elif status == 404:
    print("")
    print("  ERR: Model not found. Check the model URL.")
else:
    print("")
    print("  Unexpected status. See body above.")

print("")
print("=" * 60)
print("")
