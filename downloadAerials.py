import json
import re
from copy import deepcopy
from pickle import FALSE
import requests
import os
import tarfile
import shutil
import urllib3
import time
urllib3.disable_warnings()

RESOURCE_URLS = {
    "tvOS16": "http://sylvan.apple.com/Aerials/resources-16.tar",
    "tvOS13": "http://sylvan.apple.com/Aerials/resources-13.tar",
    "macOS26": "http://sylvan.apple.com/itunes-assets/Aerials126/v4/82/2e/34/822e344c-f5d2-878c-3d56-508d5b09ed61/resources-26-0-1.tar"
}
RESOURCE_PATHS = {}

# Category ID normalization mapping (fixes for source data inconsistencies)
CATEGORY_ID_MAPPING = {
    "A33A55D9-EDEA-4596-A850-6C10B54FBBB6": "A33A55D9-EDEA-4596-A850-6C10B54FBBB5",
    "A33A55D9-EDEA-4596-A850-6C10B54FBBB7": "A33A55D9-EDEA-4596-A850-6C10B54FBBB5",
    "A33A55D9-EDEA-4596-A850-6C10B54FBBB8": "A33A55D9-EDEA-4596-A850-6C10B54FBBB5",
    "A33A55D9-EDEA-4596-A850-6C10B54FBBB9": "A33A55D9-EDEA-4596-A850-6C10B54FBBB5",
}

SKIP_DOWNLOADS = os.environ.get('SKIP_DOWNLOADS', '').lower() in ('1', 'true', 'yes', 'on')

VIDEO_QUALITY = os.environ.get('VIDEO_QUALITY', 'url-4K-SDR-240FPS')

BW_LIMIT = os.environ.get('BW_LIMIT', '').lower() in ('1', 'true', 'yes', 'on')

# Language for localized asset names. Must match a .lproj folder inside
# TVIdleScreenStrings.bundle (e.g. "en", "de", "fr", "ja", "zh_CN").
LANGUAGE = os.environ.get('AERIAL_LANGUAGE', 'en')

RELEASE_VERSION = "0.1.0"

README_PATH = "README.md"
README_TABLE_START = "<!-- AUTO-GENERATED-QUALITIES-TABLE:START -->"
README_TABLE_END = "<!-- AUTO-GENERATED-QUALITIES-TABLE:END -->"

def download_aerial(url, filename, friendly_name):
    chunk_size = 4096
    
    # check if file exists and it is the same size as the downloadable file.
    if os.path.exists(f"downloads/{filename}"):
        response = requests.head(url, verify=False)
        rf_size = response.headers.get("Content-Length")
        lf_size = os.stat(f"downloads/{filename}").st_size
        print(f"\t{friendly_name} ", end="")
        if int(rf_size) == int(lf_size): 
            print("exists: skipping...")
            return
        else:
            print(f"exists, but has a size of {int(lf_size)/(1024*1024):.2f} MB v {int(rf_size)/(1024*1024):.2f} MB: downloading...")

    with requests.get(url, stream=True, verify=False) as r:
        file_size = r.headers.get("Content-Length")
        with open(f"downloads/{filename}", 'wb') as f:
            received = 0
            for chunk in r.iter_content(chunk_size): 
                if BW_LIMIT: time.sleep(0.004) # approx 1 MB/s
                if chunk:
                    received += chunk_size
                    print(f"\t({int(received)/(1024*1024):.2f} MB/{int(file_size)/(1024*1024):.2f} MB)", end="\r")
                    f.write(chunk)
    print("")

def load_localizations(language=None):
    """Load _NAME strings from TVIdleScreenStrings.bundle for the given language.

    Searches all RESOURCE_PATHS for the bundle, merges results (later sources
    win), and falls back to 'en' if the requested language lproj is absent.
    """
    import plistlib
    lang = language or LANGUAGE
    strings = {}
    for resource_path in RESOURCE_PATHS.values():
        bundle = os.path.join(resource_path, 'TVIdleScreenStrings.bundle')
        if not os.path.isdir(bundle):
            continue
        # Try exact language, then base language (en_AU -> en), then 'en'
        candidates = [lang]
        if '_' in lang:
            candidates.append(lang.split('_')[0])
        if lang != 'en':
            candidates.append('en')
        for candidate in candidates:
            strings_file = os.path.join(bundle, f'{candidate}.lproj', 'Localizable.nocache.strings')
            if os.path.exists(strings_file):
                with open(strings_file, 'rb') as f:
                    strings.update(plistlib.load(f))
                break
    return strings

def get_available_languages():
    """Return sorted language codes found in TVIdleScreenStrings.bundle .lproj folders."""
    languages = set()
    for resource_path in RESOURCE_PATHS.values():
        bundle = os.path.join(resource_path, 'TVIdleScreenStrings.bundle')
        if not os.path.isdir(bundle):
            continue

        for entry in os.listdir(bundle):
            if not entry.endswith('.lproj'):
                continue
            language = entry[:-6]
            strings_file = os.path.join(bundle, entry, 'Localizable.nocache.strings')
            if language and os.path.isfile(strings_file):
                languages.add(language)

    return sorted(languages, key=lambda code: code.lower())

def build_subcategory_map(all_metadata, strings=None):
    """Build {subcategory_id: display_name} from category definitions."""
    subcategory_map = {}
    for metadata in all_metadata.values():
        for category in metadata.get('categories', []):
            for subcat in category.get('subcategories', []):
                sid = subcat.get('id')
                name_key = subcat.get('localizedNameKey', '')
                if sid and name_key:
                    if strings and name_key in strings:
                        subcategory_map[sid] = strings[name_key]
                    else:
                        # Fallback: strip AerialSubcategory/AerialCategory prefix and split CamelCase
                        import re as _re
                        key = name_key
                        for prefix in ('AerialSubcategory', 'AerialCategory'):
                            if key.startswith(prefix):
                                key = key[len(prefix):]
                                break
                        subcategory_map[sid] = _re.sub(r'([a-z])([A-Z])', r'\1 \2', key)
    return subcategory_map

def build_category_map(all_metadata, strings=None):
    """Build {category_id: display_name} from top-level categories."""
    category_map = {}
    for metadata in all_metadata.values():
        for category in metadata.get('categories', []):
            cid = category.get('id')
            name_key = category.get('localizedNameKey', '')
            if cid and name_key:
                if strings and name_key in strings:
                    category_map[cid] = strings[name_key]
                else:
                    import re as _re
                    key = name_key
                    for prefix in ('AerialSubcategory', 'AerialCategory'):
                        if key.startswith(prefix):
                            key = key[len(prefix):]
                            break
                    category_map[cid] = _re.sub(r'([a-z])([A-Z])', r'\1 \2', key)
    return category_map

def build_poi_map(all_metadata, strings=None):
    """Build {poi_id: localized_name} map from all assets' pointsOfInterest.
    
    If strings dict provided, looks up POI IDs directly (no _NAME suffix).
    Falls back to returning the POI ID as-is if not found in strings.
    """
    poi_map = {}
    for metadata in all_metadata.values():
        for asset in metadata.get('assets', []):
            pois = asset.get('pointsOfInterest', {})
            if isinstance(pois, dict):
                for poi_id in pois.values():
                    if poi_id and poi_id not in poi_map:
                        if strings and poi_id in strings:
                            poi_map[poi_id] = strings[poi_id]
                        else:
                            poi_map[poi_id] = poi_id  # Fallback to ID itself
    return poi_map

def merge_asset_records(base_asset, new_asset):
    for key, value in new_asset.items():
        if key not in base_asset:
            base_asset[key] = value
            continue

        existing = base_asset[key]

        if isinstance(existing, dict) and isinstance(value, dict):
            existing.update(value)
        elif isinstance(existing, list) and isinstance(value, list):
            for item in value:
                if item not in existing:
                    existing.append(item)
        elif (existing == "" or existing is None) and value not in ("", None):
            base_asset[key] = value

    return base_asset

def write_readme_quality_table(consolidated_assets):
    quality_keys = sorted({
        key
        for asset in consolidated_assets
        for key, value in asset.items()
        if key.startswith("url-") and isinstance(value, str) and value.strip()
    })

    header = "| " + " | ".join(["Name", *quality_keys]) + " |"
    divider = "|" + "|".join(["---"] * (len(quality_keys) + 1)) + "|"

    def asset_row(asset):
        label = asset.get("localizedName") or asset.get("accessibilityLabel") or asset.get("shotID") or asset.get("id") or "unknown"
        cells = [
            f"[&#10003;]({asset[q]})" if isinstance(asset.get(q), str) and asset.get(q).strip() else "-"
            for q in quality_keys
        ]
        return "| " + " | ".join([label.replace("|", "\\|"), *cells]) + " |"

    def sort_key(asset):
        available = sum(1 for q in quality_keys if isinstance(asset.get(q), str) and asset.get(q).strip())
        pattern = tuple(0 if isinstance(asset.get(q), str) and asset.get(q).strip() else 1 for q in quality_keys)
        label = (asset.get("localizedName") or asset.get("accessibilityLabel") or asset.get("shotID") or asset.get("id") or "").lower()
        return (-available, pattern, label)

    # Group by top-level category; 240fps-only assets are nested under subcategory headings.
    other_quality_keys = [q for q in quality_keys if q != 'url-4K-SDR-240FPS']
    groups = {}
    for asset in consolidated_assets:
        cats = asset.get('categoryNames') or []
        category = cats[0] if cats else 'Uncategorized'
        bucket = groups.setdefault(category, {'category_assets': [], 'subcategories': {}})

        only_240fps = (
            isinstance(asset.get('url-4K-SDR-240FPS'), str) and asset.get('url-4K-SDR-240FPS', '').strip()
            and not any(isinstance(asset.get(q), str) and asset.get(q, '').strip() for q in other_quality_keys)
        )

        if only_240fps:
            subcats = asset.get('subcategoryNames') or []
            subcategory = subcats[0] if subcats else 'Uncategorized'
            bucket['subcategories'].setdefault(subcategory, []).append(asset)
        else:
            bucket['category_assets'].append(asset)

    table = [
        "## Auto-generated Download Qualities",
        "",
        "Generated from the latest consolidated metadata. Do not edit manually.",
    ]

    for category_name in sorted(groups.keys(), key=lambda g: (g == 'Uncategorized', g.lower())):
        category_group = groups[category_name]
        table += ["", f"### {category_name}"]

        if category_group['category_assets']:
            table += ["", header, divider]
            for asset in sorted(category_group['category_assets'], key=sort_key):
                table.append(asset_row(asset))

        for subcategory_name in sorted(category_group['subcategories'].keys(), key=lambda g: (g == 'Uncategorized', g.lower())):
            table += ["", f"#### {subcategory_name}", "", header, divider]
            for asset in sorted(category_group['subcategories'][subcategory_name], key=sort_key):
                table.append(asset_row(asset))

    table_block = "\n".join([
        README_TABLE_START,
        *table,
        README_TABLE_END,
    ])

    if not os.path.exists(README_PATH):
        return

    with open(README_PATH, "r") as f:
        readme = f.read()

    if README_TABLE_START in readme and README_TABLE_END in readme:
        start_idx = readme.index(README_TABLE_START)
        end_idx = readme.index(README_TABLE_END) + len(README_TABLE_END)
        updated = readme[:start_idx] + table_block + readme[end_idx:]
    else:
        updated = readme.rstrip() + "\n\n" + table_block + "\n"

    with open(README_PATH, "w") as f:
        f.write(updated)

def compare_and_consolidate_metadata():
    """Load all metadata.json files, merge assets by id, and return consolidated assets."""
    all_metadata = {}
    merged_assets_by_id = {}

    print("\nComparing metadata.json from all resources:")
    for resource_key, resource_path in RESOURCE_PATHS.items():
        metadata_file = f'{resource_path}/entries.json'
        if os.path.exists(metadata_file):
            with open(metadata_file) as f:
                metadata = json.loads(f.read())
                all_metadata[resource_key] = metadata
                print(f"  {resource_key}: {len(metadata.get('assets', []))} assets")

    # Consolidate by asset id and merge metadata from matching assets.
    for resource_key, metadata in all_metadata.items():
        for asset in metadata.get('assets', []):
            asset_id = asset.get('id')
            if not asset_id:
                continue

            if asset_id not in merged_assets_by_id:
                merged_assets_by_id[asset_id] = dict(asset)
                merged_assets_by_id[asset_id]['sources'] = [resource_key]
            else:
                merged_assets_by_id[asset_id] = merge_asset_records(merged_assets_by_id[asset_id], asset)
                if resource_key not in merged_assets_by_id[asset_id]['sources']:
                    merged_assets_by_id[asset_id]['sources'].append(resource_key)

    def localize_assets(strings):
        subcategory_map = build_subcategory_map(all_metadata, strings)
        category_map = build_category_map(all_metadata, strings)
        poi_map = build_poi_map(all_metadata, strings)
        localized_assets = []

        for merged_asset in merged_assets_by_id.values():
            # Only include assets that have a shotID
            if not merged_asset.get('shotID'):
                continue

            asset = deepcopy(merged_asset)
            raw_subcats = asset.get('subcategories') or []
            asset['subcategoryNames'] = [subcategory_map.get(sid, sid) for sid in raw_subcats]

            raw_cats = asset.get('categories') or []
            normalized_cats = [CATEGORY_ID_MAPPING.get(cid, cid) for cid in raw_cats]
            asset['categories'] = normalized_cats
            asset['categoryNames'] = [category_map.get(cid, cid) for cid in normalized_cats]

            name_key = asset.get('localizedNameKey')
            asset['localizedName'] = (strings.get(name_key) if name_key else None) or asset.get('accessibilityLabel', '')

            raw_pois = asset.get('pointsOfInterest', {})
            if isinstance(raw_pois, dict):
                asset['pointsOfInterestNames'] = {
                    timestamp: poi_map.get(poi_id, poi_id)
                    for timestamp, poi_id in raw_pois.items()
                }

            localized_assets.append(asset)

        return localized_assets

    available_languages = get_available_languages()
    if not available_languages:
        fallback_language = LANGUAGE or 'en'
        available_languages = [fallback_language]

    localized_assets_by_language = {}
    print(f"  Generating localized metadata for {len(available_languages)} languages")
    for language in available_languages:
        strings = load_localizations(language)
        localized_assets_by_language[language] = localize_assets(strings)

    if LANGUAGE in localized_assets_by_language:
        default_language = LANGUAGE
    elif 'en' in localized_assets_by_language:
        default_language = 'en'
    else:
        default_language = available_languages[0]
    consolidated_assets = localized_assets_by_language[default_language]

    print(f"  Total unique assets: {len(consolidated_assets)}")

    os.makedirs('resources', exist_ok=True)
    with open('resources/consolidated-metadata.json', "w") as f:
        json.dump({'assets': consolidated_assets}, f, indent=4, sort_keys=True)
    print("  Written to resources/consolidated-metadata.json")

    metadata_version_dir = os.path.join('metadata', RELEASE_VERSION)
    os.makedirs(metadata_version_dir, exist_ok=True)

    with open(os.path.join(metadata_version_dir, 'metadata.json'), "w") as f:
        json.dump({'assets': consolidated_assets}, f, indent=4, sort_keys=True)

    for language, assets in localized_assets_by_language.items():
        language_file = os.path.join(metadata_version_dir, f'metadata-{language}.json')
        with open(language_file, "w") as f:
            json.dump({'assets': assets}, f, indent=4, sort_keys=True)

    print(f"  Written localized metadata to {metadata_version_dir}")

    write_readme_quality_table(consolidated_assets)
    print("  Updated README quality table")

    return consolidated_assets

def download_aerials():
    print("\nWARNING: Downloading using the HTTPS urls in metadata.json uses unverified HTTPS because the cert on sylvan.apple.com is self signed by Apple")
    if not os.path.exists("downloads"):
        os.mkdir("downloads")
    
    # Get consolidated metadata
    consolidated_assets = compare_and_consolidate_metadata()
    metadata = {'assets': consolidated_assets}
    
    for index, asset in enumerate(metadata['assets']):
        try:
            
            url = asset[VIDEO_QUALITY]
            filename = re.sub(r'^https?://[^/]+/(?:.*/)?', '', url)
            metadata['assets'][index][f"filename"] = f'{filename}'
            friendly_name = f"{asset['shotID']} ({asset['localizedName']})"
            if not SKIP_DOWNLOADS:
                print(f"{index+1}/{len(metadata['assets'])} Downloading {friendly_name}")
                download_aerial(url, filename, friendly_name)
            else:
                print(f"{index+1}/{len(metadata['assets'])} skipped downloading {friendly_name}")
        except KeyError as e:
            print(f"{index+1}/{len(metadata['assets'])} Quality {VIDEO_QUALITY} not found for {friendly_name}. Skipping...")

def get_resources():
    """Download and extract all resources from RESOURCE_URLS."""
    global RESOURCE_PATHS
    
    def is_within_directory(directory, target):
        abs_directory = os.path.abspath(directory)
        abs_target = os.path.abspath(target)
        prefix = os.path.commonprefix([abs_directory, abs_target])
        return prefix == abs_directory
    
    def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        for member in tar.getmembers():
            member_path = os.path.join(path, member.name)
            if not is_within_directory(path, member_path):
                raise Exception("Attempted Path Traversal in Tar File")
        tar.extractall(path, members, numeric_owner=numeric_owner)
    
    for resource_key, url in RESOURCE_URLS.items():
        print(f"\nDownloading {resource_key}...")
        tar_filename = f"{resource_key}.tar"
        resource_path = f"resources/{resource_key}"
        
        try:
            req = requests.get(url, stream=True)
            with open(tar_filename, 'wb') as dl:
                dl.write(req.content)
            
            print(f"Extracting {resource_key} to {resource_path}...")
            os.makedirs(resource_path, exist_ok=True)
            with tarfile.open(tar_filename, 'r') as tar:
                safe_extract(tar, resource_path)
            
            RESOURCE_PATHS[resource_key] = resource_path
            print(f"Successfully extracted {resource_key}")
        except Exception as e:
            print(f"Error downloading/extracting {resource_key}: {str(e)}")

def cleanup():
    """Clean up tar files and temp directories."""
    for resource_key in RESOURCE_URLS.keys():
        tar_filename = f"{resource_key}.tar"
        if os.path.isfile(tar_filename):
            os.remove(tar_filename)

    try: shutil.rmtree(f"resources")
    except FileNotFoundError as e: pass

if __name__ == "__main__":
    try:
        print("fetching resources...")
        get_resources()

        print("downloading files...")
        download_aerials()

    except Exception as e: 
        print("Something failed...", str(e))

    finally:
        print("cleaning up...")
        cleanup()
