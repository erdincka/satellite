# Satellite — headquarters and a disconnected edge, sharing what matters

A field team on a satellite link cannot pull down everything headquarters has. They
need to know what *exists*, and then choose the few things worth spending bandwidth on.
**Satellite** is a working model of that pattern: an HQ site ingests imagery, catalogues
it, and broadcasts lightweight *descriptions* to every edge site; the edge browses those
descriptions and requests the handful it actually wants; only then does the imagery
itself get copied. A vision model at the edge can then describe what arrived, so an
operator gets an answer without opening every file. It is built on
[HPE Data Fabric](https://www.hpe.com/us/en/hpe-ezmeral-data-fabric.html) streams and
volume mirroring, and it is a useful reference for anyone designing for intermittent
connectivity — disaster response, maritime, remote industrial sites — where the real
design problem is deciding what crosses the link.

The whole thing runs in **one container** on your laptop. No cluster required.

![HQ and edge side by side: HQ broadcasting assets, the edge requesting one and receiving it](app-image.png)

## How it works

![Regional HQ ingests, catalogues and broadcasts; the edge requests, and only then is the image mirrored across](core-edge.png)

At HQ, three services pass work to each other over a pipeline stream: **Download**
fetches an asset and stores it in a volume, **Categorize** records its metadata in a
table, and **Broadcast** publishes the description onto a replicated stream.

That stream is bidirectional. HQ publishes to `ASSET_BROADCAST`, which every edge site
receives; edge sites publish to `ASSET_REQUEST`, which HQ receives. So a single
replicated stream carries the catalogue outwards and requests back, and neither side
needs a connection to the other's storage.

Bulk data moves separately, and only on request: when HQ responds to a request it
copies the file into a mirrored volume, and the edge re-syncs the mirror when it
chooses to. Mirroring stays manual on purpose — the field team decides when to spend
their bandwidth.

## Run it

```bash
curl -o docker-compose.yaml https://raw.githubusercontent.com/erdincka/satellite/main/docker-compose.yaml
docker compose up -d
docker logs -f satellite
```

First start takes roughly **10 minutes on x86, or 30 on Apple Silicon** (it runs under
emulation). It is ready when the log shows both:

```
NiceGUI ready to go on http://localhost:3000, and http://172.19.0.2:3000
NiceGUI ready to go on http://localhost:3001, and http://172.19.0.2:3001
```

Then open both, side by side:

| Site | URL |
|---|---|
| HQ — Command & Control | <http://localhost:3000> |
| Edge — Mission Control | <http://localhost:3001> |

Use **Configure** in the HQ interface to create the volumes and streams, then start the
HQ services and watch assets broadcast. On the edge, start the listener, request an
asset, and re-sync the mirror when HQ has responded. **Reset** removes everything the
demo created.

To point the vision model somewhere, use the **VLM** button; any OpenAI-compatible
endpoint works.

### Running the two sites by hand

The container starts both simulators for you. To drive them yourself:

```bash
docker exec -it satellite bash -c "UV_ENV_FILE=.env ~/.local/bin/uv run hq.py"
docker exec -it satellite bash -c "UV_ENV_FILE=.env ~/.local/bin/uv run edge.py"
```

Or get a shell in the container with `docker exec -it satellite bash`.

## Built with

Python 3.12 and [NiceGUI](https://nicegui.io) for both interfaces, `mapr-streams-python`
for the replicated streams, PyIceberg for the catalogue, and the OpenAI client for the
vision model. Data Fabric itself runs inside the same container, which is what makes
the single-container demo possible.

## Status

Working demo. Two things it does not yet do:

- Connect to an external Data Fabric cluster instead of its built-in one
- Split HQ and edge across two separate containers or hosts

<details>
<summary>Reference: the volumes and streams the Configure button creates</summary>

Kept here so you can see what the app is doing on your behalf, or fix it by hand.

```bash
CLUSTER_NAME=$(head -n 1 /opt/mapr/conf/mapr-clusters.conf | awk '{print $1}')

maprcli volume create -path /apps/satellite       -name satellite
maprcli volume create -path /apps/satellite/assets -name hq_assets
maprcli volume create -path /apps/satellite/edge   -name edge
maprcli volume create -path /apps/satellite/edge_replicated -name edge_replicated
maprcli volume create -path /apps/satellite/edge/assets -name edge_assets \
  -type mirror -source edge_replicated@${CLUSTER_NAME}

maprcli stream create -path /apps/satellite/hq_stream \
  -produceperm p -consumeperm p -topicperm p
maprcli stream replica autosetup -path /apps/satellite/hq_stream \
  -replica /apps/satellite/edge/edge_stream -multimaster true

mount -t nfs -o nolock,hard localhost:/mapr /mapr
```

The **Reset** button reverses all of it.

</details>

## Contributing

Issues and pull requests welcome.

## Licence

MIT — see [LICENSE](./LICENSE).
