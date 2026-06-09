import os
import webbrowser
import requests
from flask import Flask, render_template, request, jsonify, redirect, session
from urllib.parse import urlencode

from crawler import crawl_site, extract_domain
from template_renderer import render_pin

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


def get_token():
    return session.get("access_token")

# ── Pinterest API helpers ─────────────────────────────────────────────────────

def get_boards(token):
    r = requests.get(f"{BASE_URL}/boards",
                     headers={"Authorization": f"Bearer {token}"})
    return r.json().get("items", []) if r.status_code == 200 else []


def create_pin_base64(token, board_id, image_b64, title, description, link):
    payload = {
        "board_id": board_id,
        "title": title,
        "description": description,
        "link": link,
        "media_source": {
            "source_type": "image_base64",
            "content_type": "image/jpeg",
            "data": image_b64,
        },
    }
    return requests.post(
        f"{BASE_URL}/pins",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
    )

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html", logged_in=bool(get_token()))


@app.route("/login")
def login():
    params = {
        "client_id":    APP_ID,
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
        "grant_type":   "authorization_code",
        "code":         code,
        "redirect_uri": redirect_uri(),
    }, auth=(APP_ID, APP_SECRET))
    if resp.status_code == 200:
        session["access_token"] = resp.json().get("access_token")
        return redirect("/")
    return redirect("/?error=token_failed")


@app.route("/nettest")
def nettest():
    import requests, os
    results = {}
    for test_url in [
        "https://chocolatebarnyc.com/dirt-cake-ii/",
        "https://example.com",
        "https://httpbin.org/get",
    ]:
        try:
            r = requests.get(test_url, timeout=8)
            results[test_url] = f"OK {r.status_code}"
        except Exception as ex:
            results[test_url] = f"FAIL {type(ex).__name__}: {str(ex)[:80]}"
    proxy = os.environ.get('http_proxy') or os.environ.get('HTTP_PROXY') or 'none'
    return "<br>".join([f"proxy={proxy}"] + [f"{u}: {v}" for u,v in results.items()])

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


@app.route("/crawl", methods=["POST"])
def crawl():
    url = (request.json or {}).get("url", "").strip()
    if not url:
        return jsonify({"error": "No URL provided"}), 400
    result   = crawl_site(url, max_articles=15)
    articles = result["articles"]
    domain   = extract_domain(url)
    return jsonify({"articles": articles, "domain": domain,
                    "count": len(articles), "error": result["error"]})


@app.route("/boards")
def boards():
    token = get_token()
    if not token:
        return jsonify({"error": "Not logged in"}), 401
    return jsonify({"boards": get_boards(token)})


@app.route("/preview", methods=["POST"])
def preview():
    data = request.json or {}
    try:
        b64 = render_pin(
            data.get("image", ""),
            data.get("title", "Preview Title"),
            data.get("domain", "example.com"),
            data.get("template", "bold"),
        )
        return jsonify({"image": b64})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/pin", methods=["POST"])
def pin():
    token = get_token()
    if not token:
        return jsonify({"error": "Not logged in"}), 401

    data     = request.json or {}
    board_id = data.get("board_id")
    template = data.get("template", "bold")
    domain   = data.get("domain", "")
    articles = data.get("articles", [])

    results = []
    for article in articles:
        img_url     = article.get("image", "")
        title       = article.get("title", "")
        article_url = article.get("url", "")
        try:
            b64 = render_pin(img_url, title, domain, template)
            r   = create_pin_base64(token, board_id, b64, title, title, article_url)
            if r.status_code == 201:
                results.append({
                    "success": True,
                    "id":      r.json().get("id"),
                    "title":   title,
                    "image":   img_url,
                })
            elif r.status_code == 403:
                results.append({
                    "success": False, "title": title, "image": img_url,
                    "error": "Standard access pending — Pinterest approval required.",
                })
            else:
                results.append({
                    "success": False, "title": title, "image": img_url,
                    "error": r.json().get("message", f"Error {r.status_code}"),
                })
        except Exception as e:
            results.append({
                "success": False, "title": title, "image": img_url, "error": str(e),
            })

    return jsonify({"results": results})


if __name__ == "__main__":
    is_local = not os.environ.get("APP_HOST")
    if is_local:
        webbrowser.open("http://localhost:5000")
    app.run(debug=False, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
