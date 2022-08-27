# Aerials Downloader for tvOS's wall papers

This Python script will download all the tvOS videos to the downloads folder.

This script also turns the `Localizable.nocache.strings` into a json file that is hosted here in the api folder. 
`entries.json` is also avaliable under `api/entries.json`

These can be pulled using the following url: 
`https://declan-fitzpatrick.github.io/aerials/api/{parsed|raw}/{lang}`

## todos
* todo list
* github action for sub strings

## running this script

Expected environment variables: 

| ENV VAR | Description | Defaults, Options |
|---------|-------------|-------------------|
SKIP_GENERATE_POI | skip the generation of points of interest files | default False
LOCALISE_BIZ_API_KEY | API key for your Loco project. Create project here [docs](https://localise.biz/api) | default None
TVOS_VERSION | the tvOS version to use for downloads | default 16
LOCAL_SERVER_URL | update entries.json with local location for these files | default none
VIDEO_QUALITY | the tvOS quality to download | default "url-1080-H264", opts "url-1080-H264", "url-1080-HDR", "url-1080-SDR", "url-4K-HDR", "url-4K-SDR" 


Run: 
```shell
python downloadAerials.py
```

## Localise.biz
"because i could throw .strings at them and download .json"
 

Nice [API docs](https://localise.biz/api/docs)

## Substrings file
It has the same contents as raw, just split into the video title and time stamps. 

raw: 
```json
{
    "VideoId_TS" : "description", 
}
```

Substrings: 
```json
{
    "VideoId": {
        "TS": "description",
    }
}
```

Can manually do it: 

curl --data-binary @Localizable.strings 'https://localise.biz/api/import/bplist?index=id&locale=en_za' -u $LOCALISE_BIZ_API_KEY: 

or use plistutil, but this generates xml

plistutil -i Localizable.nocache.strings -f xml -o results.xml