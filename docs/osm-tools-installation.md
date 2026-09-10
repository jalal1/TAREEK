# OSM Tools Installation

`osmium-tool` is required to run TAREEK. The pipeline downloads a state-level PBF file from Geofabrik and uses osmium to extract the area of interest and convert it to the format pt2matsim expects. Without osmium the network generation step will fail.

`osmconvert` is optional — it's only used as a lighter alternative when converting Overpass XML to PBF format and is not needed in the default flow.

## Install osmium-tool

**Linux (Ubuntu/Debian)**
```bash
sudo apt-get install osmium-tool
```

**macOS**
```bash
brew install osmium-tool
```

**Windows**
Download the binary from [osmcode.org/osmium-tool](https://osmcode.org/osmium-tool/), extract it, and add the folder to your `PATH`.

**Conda (all platforms)**
```bash
conda install -c conda-forge osmium-tool
```

Verify the install:
```bash
osmium --version
```

## Install osmconvert (optional, lighter alternative)

Only needed if you can't install osmium.

**Linux**
```bash
sudo apt-get install osmctools
```

**Windows**
Download from [wiki.openstreetmap.org/wiki/Osmconvert](https://wiki.openstreetmap.org/wiki/Osmconvert) and place the binary in your `PATH`.

## Cache note

When osmium is available, the pipeline downloads a state-level PBF file (~500 MB for Minnesota) on first run and caches it at:

```
data/osm_cache/minnesota-latest.osm.pbf
```

Subsequent runs extract from this cache in seconds. You can delete it to free space — it will be re-downloaded on the next run.
