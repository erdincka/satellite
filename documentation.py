"""
The in-app explanation of the demo.

Previously this was bound to `not ready`, so the walkthrough vanished at the exact
moment the demo became runnable, and the edge had no explanation at all. Now both sites
can open it at any time from the footer.
"""

from __future__ import annotations

import inspect

from nicegui import ui

import services
import settings

OVERVIEW = """
A field team on a satellite link cannot pull down everything headquarters has. They need
to know what **exists**, then choose the few things worth spending bandwidth on.

HQ ingests imagery, catalogues it, and broadcasts lightweight *descriptions* to every
edge site over a replicated stream. The edge browses those descriptions and requests the
handful it actually wants. Only then does the imagery itself get copied.
"""

TRANSPORT = """
The stream is **multi-master**, so one replicated stream carries the catalogue outward
and requests back. Neither side needs a route to the other's storage.

Bulk data moves separately and only on request — that separation is the whole point.
"""

STEPS = {
    "HQ": [
        ("Ingested", "A feed item is published to the pipeline stream. Nothing has moved yet — "
                     "this is just an announcement that an asset exists.",
         services.publish_to_pipeline),
        ("Downloaded", "HQ takes custody of the actual bytes and puts them in its bucket.",
         services.pipeline_to_broadcast),
        ("Catalogued", "Metadata plus the AI narration is appended to an Iceberg table. "
                       "Open Catalogue in the footer to see it.",
         None),
        ("Broadcast", "The description — not the image — goes out to every edge site.",
         None),
        ("Requested", "An edge site has asked for the full asset.", services.request_listener),
        ("Delivered", "HQ copies the image into the edge's bucket and confirms on the stream.",
         None),
    ],
    "EDGE": [
        ("Available", "A description arrived. The image itself is still at HQ. "
                      "Click a tile to request it.", services.asset_listener),
        ("Requested", "The request is on its way upstream over the same replicated stream.",
         services.request_asset),
        ("Delivered", "The image has been copied across and can be opened and asked about.",
         services.response_listener),
    ],
}


def show(side: str) -> None:
    side = side.upper()
    with ui.dialog().props("full-width") as dialog, ui.card().classes("w-full"):
        with ui.row().classes("w-full items-center justify-between"):
            ui.label("How this demo works").classes("text-lg font-medium")
            ui.button(icon="close", on_click=dialog.close).props("flat round dense")

        ui.markdown(OVERVIEW).classes("text-sm")
        ui.image("core-edge.png").classes("w-full max-h-96 object-contain")
        ui.markdown(TRANSPORT).classes("text-sm")

        ui.separator()
        ui.label(f"Stages at {'HQ' if side == 'HQ' else 'the edge'}") \
            .classes("text-base font-medium")

        for title, description, source in STEPS[side]:
            with ui.expansion(title, caption=description).classes("w-full"):
                if source is not None:
                    try:
                        ui.code(inspect.getsource(source)).classes("w-full text-xs")
                    except OSError:
                        pass
                else:
                    ui.label("See the stage header on the board for the code behind this step.") \
                        .classes("text-xs opacity-60")

        ui.separator()
        with ui.expansion("What this demo creates on the cluster").classes("w-full"):
            ui.markdown(f"""
| Object | Name |
|---|---|
| Volume | `{settings.HQ_VOLUME_NAME}` at `{settings.HQ_VOLUME}` |
| Volume | `{settings.EDGE_VOLUME_NAME}` at `{settings.EDGE_VOLUME}` |
| Stream | `{settings.HQ_STREAM}` |
| Stream replica | `{settings.EDGE_STREAM}` (multi-master) |
| Bucket | `{settings.HQ_BUCKET}` |
| Bucket | `{settings.EDGE_BUCKET}` |
| Bucket | `{settings.WAREHOUSE_BUCKET}` (Iceberg warehouse) |

**Reset** in the footer removes all of it.
""").classes("text-sm")

    dialog.on("hide", dialog.delete)
    dialog.open()
