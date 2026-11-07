"""Shared configurable Tushare transport, with separate provider credentials."""
import configparser
import datetime as dt
import queue
import threading
from functools import partial
from pathlib import Path

import pandas as pd
import requests

CONFIG_PATH = Path(__file__).resolve().parents[1] / 'tushare_config.ini'


def get_settings():
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(CONFIG_PATH, encoding='utf-8-sig'):
        raise RuntimeError(f'Missing Tushare configuration: {CONFIG_PATH}')
    provider = config.get('tushare', 'provider').strip()
    if provider not in ('relay', 'official'):
        raise ValueError('tushare provider must be relay or official')
    section = config[provider]
    url = section.get('url', '').strip()
    if not url.startswith(('https://', 'http://')):
        raise ValueError('Tushare URL must start with http:// or https://')
    return dict(provider=provider, url=url, token=section.get('token', '').strip())


ENDPOINT = get_settings()['url']
REQUEST_DEADLINE_SECONDS = 90


def request_body(session, payload, deadline=None, endpoint=None):
    """Bound the entire response, including a server that trickles HTTP chunks."""
    result = queue.Queue(maxsize=1)

    def fetch():
        response = None
        try:
            response = session.post(endpoint or ENDPOINT, json=payload, timeout=(15, 45))
            response.raise_for_status()
            result.put((True, response.json()))
        except Exception as exc:
            result.put((False, exc))
        finally:
            if response is not None:
                response.close()

    threading.Thread(target=fetch, daemon=True, name='tushare-request').start()
    try:
        ok, value = result.get(timeout=REQUEST_DEADLINE_SECONDS if deadline is None else deadline)
    except queue.Empty:
        raise TimeoutError('Tushare: entire request exceeded deadline (including response body)') from None
    if not ok:
        raise value
    return value


def get_token(settings=None):
    settings = settings or get_settings()
    if settings['token']:
        return settings['token']
    raise RuntimeError(f"Configure [{settings['provider']}] token in {CONFIG_PATH.name}")


def date_batches(params):
    """Split inclusive historical windows without dropping boundary days."""
    start, end = params.get('start_date'), params.get('end_date')
    if not (start and end):
        yield params
        return
    first = dt.datetime.strptime(start, '%Y%m%d').date()
    last = dt.datetime.strptime(end, '%Y%m%d').date()
    if first > last:
        raise ValueError('start_date must not exceed end_date')
    while first <= last:
        stop = min(first + dt.timedelta(days=365), last)
        yield dict(params, start_date=first.strftime('%Y%m%d'), end_date=stop.strftime('%Y%m%d'))
        first = stop + dt.timedelta(days=1)


class RelayClient:
    def __init__(self, session=None):
        self.session = session if session is not None else requests.Session()

    def __getattr__(self, name):
        if name.startswith('_'):
            raise AttributeError(name)
        return partial(self.query, name)

    def query(self, api_name, fields='', **params):
        settings = get_settings()
        token = get_token(settings)
        endpoint = settings['url'].replace('{api_name}', api_name)
        if isinstance(fields, (list, tuple)):
            fields = ','.join(fields)
        frames = []
        for batch in date_batches(params):
            try:
                body = request_body(self.session, {
                    'api_name': api_name, 'token': token, 'params': batch, 'fields': fields,
                }, endpoint=endpoint)
                if body.get('code') != 0:
                    raise RuntimeError(f"{api_name} [{body.get('code')}]: {body.get('msg', body.get('message', 'request failed'))}")
                data = body.get('data')
                for metadata in (body, body.get('meta') or {}, data if isinstance(data, dict) else {}):
                    if metadata.get('pending') or metadata.get('backfill_pending') or metadata.get('partial') or metadata.get('status') in ('pending', 'partial'):
                        raise RuntimeError(f'{api_name}: incomplete response (pending/partial)')
                if not isinstance(data, dict) or not isinstance(data.get('fields'), list) or not isinstance(data.get('items'), list):
                    raise RuntimeError(f'{api_name}: invalid SDK response')
                frames.append(pd.DataFrame(data['items'], columns=data['fields']))
            except Exception as exc:
                if isinstance(exc, TimeoutError):
                    # Do not reuse a Session while its abandoned request is active.
                    self.session = requests.Session()
                raise RuntimeError(str(exc).replace(token, '[REDACTED]')) from None
        return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def create_client():
    get_token()
    return RelayClient()
