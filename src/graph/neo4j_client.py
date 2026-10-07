"""Shared Neo4j helpers."""
from datetime import date
from decimal import Decimal

from neo4j import GraphDatabase, NotificationDisabledClassification, RoutingControl

from src import config

_driver = None


def driver():
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            config.NEO4J_URI, auth=(config.NEO4J_USERNAME, config.NEO4J_PASSWORD),
            # hide "feature deprecated" notices (e.g. db.index.vector.queryNodes); queries still work
            notifications_disabled_classifications=[NotificationDisabledClassification.DEPRECATION])
        _driver.verify_connectivity()
    return _driver


def run(query, **params):
    """Run a Cypher query and return the records as a list of dicts."""
    records, _, _ = driver().execute_query(query, params, database_=config.NEO4J_DATABASE)
    return [r.data() for r in records]


def run_read(query, **params):
    """Run a query in READ mode: the database itself rejects any write (used for LLM-written Cypher)."""
    records, _, _ = driver().execute_query(query, params, database_=config.NEO4J_DATABASE,
                                           routing_=RoutingControl.READ)
    return [r.data() for r in records]


def clean(value):
    """Convert values Neo4j cannot store (Decimal, empty string) into ones it can."""
    if isinstance(value, Decimal):
        return float(value)
    if value == "":
        return None
    return value


def clean_rows(rows):
    return [{k: clean(v) for k, v in r.items()} for r in rows]


def close():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


__all__ = ["driver", "run", "run_read", "clean_rows", "close", "date"]
