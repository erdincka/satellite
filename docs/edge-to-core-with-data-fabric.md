# Deciding what crosses the link

### An edge-to-core pattern on HPE Data Fabric, and why one platform beats an assembled stack

A field team working off a satellite link cannot pull down everything headquarters has.
That sounds like a bandwidth problem, and most designs treat it as one — compress harder,
sync less often, buy a bigger pipe. It isn't. It's a **decision** problem. The team needs
to know what *exists* so they can choose the few things worth spending the link on.

**Satellite Demo** is a working model of that pattern, built on HPE Data Fabric. An HQ site
ingests imagery, catalogues it, and continuously broadcasts lightweight *descriptions* to
every edge site. The edge browses those descriptions and requests the handful it actually
wants. Only then does the imagery itself move. A vision model at the edge can describe
what arrived, so an operator gets an answer without opening every file.

The pattern generalises well beyond satellite imagery — disaster response, maritime
operations, remote industrial sites, defence — anywhere the link is expensive,
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

## One pipeline, four data models

Here is what makes this interesting as a platform story. That single pipeline touches
four different kinds of data, and each wants a different interface:

| In the pipeline | Data model | Interface used |
|---|---|---|
| Catalogue broadcast, asset requests | Event stream | Kafka API |
| Satellite imagery | Files | POSIX, over NFS |
| Asset metadata and AI narration | Table | Iceberg |
| The Iceberg warehouse itself | Objects | S3 |
| Volumes, streams, topics, mirrors | Administration | REST |

**None of that required a second system.** No message broker to deploy, no object store
to stand up, no separate catalog service, no file-transfer scheduler. One cluster, one
namespace, one identity — addressed through whichever standard interface each part of the
pipeline naturally speaks.

That is what multi-modal and multi-protocol mean in practice: the platform is not a
file system with an object gateway bolted on, or a message queue with a storage tier
attached. Files, objects, streams and tables are first-class, they live in the same
namespace, and they are governed by the same security model.

The practical consequence is that data does not have to move between systems to become
usable by a different consumer. An operator's imagery lands on a volume via POSIX; the
catalogue that indexes it is an Iceberg table on S3; the notification that it exists is a
stream event. Same cluster, same volumes, same credentials — no ETL between tiers whose
only purpose is to satisfy the next tool's preferred protocol.

## What you would otherwise assemble

It is worth being concrete about the alternative, because "one platform" is easy to say
and hard to evaluate. To build this pattern on general-purpose components you would need,
at minimum:

| Requirement | Assembled stack | HPE Data Fabric |
|---|---|---|
| Events between sites | Kafka plus MirrorMaker | Stream replication, multi-master |
| Bulk file transfer | rsync or a sync service, plus a scheduler | Volume mirroring, on demand or scheduled |
| Object storage | MinIO or Ceph, plus its own replication | S3 on the same volumes |
| Table storage | A warehouse and a catalog service | Iceberg on the same object store |
| File access at the edge | NFS server, separately deployed | Native |
| Identity across all of it | Per-system auth, federated somehow | One cluster identity, one ticket |
| Provisioning | Automation against several APIs | One REST API |

Every row in that middle column is a component to deploy, secure, monitor, patch, and
capacity-plan — at **every site**, including the ones with no staff and a satellite link.

And each brings its own disconnection semantics. MirrorMaker's lag behaviour is not
rsync's retry behaviour, which is not object replication's queueing behaviour. When the
link drops, you are reasoning about three or four independent recovery models at once,
and the interactions between them are where the incidents come from.

On Data Fabric, disconnection is handled the same way for everything, because it is the
platform's concern rather than each component's. In the demo, cutting the link left HQ
publishing normally while the edge stayed frozen and the backlog grew to 21 messages;
restoring it drained to zero within seconds. Imagery behaved consistently: a requested
asset simply sat staged in HQ's outbound volume until the edge chose to mirror it.
Nothing about that is simulated, and nothing about it is application code.

## What still needs designing

The platform removes the infrastructure problem. It does not remove the design problem,
and three decisions mattered more than any other.

### Model the link as a state, not an error

The instinct is to treat disconnection as an exception. It isn't — for an edge deployment
it is a normal operating mode, and often a *scheduled* one. Designing for three explicit
states (connected, scheduled, cut) produced a much better system than designing for
"connected, with error handling". The platform supports this directly: pausing and
resuming replication is a supported operation, and mirrors are on-demand by nature.

The corollary is to show the link's real state, read from the cluster, rather than
inferring it from whether your own messages happen to be flowing.

### Audit what you replicate

HQ's internal service hand-off runs on its own unreplicated stream. It would have been
one line of configuration to put it on the replicated pair — and it would have pushed
HQ's private chatter down the very link the design exists to conserve.

Because replication is so easy to enable, it is equally easy to enable by accident. On a
constrained link that is a real and recurring cost. Decide deliberately what crosses.

### Name objects by site, not by cluster

Each site owns its own volumes, streams and buckets, distinguished by name rather than by
which cluster they happen to live on. The consequence is that the system behaves
identically whether both sites share one cluster or sit on two with a trust relationship.
One is not a degraded version of the other, and moving from one to two is a configuration
change rather than a redesign.

For anyone building a real edge fleet, this is the difference between a per-site
deployment template and bespoke work at every location.

## Why it matters

The interesting claim isn't that Data Fabric can move data between sites. Plenty of
things move data. It is that a pipeline spanning streams, files, tables and objects —
across sites, over a link that comes and goes — can be built on **one platform, through
standard interfaces**, instead of assembled from components that each need their own
deployment, security domain, replication mechanism and failure model.

That leaves the application with the one job it should have: deciding what is worth
sending, and when. The fabric handles delivery, queueing, resumption and consistency
underneath.

The application decides. The fabric delivers.

---

*The demo is in this repository. See the [README](../README.md) to run it against your
own cluster.*
