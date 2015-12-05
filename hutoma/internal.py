from __future__ import print_function, unicode_literals
import re
import six
import sys
from requests import Request, codes, exceptions
from requests.compat import urljoin
from .errors import (HTTPException, Forbidden, NotFound)


def _prepare_request(session, url, params, data, auth, files, method=None):
    """Return a requests Request object that can be "prepared"."""
    headers = {}
    headers.update(session.http.headers)

    if method:
        pass
    elif data or files:
        method = 'POST'
    else:
        method = 'GET'

    # Log the request if logging is enabled
    if session.config.log_requests >= 1:
        sys.stderr.write('{0}: {1}\n'.format(method, url))
    if session.config.log_requests >= 2:
        if params:
            sys.stderr.write('params: {0}\n'.format(params))
        if data:
            sys.stderr.write('data: {0}\n'.format(data))
        if auth:
            sys.stderr.write('auth: {0}\n'.format(auth))
    # Prepare request
    request = Request(method=method, url=url, headers=headers, params=params,
                      auth=auth, cookies=session.http.cookies)
    if method == 'GET':
        return request
    # Most POST requests require adding `api_type` and `uh` to the data.
    if data is True:
        data = {}

    if isinstance(data, dict):
        if not auth:
            data.setdefault('api_type', 'json')
            if session.modhash:
                data.setdefault('uh', session.modhash)
    else:
        request.headers.setdefault('Content-Type', 'application/json')

    request.data = data
    request.files = files
    return request


def _raise_redirect_exceptions(response):
    """Return the new url or None if there are no redirects.

    Raise exceptions if appropriate.

    """
    if response.status_code not in [301, 302, 307]:
        return None
    new_url = urljoin(response.url, response.headers['location'])
    return new_url


def _raise_response_exceptions(response):
    """Raise specific errors on some status codes."""
    if response.status_code == codes.forbidden:  # pylint: disable=E1101
        raise Forbidden(_raw=response)
    elif response.status_code == codes.not_found:  # pylint: disable=E1101
        raise NotFound(_raw=response)
    else:
        try:
            response.raise_for_status()  # These should all be directly mapped
        except exceptions.HTTPError as exc:
            raise HTTPException(_raw=exc.response)
