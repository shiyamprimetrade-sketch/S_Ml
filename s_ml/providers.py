"""Read-only Metricool connection health. Credentials stay in environment secrets.

This does not reuse browser cookies, implement OAuth, fetch post analytics, or
claim that a local disconnect revokes a provider token.
"""
from __future__ import annotations
from email.utils import parsedate_to_datetime
import json
import math
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

ENDPOINT = 'https://app.metricool.com/api/admin/simpleProfiles'
MAX_RESPONSE = 2_000_000


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward X-Mc-Auth to a redirect destination.


def transport(url, headers):
    request = Request(url, headers=headers, method='GET')
    try:
        with build_opener(NoRedirect()).open(request, timeout=20) as response:
            body = response.read(MAX_RESPONSE + 1)
            return response.status, dict(response.headers), body
    except HTTPError as error:
        # Error response bodies are deliberately not read or logged.
        return error.code, dict(error.headers), b''
    except (URLError, TimeoutError, OSError):
        raise ConnectionError('Provider health transport unavailable') from None


def retry_after(headers, now):
    value = next((v for k, v in headers.items() if k.lower() == 'retry-after'), None)
    if value is None:
        return 600.
    try:
        delay = float(value)
        if math.isfinite(delay) and delay >= 0:
            return max(1., delay)
    except (ValueError, TypeError):
        pass
    try:
        return max(1., parsedate_to_datetime(value).timestamp() - now)
    except (ValueError, TypeError, OverflowError):
        return 600.


def connect(store, account_id, user_id, token_environment='S_ML_METRICOOL_TOKEN'):
    if not isinstance(user_id, str) or not re.fullmatch(r'\d{1,30}', user_id):
        raise ValueError('Metricool user ID must be numeric')
    if not re.fullmatch(r'S_ML_[A-Z0-9_]{1,80}', token_environment):
        raise ValueError('Use a dedicated S_ML_ environment-secret reference')
    with store.connection:
        store.connection.execute('''INSERT INTO provider_connections(account_id,user_id,token_environment)
            VALUES (?,?,?) ON CONFLICT(account_id) DO UPDATE SET user_id=excluded.user_id,
            token_environment=excluded.token_environment,enabled=1,last_check=NULL,last_status='not_checked' ''',
            (account_id, user_id, token_environment))
    return {'account_id': account_id, 'status': 'configured_reference_only',
            'authorization': 'separate Metricool API token required; browser session not transferred'}


def disconnect(store, account_id):
    with store.connection:
        store.connection.execute("UPDATE provider_connections SET enabled=0,last_status='disabled' WHERE account_id=?", (account_id,))
        store.connection.execute('UPDATE worker_jobs SET paused=1 WHERE account_id=?', (account_id,))
    return {'status': 'locally_disconnected', 'provider_token_revoked': False,
            'next_action': 'Revoke or rotate the token in Metricool settings if needed'}


def health(store, account_id, environment=None, send=transport, now=None):
    now = time.time() if now is None else now
    environment = os.environ if environment is None else environment
    db = store.connection
    row = db.execute('''SELECT c.*,a.brand_id FROM provider_connections c JOIN accounts a ON a.id=c.account_id
        WHERE c.account_id=?''', (account_id,)).fetchone()
    if row is None or not row['enabled']:
        return {'status': 'disconnected', 'live_check': False}
    if row['next_check'] > now:
        return {'status': 'check_deferred', 'live_check': False,
                'retry_after_seconds': row['next_check'] - now}
    secret = environment.get(row['token_environment'])
    if not secret:
        return {'status': 'credential_not_configured', 'live_check': False}
    if not isinstance(secret, str) or '\r' in secret or '\n' in secret:
        return {'status': 'invalid_credential_configuration', 'live_check': False}
    result = {'live_check': True, 'permissions': 'Provider token scopes are not exposed by this endpoint'}
    try:
        # Fixed HTTPS origin/path; no operator-controlled destination receives the secret.
        code, headers, body = send(ENDPOINT + '?' + urlencode({'userId': row['user_id'], 'blogId': row['brand_id']}),
                                   {'X-Mc-Auth': secret, 'Accept': 'application/json'})
        if code == 429:
            result.update(status='rate_limited', retry_after_seconds=retry_after(headers, now))
        elif code in (401, 403):
            result['status'] = 'authorization_denied'
        elif code != 200:
            result['status'] = 'provider_unavailable'
        elif len(body) > MAX_RESPONSE:
            result['status'] = 'invalid_response'
        else:
            data = json.loads(body)
            entries = data.get('data') if isinstance(data, dict) else data
            if not isinstance(entries, list):
                raise ValueError('Unsupported response shape')
            allowed = any(isinstance(item, dict) and str(item.get('blogId', item.get('id'))) == row['brand_id'] for item in entries)
            result['status'] = 'connected' if allowed else 'brand_not_authorized'
    except Exception:
        result['status'] = 'health_check_failed'
    with db:
        db.execute('UPDATE provider_connections SET last_check=?,last_status=?,next_check=? WHERE account_id=?',
                   (now, result['status'], now + result.get('retry_after_seconds', 30), account_id))
    return result
