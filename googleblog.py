import re
import json
import time
import urllib.parse as urlparse
from datetime import datetime, timezone

import lxml.html

import common

#this module generates a mapping of platform versions to chrome versions by scraping the google releases blog

downloads_path = common.base_path / "downloads" / "googleblog"

start_url = "https://chromereleases.googleblog.com/search?updated-max=2008-10-03T10:59:00-07:00&max-results=20&reverse-paginate=true"

chrome_version_regex = r"[^\.\d](\d+?\.\d+?\.\d+?\.\d+)[^\.\d]"
platform_version_regex = r"[^\.\d](\d+?\.\d+?\.\d+)[^\.\d]"

# most recently fetched page
TERMINAL_FILE = downloads_path / "__terminal__.json"


def _url_to_cache_path(url):
  url_parsed = urlparse.urlparse(url)
  updated_max = urlparse.parse_qs(url_parsed.query)["updated-max"][0]
  return downloads_path / f"{updated_max.replace(':', '_')}.json"


def _cache_path_to_dt(path):
  try:
    return datetime.fromisoformat(path.stem.replace("_", ":"))
  except ValueError:
    return None


def _load_all_cached_versions():
  if not downloads_path.exists():
    return
  for path in downloads_path.glob("*.json"):
    if path.name == TERMINAL_FILE.name:
      continue
    try:
      common.versions.update(json.loads(path.read_text()).get("versions", {}))
    except Exception:
      pass


def fetch_blog_page(url):
  cache_path = _url_to_cache_path(url)

  if cache_path.exists():
    page_info = json.loads(cache_path.read_text())
    common.versions.update(page_info["versions"])
    return page_info["next_url"]

  print(f"GET {url}")
  response = common.session.get(url)
  response.raise_for_status()
  document = lxml.html.fromstring(response.text)

  page_versions = {}
  for post_div in document.cssselect(".post"):
    labels = [e.text_content().strip() for e in post_div.cssselect(".label")]
    if "ChromeOS" not in labels and "Chrome OS" not in labels:
      continue

    post_text_div = post_div.cssselect("div[itemprop='articleBody']")[0]
    post_text = lxml.html.fromstring(post_text_div.text_content().strip()).text_content().strip()

    chrome_versions = set(re.findall(chrome_version_regex, post_text))
    platform_versions = set(re.findall(platform_version_regex, post_text))
    if len(chrome_versions) != 1 or len(platform_versions) != 1:
      continue

    page_versions[platform_versions.pop()] = chrome_versions.pop()

  next_link_els = document.cssselect(".blog-pager-newer-link")
  next_url = None
  if next_link_els:
    href = next_link_els[0].get("href")
    if href != "https://chromereleases.googleblog.com/":
      next_url = href

  page_info = {"versions": page_versions, "next_url": next_url}
  common.versions.update(page_versions)

  cache_path.write_text(json.dumps(page_info, indent=2))

  if next_url is None:
    TERMINAL_FILE.write_text(json.dumps({"terminal_url": url}, indent=2))

  return next_url


def _find_resume_url(since: datetime | None) -> str:
  if not downloads_path.exists():
    return start_url

  dated = sorted(
    (dt, p)
    for p in downloads_path.glob("*.json")
    if p.name != TERMINAL_FILE.name
    and (dt := _cache_path_to_dt(p)) is not None
  )

  if not dated:
    return start_url

  if since is not None and since.tzinfo is None:
    since = since.replace(tzinfo=timezone.utc)

  if since is not None:
    since_utc = since.astimezone(timezone.utc)
    for dt, path in dated:
      if dt.astimezone(timezone.utc) > since_utc:
        path.unlink()
        updated_max = path.stem.replace("_", ":")
        return (
          f"https://chromereleases.googleblog.com/search"
          f"?updated-max={updated_max}&max-results=20&reverse-paginate=true"
        )

  if TERMINAL_FILE.exists():
    info = json.loads(TERMINAL_FILE.read_text())
    terminal_url = info["terminal_url"]
    stale = _url_to_cache_path(terminal_url)
    if stale.exists():
      stale.unlink()
    return terminal_url

  for _dt, path in reversed(dated):
    try:
      page_info = json.loads(path.read_text())
      if page_info.get("next_url"):
        return page_info["next_url"]
    except Exception:
      continue

  return start_url


def _crawl_from(url):
  while url:
    try:
      url = fetch_blog_page(url)
    except IndexError:
      time.sleep(5)
      url = fetch_blog_page(url)


def fetch_all_versions():
  downloads_path.mkdir(exist_ok=True, parents=True)
  _crawl_from(start_url)


def fetch_versions_since(since: datetime | None = None):
  downloads_path.mkdir(exist_ok=True, parents=True)

  _load_all_cached_versions()

  url = _find_resume_url(since)
  print(f"Resuming googleblog fetch from: {url}")
  _crawl_from(url)