# Aerials Downloader for tvOS's wall papers

This Python script will download all the tvOS videos to the downloads folder.

This script also turns the `Localizable.nocache.strings` into a json file that is hosted here in the api folder. 

`entries.json` is also avaliable under `api/{release}/entries.json`

These can be pulled using the following url: 
`https://declan-fitzpatrick.github.io/aerials/api/{release}/{parsed|raw}/{lang}`

Finally, a Docker container will serve the files (with CORS) on localhost:5050. [Reverse proxy setup](https://hub.docker.com/r/flashspys/nginx-static/) is left as an exercise to the reader.

## running this script

Expected environment variables and their defaults: 

| ENV VAR | Description | Defaults, Options |
|---------|-------------|-------------------|
SKIP_GENERATE_POI | skip the generation of points of interest files | default False
LOCALISE_BIZ_API_KEY | API key for your Loco project. Create project here [docs](https://localise.biz/api) | default None
TVOS_VERSION | the tvOS version to use for downloads | default 16
VIDEO_QUALITY | the tvOS quality to download | default "url-1080-H264", opts "url-1080-H264", "url-1080-HDR", "url-1080-SDR", "url-4K-HDR", "url-4K-SDR" 
BW_LIMIT | Limit the video download to ~1MB/s | Default false


Run: 
```shell
ENV_VAR=<value> python downloadAerials.py
```

## Localise.biz
"because i could throw .strings at them and download .json"
 

Nice [API docs](https://localise.biz/api/docs)

## Points of interest file
It has the same contents as raw, just split into the video title and time stamps. 

raw: 
```json
{
    "VideoId_TS" : "description", 
}
```

parsed: 
```json
{
    "VideoId": {
        "TS": "description",
    }
}
```

## Manual localise strings

Can [upload your own file to loco without an account](https://localise.biz/free/converter/ios-to-android)

or locally: plistutil on Linux, but this only generates xml

```shell
plistutil -i Localizable.nocache.strings -f xml -o results.xml
```

Mac uses:
```shell
plutil -convert xml1 Localizable.nocache.strings
```

## Running the docker container
The container is hosted in [DockerHub](https://hub.docker.com/repository/docker/declanfitzpatrick/aerials): 
1. First run the downloader script above to grab the files
2. run the docker compose file

```shell
docker-compose up
```
