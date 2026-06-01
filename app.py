import json
import os
import webbrowser
import requests
from bs4 import BeautifulSoup
from flask import Flask, render_template, request, jsonify, redirect, session
from urllib.parse import urlparse, urlencode

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "pincreator-secret-key-2026")

APP_ID     = os.environ.get("PINTEREST_APP_ID", "1515450")
APP_SECRET = os.environ.get("PINTEREST_APP_SECRET", "39543cc7a9a0ef5e4b00095e54aa1bbec0d18356")
BASE_URL   = "https://api.pinterest.com/v5"
AUTH_URL   = "https://www.pinterest.com/oauth/"
TOKEN_URL  = "https://api.pinterest.com/v5/oauth/token"

def redirect_uri():
    host = os.environ.get("APP_HOST", "http://localhost:5000")
    return f"{host}/callback"

# ── Token (session-based for web) ─────────────────────────────────────────────

def get_token():
    return session.get("access_token")

# ── Scraper ───────────────────────────────────────────────────────────────────

def fetch_images(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:
        return [], "", ""

    og_title = soup.find("meta", property="og:title")
    og_desc  = soup.find("meta", property="og:description")
    title    = og_title["content"] if og_title else (soup.title.string if soup.title else "")
    desc     = og_desc["content"]  if og_desc  else ""

    images = []
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        images.append(og_img["content"])

    for tag in soup.find_all("img"):
        src = tag.get("src") or tag.get("data-src")
        if src:
            if src.startswith("//"): src = "https:" + src
            elif src.startswith("/"):
                p = urlparse(url)
                src = f"{p.scheme}://{p.netloc}{src}"
            if src.startswith("http") and src not in images:
                images.append(src)

    return images[:20], title.strip(), desc.strip()

# ── API helpers ───────────────────────────────────────────────────────────────

def get_boards(token):
    r = requests.get(f"{BASE_URL}/boards",
                     headers={"Authorization": f"Bearer {token}"})
    return r.json().get("items", []) if r.status_code == 200 else []

def create_pin(token, board_id, image_url, title, description, link):
    payload = {
        "board_id": board_id,
        "title": title,
        "description": description,
        "link": link,
        "media_source": {"source_type": "image_url", "url": image_url}
    }
    return requests.post(f"{BASE_URL}/pins",
                         headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json"},
                         json=payload)

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", logged_in=bool(get_token()))

@app.route("/login")
def login():
    params = {
        "client_id": APP_ID,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": "boards:read,boards:write,pins:write,pins:read",
    }
    return redirect(AUTH_URL + "?" + urlencode(params))

@app.route("/callback")
def callback():
    code = request.args.get("code")
    if not code:
        return redirect("/?error=login_failed")

    resp = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri(),
    }, auth=(APP_ID, APP_SECRET))

    if resp.status_code == 200:
        session["access_token"] = resp.json().get("access_token")
        return redirect("/")
    return redirect("/?error=token_failed")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/fetch", methods=["POST"])
def fetch():
    url = request.json.get("url", "")
    images, title, desc = fetch_images(url)
    return jsonify({"images": images, "title": title, "description": desc})

@app.route("/boards")
def boards():
    token = get_token()
    if not token:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify({"boards": get_boards(token)})

@app.route("/pin", methods=["POST"])
def pin():
    token = get_token()
    if not token:
        return jsonify({"error": "Not logged in"}), 401

    data     = request.json
    board_id = data.get("board_id")
    images   = data.get("images", [])
    title    = data.get("title", "")
    desc     = data.get("description", "")
    link     = data.get("link", "")

    results = []
    for img_url in images:
        r = create_pin(token, board_id, img_url, title, desc, link)
        if r.status_code == 201:
            results.append({"success": True, "id": r.json().get("id"), "image": img_url})
        elif r.status_code == 403:
            results.append({"success": False, "image": img_url,
                            "error": "Standard access pending — Pinterest approval required to publish live pins."})
        else:
            results.append({"success": False, "image": img_url,
                            "error": r.json().get("message", "Unknown error")})

    return jsonify({"results": results})

if __name__ == "__main__":
    is_local = not os.environ.get("APP_HOST")
    if is_local:
        webbrowser.open("http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
