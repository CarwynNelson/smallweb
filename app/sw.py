import re
from flask import (
    Flask,
    request,
    render_template,
)
import feedparser
from apscheduler.schedulers.background import BackgroundScheduler
import random
from urllib.parse import urlparse, parse_qs
import atexit
import os
import time
from urllib.parse import urlparse

random.seed(time.time())


prefix = os.environ.get("URL_PREFIX", "")
app = Flask(__name__, static_url_path=prefix + "/static")

master_feed = False


def update_all():
    global urls_cache, urls_yt_cache, master_feed

    # url = "http://127.0.0.1:4000"  # testing with local feed
    url = "https://kagi.com/api/v1/smallweb/feed/"

    check_feed = feedparser.parse(url)
    if check_feed:
        master_feed = check_feed

    new_entries = update_entries(url + "?nso")  # no same origin sites feed

    if not bool(urls_cache) or bool(new_entries):
        urls_cache = new_entries

    new_entries = update_entries(url + "?yt")  # youtube sites

    if not bool(urls_yt_cache) or bool(new_entries):
        urls_yt_cache = new_entries

def update_entries(url):
    feed = feedparser.parse(url)
    entries = feed.entries

    if len(entries):
        formatted_entries = []
        for entry in entries:
            domain = entry.link.split("//")[-1].split("/")[0]
            domain = domain.replace("www.", "")
            formatted_entries.append(
                {
                    "domain": domain,
                    "title": entry.title,
                    "link": entry.link,
                    "author": entry.author,
                }
            )

        cache = [
            (entry["link"], entry["title"], entry["author"])
            for entry in formatted_entries
        ]
        print(len(cache), "entries")
        return cache
    else:
        return False


def load_public_suffix_list(file_path):
    public_suffix_list = set()
    with open(file_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("//"):
                public_suffix_list.add(line)
    return public_suffix_list


# Load the list from your actual file path
public_suffix_list = load_public_suffix_list("public_suffix_list.dat")


def get_registered_domain(url):
    parsed_url = urlparse(url)
    netloc_parts = parsed_url.netloc.split(".")
    for i in range(len(netloc_parts)):
        possible_suffix = ".".join(netloc_parts[i:])
        if possible_suffix in public_suffix_list:
            return ".".join(netloc_parts[:i]) + "." + possible_suffix
    

@app.route("/")
def index():
    global urls_cache, urls_yt_cache

    url = request.args.get("url")
    is_youtube = "yt" in request.args
    cache = urls_yt_cache if is_youtube else urls_cache
    title = None

    if url is None:
        random_url, _, _ = random.choice(cache)
        redirect_to = f"?yt&url={random_url}" if is_youtube else f"?url={random_url}"
        return app.redirect(redirect_to, code=307)

    http_url = url.replace("https://", "http://")
    title, _ = next(
        (
            (url_tuple[1], url_tuple[2])
            for url_tuple in cache
            if url_tuple[0] == url or url_tuple[0] == http_url
        ),
        (None, None),
    )

    if title is None:
        query_params = request.args.copy()
        query_string = "&".join(
            f"{key}={value}" for key, value in query_params.items()
        )
        return app.redirect(f"/next?{query_string}", code=307)

    short_url = re.sub(r"^https?://(www\.)?", "", url)
    short_url = short_url.rstrip("/")

    domain = get_registered_domain(url)
    domain = re.sub(r"^(www\.)?", "", domain)

    videoid = ""

    if is_youtube:
        parsed_url = urlparse(url)
        videoid = parse_qs(parsed_url.query)["v"][0]

    if url.startswith("http://"):
        url = url.replace(
            "http://", "https://"
        )  # force https as http will not work inside https iframe anyway

    next_url = random.choice(cache)[0]
    next_url = f"?yt&url={next_url}" if is_youtube else f"?url={next_url}"
    return render_template(
        "index.html",
        url=url,
        next_url=next_url,
        title=title,
        videoid=videoid,
        is_youtube=is_youtube,
        prefix="/",
    )

urls_cache = []
urls_yt_cache = []

# get feeds
update_all()

print("All feeeds updated")

# Update feeds every 1 hour
scheduler = BackgroundScheduler()
scheduler.start()
scheduler.add_job(update_all, "interval", minutes=5)


atexit.register(lambda: scheduler.shutdown())
