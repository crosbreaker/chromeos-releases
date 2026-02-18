import json
from collections import defaultdict
from datetime import datetime

import httpx

import common, versions, googleblog, chrome100, git, wayback

GITHUB_REPO = "crosbreaker/chromeos-releases-data"
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/commits"
RAW_DATA_URL = f"https://raw.githubusercontent.com/{GITHUB_REPO}/main/data.json"

DATA_PATH = common.base_path / "data"
OUT_FILE = DATA_PATH / "data.json"

ATTRIBUTION = {
  "platform_version": "0.0.0",
  "chrome_version": "0.0.0.0",
  "kernel_version": None,
  "channel": "Credit: gh://crosbreaker/chromeos-releases-data (original: gh://MercuryWorkshop/chromeos-releases-data)",
  "last_modified": 0,
  "url": "https://github.com/crosbreaker/chromeos-releases-data",
  "__license": "https://github.com/crosbreaker/chromeos-releases-data/blob/main/LICENSE",
  "__license_info": "JSON data is licensed under the Creative Commons Attribution license. If you use this for your own projects, you must include attribution and link to the repository.",
}


class HashableImageDict(dict):
  def __hash__(self):
    return hash(self["url"])


def get_last_updated():
  try:
    r = httpx.get(GITHUB_API, params={"path": "data.json", "per_page": 1},
            headers={"Accept": "application/vnd.github+json"}, timeout=15)
    r.raise_for_status()
    commits = r.json()
    if commits:
      return datetime.fromisoformat(commits[0]["commit"]["committer"]["date"].replace("Z", "+00:00"))
  except Exception as e:
    print(f"Warning: could not fetch last commit timestamp: {e}")
  return None


def load_existing_data():
  try:
    print(f"GET {RAW_DATA_URL}")
    r = httpx.get(RAW_DATA_URL, timeout=60, follow_redirects=True)
    r.raise_for_status()
    return r.json()
  except Exception as e:
    print(f"Warning: could not load existing data.json: {e}")
  return None


def existing_data_as_source(data):
  return {
    board: [img for img in entry["images"] if img.get("platform_version") != "0.0.0"]
    for board, entry in data.items()
  }


def merge_data(*sources):
  merged_sets = defaultdict(set)
  for source in sources:
    for board, images in source.items():
      merged_sets[board] |= {HashableImageDict(img) for img in images}

  merged = {}
  for board, image_set in merged_sets.items():
    images = sorted([dict(img) for img in image_set],
            key=lambda x: (x["last_modified"], x["platform_version"]))
    images.append(ATTRIBUTION)

    brand_names = sorted(common.device_names[board])
    if not brand_names and board in common.brand_name_overrides:
      brand_names = common.brand_name_overrides[board]

    merged[board] = {
      "images": images,
      "brand_names": brand_names,
      "hwid_matches": sorted(common.hwid_matches[board]),
    }

  return dict(sorted(merged.items()))


if __name__ == "__main__":
  last_updated = get_last_updated()
  if last_updated:
    print(f"data.json last committed: {last_updated.isoformat()}")

  existing_data = load_existing_data()
  if existing_data:
    print(f"Loaded existing data.json ({len(existing_data)} boards)")

  print("\nFetching...")
  versions.fetch_all_versions()
  googleblog.fetch_versions_since(since=last_updated)

  sources = [chrome100.get_chrome100_data(), *wayback.get_wayback_data(since=last_updated), *git.get_git_data()]
  if existing_data:
    sources.insert(0, existing_data_as_source(existing_data))

  merged = merge_data(*sources)

  print("\nDone!")
  DATA_PATH.mkdir(exist_ok=True)
  OUT_FILE.write_text(json.dumps(merged, indent=2))
  print(f"Written to {OUT_FILE}")
