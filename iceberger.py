"""
The asset catalogue, as an Iceberg table on the Data Fabric S3 gateway.

Two changes from the previous version worth knowing about:

  - The warehouse lives in an S3 bucket rather than behind a POSIX mount, so no FUSE
    client is needed. The SQLite catalog stays local; it is demo metadata, not data.
  - `forget_catalog()` exists because Reset deletes the warehouse underneath us. The
    old code cached the catalog in a module global and never cleared it, so after a
    reset every write failed against a database file that no longer existed.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import pyarrow as pa

import dfabric
import settings

logger = logging.getLogger(__name__)
logging.getLogger("pyiceberg").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.ERROR)

CATALOG_DB = Path("iceberg.db")

_catalog = None
_lock = threading.Lock()

# Written for every asset. Declared explicitly rather than inferred from the first
# batch, so a row with a missing narration cannot change the table's schema.
SCHEMA = pa.schema([
    pa.field("key", pa.string(), nullable=False),
    pa.field("title", pa.string()),
    pa.field("description", pa.string()),
    pa.field("keywords", pa.string()),
    pa.field("preview", pa.string()),
    pa.field("status", pa.string()),
    pa.field("analysis", pa.string()),
])


def forget_catalog() -> None:
    """Drop the cached catalog so the next write rebuilds it. Used after Reset."""
    global _catalog
    with _lock:
        _catalog = None
    try:
        CATALOG_DB.unlink(missing_ok=True)
    except Exception as error:
        logger.warning("Could not remove %s: %s", CATALOG_DB, error)


def get_catalog():
    global _catalog
    with _lock:
        if _catalog is not None:
            return _catalog

        profile = dfabric.HQ
        credentials = profile.s3_credentials()
        if not credentials:
            logger.error("No S3 credentials; cannot open the Iceberg catalog")
            return None

        try:
            from pyiceberg.catalog.sql import SqlCatalog

            _catalog = SqlCatalog("satellite", **{
                "uri": f"sqlite:///{CATALOG_DB}",
                "warehouse": f"s3://{settings.WAREHOUSE_BUCKET}",
                "s3.endpoint": profile.s3_endpoint,
                "s3.access-key-id": credentials["access_key"],
                "s3.secret-access-key": credentials["secret_key"],
                "s3.path-style-access": "true",
                "s3.ssl-verify": "false",
            })
            logger.debug("Iceberg catalog opened on %s", settings.WAREHOUSE_BUCKET)
            return _catalog
        except Exception as error:
            logger.error("Could not open the Iceberg catalog: %s", error)
            return None


def _table(namespace: str, tablename: str):
    catalog = get_catalog()
    if catalog is None:
        return None
    try:
        if (namespace,) not in catalog.list_namespaces():
            catalog.create_namespace(namespace)
        identifier = f"{namespace}.{tablename}"
        try:
            return catalog.load_table(identifier)
        except Exception:
            return catalog.create_table(identifier, schema=SCHEMA)
    except Exception as error:
        logger.error("Could not open table %s.%s: %s", namespace, tablename, error)
        return None


def write_asset(asset, namespace: str = "HQ", tablename: str = "asset_table") -> bool:
    """Append one asset to the catalogue."""
    table = _table(namespace, tablename)
    if table is None:
        return False
    try:
        record = asset.to_record()
        table.append(pa.Table.from_pylist([{f.name: record.get(f.name, "") for f in SCHEMA}],
                                          schema=SCHEMA))
        return True
    except Exception as error:
        logger.error("Could not append %s to %s.%s: %s", asset.key, namespace, tablename, error)
        return False


def read_all(namespace: str = "HQ", tablename: str = "asset_table"):
    """Return the catalogue as a DataFrame, or None.

    Used by the Catalogue view — the demo writes an Iceberg table on every asset and
    previously never showed it, which left the best evidence of the pipeline invisible.
    """
    table = _table(namespace, tablename)
    if table is None:
        return None
    try:
        return table.scan().to_pandas()
    except Exception as error:
        logger.warning("Could not scan %s.%s: %s", namespace, tablename, error)
        return None


def snapshots(namespace: str = "HQ", tablename: str = "asset_table") -> list[dict]:
    """Table history — each append is a snapshot, which shows the pipeline's cadence."""
    import datetime

    table = _table(namespace, tablename)
    if table is None:
        return []
    try:
        return [
            {
                "when": datetime.datetime.fromtimestamp(h.timestamp_ms / 1000)
                .strftime("%H:%M:%S"),
                "id": h.snapshot_id,
            }
            for h in table.history()
        ]
    except Exception as error:
        logger.warning("Could not read history for %s.%s: %s", namespace, tablename, error)
        return []
