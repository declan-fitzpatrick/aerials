import json
from pickle import FALSE
import requests
from requests.auth import HTTPBasicAuth
import os
import sys
import tarfile
import shutil
import concurrent.futures
import urllib3
import time
urllib3.disable_warnings()

SKIP_GENERATE_POI = False
if 'SKIP_GENERATE_POI' in os.environ: SKIP_GENERATE_POI = True

SKIP_DOWNLOADS = False
if 'SKIP_DOWNLOADS' in os.environ: SKIP_DOWNLOADS = True

if 'LOCALISE_BIZ_API_KEY' in os.environ: 
    LOCALISE_BIZ_API_KEY = os.environ['LOCALISE_BIZ_API_KEY']
else:
    print("Localise API key not in env. Skipping points of interest generation...")
    SKIP_GENERATE_POI = True

TVOS_VERSION = 16
if 'TVOS_VERSION' in os.environ: TVOS_VERSION = os.environ['TVOS_VERSION']
VIDEO_QUALITY = "url-1080-H264"
if 'VIDEO_QUALITY' in os.environ: VIDEO_QUALITY = os.environ['VIDEO_QUALITY']
if VIDEO_QUALITY == "url-1080-H264":
    APPLE_SERVER_URL = "https://sylvan.apple.com/Videos/"
else: 
    APPLE_SERVER_URL = "https://sylvan.apple.com/Aerials/2x/Videos"

BW_LIMIT = False
if 'BW_LIMIT' in os.environ: BW_LIMIT = True

RELEASE_VERSION = "0.0.2"

def upload_strings(file):
    password=""
    url = "https://localise.biz/api/import/strings?index=id&locale=en_za"
    with open(file, 'rb') as payload:
        response = requests.post(url, auth=HTTPBasicAuth(LOCALISE_BIZ_API_KEY, password), data=payload)

def download_poi_json(lang):
    password = ''
    url = "https://localise.biz/api/export/locale/en_za.json"
    response = requests.get(url, auth=HTTPBasicAuth(LOCALISE_BIZ_API_KEY, password))
    locales = response.json()
    poi = {}
    write_api_file(locales, 'raw', lang)
    for locale in locales:
        if '_' in locale:
            # key: values have the form of VIDEO_TIMESTAMP: DESCRIPTION,
            # where VIDEO can be 2, 3, or 4 pairs of underscore separated characters, which
            # can also contain newlines and unicode characters. See key: value examples below
            # GMT307_136NC_134K_8277_122: "Flying over the Gulf\u00a0of\u00a0Mexico towards the United\u00a0States"
            # L007_C007_149: "Passing over South London"
            timestamp = locale.split('_')[-1]
            key = locale.replace(f'_{timestamp}', '')
            if key not in poi: poi[key] = {}
            description = locales[locale]
            if "\n" in description: description = description.replace("\n", " ") # some have newlines in them
            poi[key][timestamp] = description
    return poi

def delete_asset(id):
    # https://localise.biz/api/docs/assets/deleteasset 
    url = f'https://localise.biz/api/assets/{id}.json'
    response = requests.delete(url, auth=HTTPBasicAuth(LOCALISE_BIZ_API_KEY, ''))
    return response

def delete_assets(): 
    password=""
    url = "https://localise.biz/api/assets"
    response = requests.get(url, auth=HTTPBasicAuth(LOCALISE_BIZ_API_KEY, password))
    assets = response.json()
    # multithread the deletes because there are almost 400 resources and api calls are slow. 
    # localise.biz is also not rate limited, which is nice -> https://localise.biz/api#rates
    # would be great if there was a mass delete assets... 
    executor = concurrent.futures.ProcessPoolExecutor(50)
    futures = [executor.submit(delete_asset, asset['id']) for asset in assets]
    concurrent.futures.wait(futures)

def write_api_file(data, folder, lang, ext=False):
    _ext=''
    if ext: _ext='.poi.json' # point of interest
    
    if folder == 'raw': 
        d = { video_ts : desc for video_ts,desc in data.items()}
    else: 
        # sort time stamps _ts
        d = { video : {int(_ts): _desc for _ts,_desc in pois.items()} for video,pois in data.items()}

    with open(f'api/{RELEASE_VERSION}/{folder}/{lang}{_ext}', "w") as dl:
        json.dump(d, dl, indent=4, sort_keys=True)

def get_poi():
    path = 'resources/TVIdleScreenStrings.bundle'
    total = 1
    count = 1
    for root, dirs, files in os.walk(path):
        for dir in dirs: 
            if 'lproj' in dir: 
                total +=1 # lazy way to do this TODO: better way.

    for root, dirs, files in os.walk(path):
        for dir in dirs: 
            if 'lproj' in dir: 
                lang = dir.split(".")[0]
                print(f"Getting poi for lang {lang} {count}/{total}")
                upload_strings(f'{path}/{lang}.lproj/Localizable.nocache.strings')
                poi = download_poi_json(lang)
                delete_assets()
                write_api_file(poi, 'parsed', lang)
                count +=1

def download_aerial(url, filename):
    chunk_size = 4096
    
    # check if file exists and it is the same size as the downloadable file.
    if os.path.exists(f"downloads/{filename}"):
        response = requests.head(url, verify=False)
        rf_size = response.headers.get("Content-Length")
        lf_size = os.stat(f"downloads/{filename}").st_size
        print(f"\t{filename} ", end="")
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

def download_aerials(): 
    print("WARNING: Downloading using the HTTPS urls in entries.json uses unverified HTTPS because the cert on sylvan.apple.com is self signed by Apple")
    if not os.path.exists("downloads"):
        os.mkdir("downloads")
    with open('resources/entries.json') as f:
        entries = json.loads(f.read())
    for index, asset in enumerate(entries['assets']):
        filename = asset[VIDEO_QUALITY].replace(APPLE_SERVER_URL, "")
        url = asset[VIDEO_QUALITY]
        entries['assets'][index][f"filename"] = f'{filename}'
        try: 
            if not SKIP_DOWNLOADS:
                print(f"{index+1}/{len(entries['assets'])} Downloading {filename}")
                download_aerial(url, filename)
            else: 
                print(f"{index+1}/{len(entries['assets'])} skipped downloading {filename}")
        except KeyError as e: 
            print(f"Died downloading {filename}", str(e))
    
    with open(f'api/{RELEASE_VERSION}/entries.json', "w") as f:
        json.dump(entries, f, indent=4, sort_keys=True)


def get_tvos_resources():
    url = f"http://sylvan.apple.com/Aerials/resources-{TVOS_VERSION}.tar"
    req = requests.get(url)

    with open('resources.tar','wb') as dl:
        dl.write(req.content)

    with tarfile.open('resources.tar', 'r') as tar:
        tar.extractall('resources')

def cleanup():
    try: shutil.rmtree('resources')
    except FileNotFoundError as e: pass
    if os.path.isfile('resources.tar'): os.remove('resources.tar')
    try: shutil.rmtree('tmp')
    except FileNotFoundError as e: pass

if __name__ == "__main__":
    try:
        print("fetching resources...")
        get_tvos_resources()

        if not SKIP_GENERATE_POI:
            print("cleaning old assets...")
            delete_assets()
            print("generating poi...")
            get_poi()

        print("downloading files...")
        download_aerials()
    except Exception as e: 
        print("Something failed...", str(e))
    finally:
        cleanup()

