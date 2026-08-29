# Satellite — headquarters and a disconnected edge, sharing what matters

A field team on a satellite link cannot pull down everything headquarters has. They
need to know what *exists*, and then choose the few things worth spending bandwidth on.
**Satellite** is a working model of that pattern: an HQ site ingests imagery, catalogues
it, and broadcasts lightweight *descriptions* to every edge site; the edge browses those
descriptions and requests the handful it actually wants; only then does the imagery
itself get copied. A vision model can then describe what arrived, so an operator gets an
answer without opening every file.

It is built on [HPE Ezmeral Data Fabric](https://www.hpe.com/us/en/hpe-ezmeral-data-fabric.html)
stream replication, object storage and Iceberg, and it is a useful reference for anyone
designing for intermittent connectivity — disaster response, maritime, remote industrial
sites — where the real design problem is deciding what crosses the link.

![One page: headquarters on the left, the edge on the right, and the live Data Fabric replication link between them](app-image.png)

## How it works

![HQ ingests, stores, catalogues and broadcasts; descriptions replicate to the edge continuously, requests travel back, and imagery crosses only on request](core-edge.png)

Each site owns its objects and attaches only to its own stream:

| | HQ | Edge |
|---|---|---|
| Volume | `satellite-hq` at `/apps/satellite-hq` | `satellite-edge` at `/apps/satellite-edge` |
| Stream | `/apps/satellite-hq/hq-stream` | `/apps/satellite-edge/edge-stream` |
| Internal stream | `/apps/satellite-hq/hq-pipeline` | — |
| Assets bucket | `hq-assets` | `edge-assets` |
| Iceberg warehouse | `hq-warehouse` | `edge-warehouse` |

**Neither side ever reads or writes the other's stream.** The two streams are paired
multi-master, so HQ publishes the catalogue onto its own stream and the edge reads it
from its own; edge requests travel back the same way. Data crosses between the sites
only through Data Fabric replication — which is the mechanism the demo exists to show.

At HQ an asset moves through four stages, each handing off over HQ's internal pipeline
stream: **Ingested** announces that an asset exists, **Stored** uploads the actual bytes
to HQ's bucket, **Catalogued** appends metadata and the AI narration to an Iceberg
table, and **Broadcast** publishes the description. HQ's internal chatter stays on a
separate, unreplicated stream — it is HQ's business, and pushing it down the link would
undercut the point.

Bulk data moves separately and only on request. The description is cheap and travels
continuously; the image is expensive and travels only when a field team asks for it.

## The interface

One page, both sites side by side, with the **Data Fabric link** between them — that
centre column is the point of the demo: descriptions flowing outward continuously,
requests coming back, and imagery crossing only when a field team asks for it, with the
replication state read from the cluster rather than inferred.

Each site shows its pipeline as a **stage board**: an asset is one tile that moves left
to right between stages, columns are capped, and throughput and end-to-end latency are
charted underneath.

The demo runs on the **server**, not in the browser. Close the tab and the pipeline
keeps going; reopen it and the interface resynchronises. State is pushed over a
WebSocket, so nothing polls.

## What you need

A reachable Data Fabric cluster (7.x or 8.x) with:

| Service | Port | Used for |
|---|---|---|
| `apiserver` | 8443 | Creating volumes, streams, topics; status |
| `cldb` | 7222 | Streams, via the native client |
| `s3server` | 9000 | Imagery and the Iceberg warehouse |

S3 credentials are minted per-user with `s3keys gentempkey` and refreshed as they
expire, so there are no long-lived object-store secrets to store or rotate.

The demo ships as a container built on `maprtech/pacc`, because streams need the Data
Fabric client libraries. It does **not** need a FUSE/NFS mount and never calls
`maprcli` — provisioning is REST and assets are S3.

**HQ and the edge may point at the same cluster.** They stay separate by volume, stream
and bucket, so the demo behaves identically whether you have one cluster or two.


## Run it

```bash
cp .env.example .env
```

Set `DF_HOST` and credentials in `.env`, then:

```bash
docker compose up --build -d
```

Then open <http://localhost:8080>. Set `PORT` in `.env` if 8080 is taken.

Each site's cluster can also be set from the interface — click the host next to a site's
name — so you can repoint the demo at a customer's cluster without restarting anything.

On first run each site offers **Prepare**. Do the **edge first** (its volume and
buckets), then **HQ** (its volume and buckets, the streams and topics, and the
replication pair). Every step is reported and it is safe to re-run.

Then press **Run** on each site. Assets begin flowing. On the edge, click **Request
image** on any available tile; it arrives under Delivered, where you can open it and ask
the vision model about it. **Step** advances a single cycle if you would rather drive it
by hand, and the **Pace** slider changes the rate mid-sentence.

**Reset edge** / **Reset HQ** remove everything that site owns and leave the rest of the
cluster untouched.

### Pointing at a vision model

Use **Model** in the footer; any OpenAI-compatible endpoint works, and the dialog has a
**Test** button that says whether the endpoint and model actually respond. Narration is
optional — the pipeline runs without it.

### Splitting HQ and edge across two clusters

Point each site at its own cluster — a hostname where CLDB and the apiserver are
reachable:

```bash
HQ_HOST=df01.example.com
EDGE_HOST=df02.example.com
```

Because neither side ever touches the other's stream, nothing about the design changes —
the replication pair simply spans two clusters instead of living on one. That needs a
trust relationship between them.

## Configuration

See [.env.example](.env.example) for the full list. The ones worth knowing:

| Variable | Default | Purpose |
|---|---|---|
| `HQ_HOST` / `EDGE_HOST` | — | Each site's cluster; may be the same host |
| `HQ_USER` / `HQ_PASSWORD` | `mapr` | HQ credentials |
| `EDGE_USER` / `EDGE_PASSWORD` | `mapr` | Edge credentials |
| `PORT` | `8080` | Port the interface is served on |
| `FEED_INTERVAL` | `12` | Seconds between feed injections |
| `FEED_BATCH` | `2` | Assets published per interval |
| `COLUMN_LIMIT` | `8` | Tiles kept per stage column |

`FEED_INTERVAL` and `FEED_BATCH` set the pace. The defaults are slow enough to narrate
over; raise them for an unattended screen. Volume, stream and bucket names are
overridable too, in case the defaults collide on a shared cluster.

## Built with

A FastAPI server on Python 3.12 with a React, Vite and Tailwind front end, talking over
a WebSocket. `mapr-streams-python` for the replicated streams, `boto3` for object
storage, PyIceberg for the catalogue, and the OpenAI client for the vision model. The
image is built on `maprtech/pacc`.

## Status

Working demo, verified end to end against Data Fabric 8.1: ingest → store → catalogue →
broadcast → replicate → request → deliver.

Known limitations:

- The container is `linux/amd64` only, because the Data Fabric client is.
- Building the image yourself needs credentials for HPE's package repository, or a
  reachable mirror via the `MAPR_REPO` build argument. The `maprtech/pacc` base already
  ships a working client, so most builds need neither.
- One container configures one Data Fabric client, so a two-cluster split relies on the
  trust relationship between them.
- With one cluster the two-site split is real in every respect except geography.

## Contributing

Issues and pull requests welcome.

## Licence

MIT — see [LICENSE](./LICENSE).
