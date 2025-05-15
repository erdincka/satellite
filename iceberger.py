import datetime
import logging
import pandas as pd
import pyarrow as pa
from pyiceberg.expressions import EqualTo

import settings

logger = logging.getLogger(__name__)

catalog = None


def get_catalog():
    """Return the catalog, create if not exists"""

    global catalog

    if catalog is not None:
        return catalog

    try:
        from pyiceberg.catalog.sql import SqlCatalog

        catalog = SqlCatalog(
            "default",
            **{
                # creating catalog in working directory
                "uri": f"sqlite:///iceberg.db",
                "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
            },
        )
        logger.info("Got new catalog for Iceberg")

    except Exception as error:
        logger.error("Iceberg Catalog error: %s", error)

    finally:
        return catalog


def write(tier: str, tablename: str, records: list) -> bool:
    """
    Write rows into iceberg table

    :param tier str: namespace in catalog
    :param tablename str: table name in namespace
    :param records list: records to append to `tablename`

    :return bool: Success or failure
    """

    warehouse_path = f"{tier}/{tablename}"

    catalog = get_catalog()

    if catalog is not None:
        # create namespace if missing
        if (tier,) not in catalog.list_namespaces():
            catalog.create_namespace(tier)

        # logger.info(catalog.list_namespaces())

        table = None

        # tbl = pa.Table.from_pylist(records)
        tbl = pa.Table.from_pandas(pd.DataFrame.from_records(records))

        # Create table if missing
        try:
            logger.info("Creating table %s.%s", tier, tablename)
            table = catalog.create_table(
                f"{tier}.{tablename}",
                schema=tbl.schema,
                location=warehouse_path,
            )

        except Exception as error:
            logger.error(error)
            # if error is for table already exists
            logger.info("Table exists, appending to: " + tablename)
            table = catalog.load_table(f"{tier}.{tablename}")

        existing = table.scan().to_pandas()

        incoming = pd.DataFrame.from_dict(records) # pyright: ignore[reportArgumentType]

        if existing.empty:
            merged = incoming
        else:
            merged = pd.concat([existing, incoming]).drop_duplicates(keep="last")

        logger.info(f"Appending {incoming.shape[0]} records to {tablename}")
        try:
            table.append(pa.Table.from_pandas(merged, preserve_index=False))

        except Exception as error:
            logger.warning(error)
            return False

        return True

    # catalog not found
    return False


def tail(tier: str, tablename: str):
    """Return all records from tablename"""

    catalog = get_catalog()

    if catalog is not None:

        logger.info("Loading table from %s.%s", tier, tablename)

        table = catalog.load_table(f"{tier}.{tablename}")

        df = table.scan().to_pandas()

        # logger.debug(df)

        return df


def history(tier: str, tablename: str):
    """Return list of snapshot history from tablename"""

    # warehouse_path = f"{MOUNT_PATH}/{get_cluster_name()}{DEMO['basedir']}/{tier}/{tablename}"

    catalog = get_catalog()

    if catalog is not None:

        logger.info("Loading table: %s.%s", tier, tablename)

        table = catalog.load_table(f"{tier}.{tablename}")

        logger.info("Got table: %s", table)

        return [
            {
                "date": datetime.datetime.fromtimestamp(
                    int(h.timestamp_ms) / 1000
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "id": h.snapshot_id,
            }
            for h in table.history()
        ]


def find_all(tier: str, tablename: str):
    """
    Return pandas dataframe of all records

    :param tier str: tier volume name used as iceberg namespace

    :param tablename str: iceberg table name in the namespace

    :returns DataFrame: all records, or None
    """

    catalog = get_catalog()

    if catalog is not None:
        try:
            table = catalog.load_table(f"{tier}.{tablename}")
            df = table.scan().to_pandas()
            return df

        except Exception as error:
            logger.warning("Failed to scan table %s: %s", tablename, error)
            return None


def find_by_field(tier: str, tablename: str, field: str, value: str):
    """
    Find record(s) matching the field as arrow dataset

    :param tier str: tier volume name used as iceberg namespace

    :param tablename str: iceberg table name in the namespace

    :param field str: field in the table to match against

    :param value str: `field` value to match

    :return found `rows` or None
    """

    catalog = get_catalog()

    if catalog is not None:
        try:
            table = catalog.load_table(
                f"{tier}.{tablename}",
            )

            logger.info("table path: %s.%s", tier, tablename)

            filtered = table.scan(
                row_filter=EqualTo(field, value),
                selected_fields=("_id",),
                # limit=1, # assuming no duplicates
            ).to_arrow()

            return filtered

        except:
            logger.warning("Cannot scan table: " + tablename)

        return None
