import datetime
import logging
import pandas as pd
import pyarrow as pa
from pyiceberg.expressions import EqualTo
from pyiceberg.exceptions import TableAlreadyExistsError

logger = logging.getLogger(__name__)

logging.getLogger("pyiceberg").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.ERROR)

catalog = None


def get_catalog(warehouse_path: str):
    """Return the catalog, create if not exists"""

    global catalog

    if catalog is not None:
        return catalog

    try:
        from pyiceberg.catalog.sql import SqlCatalog

        logger.debug("Creating catalog: %s", f"sqlite:///{warehouse_path}/iceberg.db")
        catalog = SqlCatalog(
            "default",
            **{
                # creating catalog in working directory
                # "uri": f"sqlite:///{warehouse_path}/iceberg.db",
                "uri": f"sqlite:///iceberg.db",
                "py-io-impl": "pyiceberg.io.pyarrow.PyArrowFileIO",
            },
        )
        logger.debug("Got new catalog for Iceberg")

    except Exception as error:
        logger.error("Iceberg Catalog error: %s", error)

    finally:
        return catalog


def write(warehouse_path: str, namespace: str, tablename: str, records: list) -> bool:
    """
    Write rows into iceberg table

    :param tier str: namespace in catalog
    :param tablename str: table name in namespace
    :param records list: records to append to `tablename`

    :return bool: Success or failure
    """

    catalog = get_catalog(warehouse_path)

    logger.debug("Retrieving catalog: %s", catalog)

    if catalog is not None:
        # Create namespace if missing
        if (namespace,) not in catalog.list_namespaces():
            logger.debug("Creating namespace: %s", namespace)
            catalog.create_namespace(namespace)

        tbl = pa.Table.from_pandas(pd.DataFrame.from_records(records))
        logger.debug("Got table: %s", tbl)

        try:
            # Create table if missing
            t = catalog.create_table(
                f"{namespace}.{tablename}",
                schema=tbl.schema,
                location=warehouse_path,
            )
        except Exception as error:
            if not isinstance(error, TableAlreadyExistsError): logger.error(error)
            try:
                t = catalog.load_table(f"{namespace}.{tablename}")
                logger.debug("Loaded table: %s", t)
            except Exception as error:
                logger.error(error)
                return False
        # Append data to the table
        try:
            t.append(tbl)
            logger.debug(f"Appending {len(records)} records to {tablename}")
            return True
        except Exception as error:
            logger.warning(error)
            return False

    # Catalog not found
    return False


def tail(warehouse_path: str, tier: str, tablename: str):
    """Return all records from tablename"""
    catalog = get_catalog(warehouse_path)

    if catalog is not None:

        logger.info("Loading table from %s.%s", tier, tablename)

        table = catalog.load_table(f"{tier}.{tablename}")

        df = table.scan().to_pandas()

        # logger.debug(df)
        return df


def history(warehouse_path: str, tier: str, tablename: str):
    """Return list of snapshot history from tablename"""

    # warehouse_path = f"{MOUNT_PATH}/{get_cluster_name()}{DEMO['basedir']}/{tier}/{tablename}"

    catalog = get_catalog(warehouse_path)

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


def find_all(warehouse_path:str, tier: str, tablename: str):
    """
    Return pandas dataframe of all records

    :param tier str: tier volume name used as iceberg namespace

    :param tablename str: iceberg table name in the namespace

    :returns DataFrame: all records, or None
    """

    catalog = get_catalog(warehouse_path)

    if catalog is not None:
        try:
            table = catalog.load_table(f"{tier}.{tablename}")
            df = table.scan().to_pandas()
            return df

        except Exception as error:
            logger.warning("Failed to scan table %s: %s", tablename, error)
            return None


def find_by_field(warehouse_path: str, tier: str, tablename: str, field: str, value: str):
    """
    Find record(s) matching the field as arrow dataset

    :param tier str: tier volume name used as iceberg namespace

    :param tablename str: iceberg table name in the namespace

    :param field str: field in the table to match against

    :param value str: `field` value to match

    :return found `rows` or None
    """

    catalog = get_catalog(warehouse_path)

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
