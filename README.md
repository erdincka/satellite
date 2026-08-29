# Satellite — headquarters and a disconnected edge, sharing what matters

A field team on a satellite link cannot pull down everything headquarters has. They
need to know what *exists*, and then choose the few things worth spending bandwidth on.
**Satellite** is a working model of that pattern: an HQ site ingests imagery, catalogues
it, and broadcasts lightweight *descriptions* to every edge site; the edge browses those
descriptions and requests the handful it actually wants; only then does the imagery
itself get copied. A vision model can then describe what arrived, so an operator gets an
answer without opening every file. It is built on
[HPE Ezmeral Data Fabric](https://www.hpe.com/us/en/hpe-ezmeral-data-fabric.html)
streams, object storage and Iceberg, and it is a useful reference for anyone designing
for intermittent connectivity — disaster response, maritime, remote industrial sites —
where the real design problem is deciding what crosses the link.

![HQ and edge side by side: HQ broadcasting assets, the edge requesting one and receiving it](app-image.png)

## How it works

![Regional HQ ingests, catalogues and broadcasts; the edge requests, and only then is the image copied across](core-edge.png)

At HQ, an asset moves through four stages, each handing off to the next over a stream:
**Ingested** announces that an asset exists, **Downloaded** takes custody of the bytes,
**Catalogued** appends its metadata and AI narration to an Iceberg table, and
**Broadcast** publishes the description to every edge site.

That stream is **multi-master**. HQ publishes descriptions outward, edge sites publish
requests back, and a single replicated stream carries both directions — so neither side
needs a route to the other's storage.

Bulk data moves separately, and only on request. The description is cheap and travels
continuously; the image is expensive and travels only when a field team asks for it.
That separation is the whole point.

The interface is a **stage board**: each stage is a column, and an asset is one tile that
moves left to right as it progresses. Columns are capped, so the demo can run for an
hour without the page growing without bound.

## What you need

A reachable Data Fabric cluster (7.x or 8.x) with these services, all of which a default
install provides:

| Service | Port | Used for |
|---|---|---|
| `apiserver` | 8443 | Creating volumes, streams and topics; status |
| `data-access-gateway` | 9092 | Streams, over the Kafka Wire Protocol |
| `s3server` | 9000 | Imagery and the Iceberg warehouse |

**No MapR client is required.** The app talks to the cluster entirely over the network,
so it runs on a laptop with nothing installed but Python. It never needs `/opt/mapr`, a
FUSE or NFS mount, or `maprcli`.

S3 credentials are minted on demand via `s3keys gentempkey` and refreshed as they
expire, so there are no long-lived object-store secrets to store or rotate.

## Run it

```bash
cp .env.example .env
```

Edit `.env` to point at your cluster, then start the two sites in separate terminals:

```bash
UV_ENV_FILE=.env uv run hq.py
```

```bash
UV_ENV_FILE=.env uv run edge.py
```

| Site | URL |
|---|---|
| HQ — Command & Control | <http://localhost:3000> |
| Edge — Mission Control | <http://localhost:3001> |

On first run, HQ shows a **Configure** banner. That creates the volumes, streams, topics
and buckets, and uploads the sample imagery — roughly a minute, reported step by step.
It is idempotent, so it is safe to run again if a step fails.

Then turn on **Run services** at HQ, and again at the edge. Assets begin flowing. On the
edge, click any tile under **Available** to request the full image; it appears under
**Delivered**, where you can open it and ask the vision model about it.

**Reset** in the HQ footer removes everything the demo created and leaves the rest of
the cluster untouched.

### Cluster prerequisite: topic mapping rules

The Kafka Wire Protocol gateway cannot address a stream as `/path/to/stream:topic`
directly — every topic needs a mapping rule. Without one, produces fail with
`UNKNOWN_TOPIC_OR_PARTITION` and the gateway simply does not advertise the topic.

A rule maps a topic *name* to exactly one stream, so HQ and the edge cannot both use the
same names against different streams via a global rule. Instead each side authenticates
as its own cluster user and gets a **user rule**. That is what makes the two sites
genuinely separate: HQ writes to `hq_stream`, the edge reads `edge_stream`, and stream
replication is what carries data between them.

Add to `kafka-cluster.conf` in the cluster filesystem at
`/opt/kafka-wire-protocol/default-cluster/conf/`, alongside any rules already present:

```
kafka.cluster.topic-mappings.user-rules.<hq-user>   = ["satellite_*:/apps/satellite/hq_stream"]
kafka.cluster.topic-mappings.user-rules.<edge-user> = ["satellite_*:/apps/satellite/edge/edge_stream"]
```

Then restart the Data Access Gateway. Point each side at its user in `.env`:

```bash
DF_USER=mapr              # HQ
EDGE_DF_USER=satedge      # edge
EDGE_DF_PASSWORD=...
```

The edge user needs to read the edge stream and mint its own S3 credentials. The demo's
streams are created with public produce/consume/topic permissions, so no extra stream
ACL is required.

See [Mapping Topics to Streams](https://docs.ezmeral.hpe.com/datafabric-customer-managed/72/MapR_Streams/kafka-wlps-topic-map-rules.html).

### Pointing at a vision model

Use **Vision model** in the footer; any OpenAI-compatible endpoint works, and the dialog
has a **Test** button that tells you whether the endpoint and model actually respond.
Narration is optional — the pipeline runs without it.

### Splitting HQ and edge across two clusters

Any `DF_*` setting can be prefixed with `HQ_` or `EDGE_` to override one side:

```bash
DF_HOST=df01.example.com        # HQ
EDGE_DF_HOST=df02.example.com   # edge, on its own cluster
```

With both sides on one cluster the two-site separation is simulated; with two clusters
and a trust relationship it is real.

## Configuration

Everything is set in `.env` — see [.env.example](.env.example) for the full list. The
ones worth knowing:

| Variable | Default | Purpose |
|---|---|---|
| `DF_HOST` | — | Cluster hostname |
| `DF_USER` / `DF_PASSWORD` | `mapr` | Cluster credentials |
| `FEED_INTERVAL` | `12` | Seconds between feed injections |
| `FEED_BATCH` | `2` | Assets published per interval |
| `COLUMN_LIMIT` | `8` | Tiles kept per stage column |

`FEED_INTERVAL` and `FEED_BATCH` set the pace. The defaults are slow enough to narrate
over; raise them for an unattended screen.

## A note on transport security

The Kafka Wire Protocol gateway accepts `SASL_PLAINTEXT` on a default install, which
sends the cluster password in clear over the network. That is the default here because
it is what a stock cluster offers, and it is fine on a lab network. Once the gateway is
configured for TLS, set `DF_KAFKA_SECURITY_PROTOCOL=SASL_SSL` and `DF_VERIFY_TLS=true`.

## Built with

Python 3.12 and [NiceGUI](https://nicegui.io) for both interfaces, `confluent-kafka` for
the replicated streams, `boto3` for object storage, PyIceberg for the catalogue, and the
OpenAI client for the vision model.

## Status

Working demo. Known limitations:

- Requires a topic mapping rule on the cluster, as above
- The HQ→edge asset copy is a server-side S3 copy rather than a volume mirror; mirroring
  a bucket volume works but produces mirror volumes that cannot be removed over REST,
  which would leave residue behind on every Reset
- With one cluster the two-site split is simulated

## Contributing

Issues and pull requests welcome.

## Licence

MIT — see [LICENSE](./LICENSE).
