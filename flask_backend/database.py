"""Flask connection lifecycle for indicator definitions and market data."""
import os
from flask import current_app, g
from market_store import initialize, is_mysql, open_connection


def get_db():
    if 'indicator_db' not in g:
        g.indicator_db = open_connection(current_app.config['DATABASE_PATH'])
    return g.indicator_db


def close_db(_error=None):
    connection = g.pop('indicator_db', None)
    if connection is not None:
        connection.close()


def init_db(app):
    if app.config['DATABASE_PATH'] != 'auto' and not is_mysql(app.config['DATABASE_PATH']):
        app.config['DATABASE_PATH'] = os.path.abspath(app.config['DATABASE_PATH'])
    initialize(app.config['DATABASE_PATH'])
    app.teardown_appcontext(close_db)

