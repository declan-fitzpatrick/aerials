# CHANGELOG

## v0.1.0
* add `macOS26` release with the latest metadata and localized data. 
* Refactor output structure to separate consolidated metadata and localized data into `metadata/`.
* Update readme to auto-generate download links. 

## v0.0.2

* pull in feature
* Remove LOCAL_SERVER_URL for better usage #2
* add docker-compose.yml for running this as a local server.
* add index.html and style.css for something of a home page. Probably should tidy it up.

## v0.0.1

* Initial release of the python aerials downloader
    * Includes bandwidth limiting
    * Includes resume downloads
    * Generates points of interest for all Apple langs
    * `poi` and `entries.json` hosted by [gh-pages](https://declan-fitzpatrick.github.io/aerials/) at `api/{release}/{raw|parsed}/lang` and `api/entries.json`