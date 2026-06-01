import json
import os
import threading
import webbrowser
import requests
from bs4 import BeautifulSoup
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs, urlencode

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_FILE) as f:
    CONFIG = json.load(f)

TOKEN_FILE = os.path.join(os.path.dirname(__file__), CONFIG["token_file"])

# ── Auth ──────────────────────────────────────────────────────────────────────

auth_code = None

class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global auth_code
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            auth_code = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Login successful! You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>Login failed. Try again.</h2>")

    def log_message(self, *args):
        pass  # suppress server logs


def get_token():
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            return json.load(f)["access_token"]
    return None


def save_token(token_data):
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f)


def login():
    global auth_code
    auth_code = None
    params = {
        "client_id": CONFIG["app_id"],
        "redirect_uri": CONFIG["redirect_uri"],
        "response_type": "code",
        "scope": "boards:read,boards:write,pins:write,pins:read",
    }
    url = "https://www.pinterest.com/oauth/?" + urlencode(params)
    print("\nOpening Pinterest login in your browser...")
    webbrowser.open(url)

    server = HTTPServer(("localhost", 8080), CallbackHandler)
    server.timeout = 120
    server.handle_request()

    if not auth_code:
        print("Login failed — no code received.")
        return None

    resp = requests.post("https://api.pinterest.com/v5/oauth/token", data={
        "grant_type": "authorization_code",
        "code": auth_code,
        "redirect_uri": CONFIG["redirect_uri"],
    }, auth=(CONFIG["app_id"], CONFIG["app_secret"]))

    if resp.status_code == 200:
        token_data = resp.json()
        save_token(token_data)
        print("Login successful! Token saved.")
        return token_data["access_token"]
    else:
        print(f"Token exchange failed: {resp.status_code} {resp.text}")
        return None


# ── Image scraper ─────────────────────────────────────────────────────────────

def fetch_images(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"Could not fetch URL: {e}")
        return [], "", ""

    # Open Graph meta
    og_title = soup.find("meta", property="og:title")
    og_desc = soup.find("meta", property="og:description")
    title = og_title["content"] if og_title else (soup.title.string if soup.title else "")
    description = og_desc["content"] if og_desc else ""

    # Collect images
    images = []
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        images.append(og_img["content"])

    for tag in soup.find_all("img"):
        src = tag.get("src") or tag.get("data-src")
        if src:
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                parsed = urlparse(url)
                src = f"{parsed.scheme}://{parsed.netloc}{src}"
            if src.startswith("http") and src not in images:
                images.append(src)

    return images, title.strip(), description.strip()


# ── Boards ────────────────────────────────────────────────────────────────────

def get_boards(token):
    resp = requests.get("https://api.pinterest.com/v5/boards", headers={
        "Authorization": f"Bearer {token}"
    })
    if resp.status_code == 200:
        return resp.json().get("items", [])
    print(f"Could not fetch boards: {resp.status_code} {resp.text}")
    return []


# ── Create pin ────────────────────────────────────────────────────────────────

def create_pin(token, board_id, image_url, title, description, link):
    payload = {
        "board_id": board_id,
        "title": title,
        "description": description,
        "link": link,
        "media_source": {
            "source_type": "image_url",
            "url": image_url,
        }
    }
    resp = requests.post("https://api.pinterest.com/v5/pins",
                         headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json"},
                         json=payload)
    return resp


# ── Main flow ─────────────────────────────────────────────────────────────────

def main():
    print("=== Pinterest Pin Creator ===\n")

    token = get_token()
    if not token:
        token = login()
    if not token:
        return

    url = input("Paste the URL to pin: ").strip()
    print("\nFetching images...")
    images, title, description = fetch_images(url)

    if not images:
        print("No images found on that page.")
        return

    print(f"\nFound {len(images)} image(s):\n")
    for i, img in enumerate(images[:20], 1):
        print(f"  [{i}] {img}")

    choice = input(f"\nEnter image number(s) — e.g. 1 or 1,2,3 or 'all': ").strip()
    max_imgs = min(len(images), 20)

    if choice.lower() == "all":
        selected_images = images[:max_imgs]
    else:
        selected_images = []
        for c in choice.split(","):
            try:
                selected_images.append(images[int(c.strip()) - 1])
            except (ValueError, IndexError):
                print(f"  Skipping invalid choice: {c.strip()}")

    if not selected_images:
        print("No valid images selected.")
        return

    print(f"\nTitle auto-filled: {title}")
    new_title = input("Press Enter to keep or type a new title: ").strip()
    if new_title:
        title = new_title

    print(f"Description auto-filled: {description}")
    new_desc = input("Press Enter to keep or type a new description: ").strip()
    if new_desc:
        description = new_desc

    boards = get_boards(token)
    if not boards:
        print("No boards found.")
        return

    print("\nYour boards:")
    for i, board in enumerate(boards, 1):
        print(f"  [{i}] {board['name']}")

    b_choice = input(f"\nEnter board number (1-{len(boards)}): ").strip()
    try:
        board_id = boards[int(b_choice) - 1]["id"]
    except (ValueError, IndexError):
        print("Invalid choice.")
        return

    print(f"\nCreating {len(selected_images)} pin(s)...")
    for idx, img_url in enumerate(selected_images, 1):
        resp = create_pin(token, board_id, img_url, title, description, url)
        if resp.status_code == 201:
            pin = resp.json()
            print(f"  [{idx}] Pin created! ID: {pin.get('id')}")
        else:
            print(f"  [{idx}] Failed: {resp.status_code} — {resp.text}")


if __name__ == "__main__":
    main()
