#!/usr/bin/env python3
"""MySQL connection pool and query helpers shared by the dashboard and API."""

import mysql.connector
from mysql.connector import pooling

import settings
from logger import logger


class DatabasePoolError(Exception):
    """Raised when database pool initialization fails."""


_pool = None


def init_db():
    """Initialize the MySQL connection pool (idempotent)."""
    global _pool
    if _pool is not None:
        return
    try:
        _pool = pooling.MySQLConnectionPool(
            pool_name='osprey_pool',
            pool_size=10,
            host=settings.host,
            user=settings.user,
            password=settings.password,
            database=settings.database,
            port=settings.port,
            connection_timeout=60,
            autocommit=True,
        )
        conn = _pool.get_connection()
        conn.close()
    except mysql.connector.Error as err:
        raise DatabasePoolError(f"Failed to initialize database pool: {err}") from err


def _borrow_cursor():
    init_db()
    conn = _pool.get_connection()
    conn.time_zone = '-05:00'
    return conn, conn.cursor(dictionary=True)


def run_query(query, parameters=None, return_val=True, log_vals=True):
    if log_vals:
        logger.info("parameters: {}".format(parameters))
        logger.info("query: {}".format(query))
    conn, cur = _borrow_cursor()
    try:
        try:
            conn.ping(reconnect=True, attempts=3, delay=1)
        except mysql.connector.InterfaceError as error:
            logger.error("mysql connection error: {}".format(error))
            return False
        try:
            if parameters is None:
                cur.execute(query)
            else:
                cur.execute(query, parameters)
        except mysql.connector.Error as err:
            logger.error("mysql error: {} (err_no: {}|query: {})".format(err, err.errno, query))
            return False
        if return_val:
            data = cur.fetchall()
            logger.info("No of results: {}".format(len(data)))
            return data
        return True
    finally:
        cur.close()
        conn.close()


def query_database_insert(query, parameters, return_res=False):
    logger.info("query: {}".format(query))
    logger.info("parameters: {}".format(parameters))
    conn, cur = _borrow_cursor()
    try:
        try:
            conn.ping(reconnect=True, attempts=3, delay=1)
        except mysql.connector.InterfaceError as error:
            logger.error("mysql connection error: {}".format(error))
            return False
        try:
            cur.execute(query, parameters)
        except Exception as error:
            logger.error(error)
            return False
        logger.info("Query: {}".format(cur.statement))
        if return_res:
            return cur.lastrowid
        return True
    finally:
        cur.close()
        conn.close()


def executemany(query, params_list):
    """Run executemany and return rowcount."""
    conn, cur = _borrow_cursor()
    try:
        conn.ping(reconnect=True, attempts=3, delay=1)
        cur.executemany(query, params_list)
        return cur.rowcount
    finally:
        cur.close()
        conn.close()
