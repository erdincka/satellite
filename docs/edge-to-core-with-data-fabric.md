# Deciding what crosses the link

### Building an edge-to-core demo on HPE Data Fabric, and what it taught us about designing for constrained connectivity

A field team working off a satellite link cannot pull down everything headquarters has.
That sounds like a bandwidth problem, and most designs treat it as one — compress harder,
sync less often, buy a bigger pipe. It isn't. It's a **decision** problem. The team needs
to know what *exists* so they can choose the few things worth spending the link on.

**Satellite** is a working model of that pattern, built on HPE Ezmeral Data Fabric. An HQ
site ingests imagery, catalogues it, and continuously broadcasts lightweight
*descriptions* to every edge site. The edge browses those descriptions and requests the
handful it actually wants. Only then does the imagery itself move. A vision model at the
edge can describe what arrived, so an operator gets an answer without opening every file.

The pattern generalises well beyond satellite imagery — disaster response, maritime
operations, remote industrial sites, defence, anywhere the link is expensive,
intermittent, or both.

## The architecture in one idea

**Separate the metadata plane from the data plane, and give them different transports and
different cadences.**

Descriptions are small, and they travel *continuously* over a replicated stream. Imagery
is large, and it travels *only when asked for*, by volume mirroring the edge triggers
itself. Two planes, two mechanisms, two economics.

That separation is what makes the system usable on a bad link. The catalogue stays
current for pennies. The expensive transfer happens under human control, at a moment
someone has decided is worth it.

## What the platform provides

Four Data Fabric capabilities carry the design, and it's worth being precise about which
does what.

**Multi-master stream replication** carries the catalogue outward and requests back over
a single replicated pair. HQ publishes to its own stream; the edge reads from its own.
Neither side ever attaches to the other's stream, so neither needs a route into the
other's storage — the fabric moves the messages. When the link is cut, messages queue on
the cluster and drain when it returns. In the demo, with replication paused, HQ kept
publishing while the edge stayed frozen and the backlog grew to 21 messages; restoring it
drained to zero in seconds. Nothing about that is simulated.

**Volume mirroring** carries the bulk data. HQ stages a requested asset into an outbound
volume; the edge's imagery volume is a mirror of it and is pulled on demand or on a
schedule. This is the part most worth internalising: the application never copies the
bytes. It stages them and asks the platform to move them, which means the transfer is
restartable, resumable after a disconnection, and governed by policy rather than by
application code.

**REST provisioning** creates every volume, stream, topic and mirror relationship. The
whole environment is built and torn down programmatically — no `maprcli`, no shell on a
cluster node. For an edge fleet that is the difference between a deployment you can
automate and one you cannot.

**Temporary S3 credentials** (`s3keys gentempkey`) back the Iceberg catalogue. Any user
who can authenticate mints their own short-lived key, so no long-lived object-store secret
is stored, shipped, or rotated.

## Lessons for designing on the platform

### Model the link as a first-class state, not an error

The instinct is to treat disconnection as an exception. It isn't — for an edge
deployment it's a normal operating mode, and often a *scheduled* one. Designing for
three explicit states (connected, scheduled, cut) produced a much better system than
designing for "connected, with error handling". Data Fabric supports this directly:
pausing and resuming stream replication is a supported operation, and mirrors are
on-demand by nature.

The corollary is that your interface should show the link's real state, read from the
cluster, rather than inferring it from whether your own messages are flowing.

### Let the platform move bulk data

An early version of this demo copied imagery between sites in application code. It
worked, and it demonstrated nothing — the app could read and write object storage, which
tells a customer nothing about the platform. Replacing it with volume mirroring changed
what the demo *proves*.

More practically: application-level copying gives up restartability, resumption after a
disconnection, progress reporting, and policy control. If your code is moving the bytes,
you have taken on all of that yourself.

### Choose the access path per data type

Data Fabric offers several front doors, and the right answer differs by workload:

| Data | Path | Why |
|---|---|---|
| Streams | Native client, full path addressing | Lets each site attach to the stream it owns |
| Bulk files | POSIX over NFS or FUSE | Volume mirroring operates on volumes |
| Catalogue / tables | S3 | Iceberg is at home on object storage |
| Administration | REST | Automatable, no node access needed |

One caution worth stating plainly: the **Kafka Wire Protocol gateway auto-creates its own
internal stream per topic name**. It is excellent for applications that just want a Kafka
endpoint, and it is the wrong choice when you need to attach to a *specific replicated
stream you provisioned*, because a client cannot address one. Use the native client for
replicated streams. This is a design guideline, not a defect — but discovering it late
costs a day.

### Separate site-internal traffic from the link

HQ's internal service hand-off runs on its own unreplicated stream. It would have been
one line of configuration to put it on the replicated pair, and it would have pushed HQ's
private chatter down the very link the design exists to conserve. **Audit what you
replicate.** On a constrained link, replicating something by accident is a real cost.

### Name objects by site, not by cluster

Each site owns its own volumes, streams and buckets, distinguished by name. The
consequence is that the demo behaves identically whether both sites share one cluster or
sit on two with a trust relationship — one is not a degraded version of the other, and
moving from one to two is a configuration change rather than a redesign.

For anyone building a real edge fleet, this is the difference between a per-site
deployment template and bespoke work per location.

### Match the client version to the cluster

A Data Fabric client older than the cluster cannot complete the secure CLDB handshake.
This surfaces as a connection failure, not a version error, which sends you looking in
the wrong place. Pin the client version in your image build to the cluster you target.

Plan credential distribution too: a secure cluster requires its truststore on the client,
it cannot be derived from the server certificate, and for a containerised deployment that
means deciding early how the file reaches every edge node.

### Mirror plain volumes

Volume mirroring works on object-store bucket volumes as well as plain ones, but a
mirrored bucket volume cannot be removed over REST afterwards. For anything that will be
provisioned and torn down repeatedly — demos, test environments, ephemeral edge sites —
keep bulk data on plain volumes and mirror those. **Make provisioning idempotent and
reversible from the start**; being unable to clean up is a worse problem than it sounds.

## Why it matters

The interesting claim isn't that Data Fabric can move data between sites. It's that the
*decision* about what moves, and when, can live with the people who understand the
mission — while the platform handles delivery, queueing, resumption and consistency
underneath.

That division of labour is what makes edge-to-core architectures maintainable. The
application decides. The fabric delivers.

---

*The demo is in this repository. See the [README](../README.md) to run it against your
own cluster.*
