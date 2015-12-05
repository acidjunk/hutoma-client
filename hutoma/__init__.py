from __future__ import print_function, unicode_literals

import json
import os
import platform
import re
import six
import sys
from hutoma import errors
from hutoma.handlers import DefaultHandler
from hutoma.helpers import normalize_url
from hutoma.internal import (_prepare_request, _raise_redirect_exceptions, _raise_response_exceptions)
from hutoma.settings import CONFIG
from requests import Session
from requests.compat import urljoin
from requests.utils import to_native_string
from requests import Request
# pylint: disable=F0401
from six.moves import html_entities, http_cookiejar
from six.moves.urllib.parse import parse_qs, urlparse, urlunparse
# pylint: enable=F0401
from warnings import warn_explicit


__version__ = '0.1.0'

MAX_FILE_SIZE = 512000

# Compatibility
if six.PY3:
    CHR = chr
else:
    CHR = unichr  # NOQA


class Config(object):  # pylint: disable=R0903
    """A class containing the configuration for a Hutoma site."""

    API_PATHS = {'ai_list':     'api/v1/ai/',
                 'ai':          'api/v1/ai/{aiid}',
                 'folder':      'api/v1/ai/{aiid}/{folder}',
                 'chat':        'api/v1/{aiid}/chat',
                 'speak':       'api/v1/{aiid}/speak',
                 'training':    'api/v1/{aiid}/training',
                 }

    @staticmethod
    def ua_string(hutoma_info):
        """Return the user-agent string.

        The user-agent string contains version and platform version info.

        """
        if os.environ.get('SERVER_SOFTWARE') is not None:
            # Google App Engine information
            # https://developers.google.com/appengine/docs/python/
            info = os.environ.get('SERVER_SOFTWARE')
        else:
            # Standard platform information
            info = platform.platform(True).encode('ascii', 'ignore')

        return '{0} Hutoma/{1} Python/{2} {3}'.format(
            hutoma_info, __version__, sys.version.split()[0], info)

    def __init__(self, site_name, **kwargs):
        """Initialize configuration."""
        def config_boolean(item):
            return item and item.lower() in ('1', 'yes', 'true', 'on')

        obj = dict(CONFIG.items(site_name))
        # Overwrite configuration file settings with those given during
        # instantiation of the Hutoma instance.
        for key, value in kwargs.items():
            obj[key] = value

        self.api_domain = obj['api_domain']
        self.api_url = 'https://' + self.api_domain
        self.api_request_delay = float(obj['api_request_delay'])
        self.by_kind = {'ai_list':  objects.AIList,
                        'ai':       objects.AI,
                        'folder':   objects.Folder,
                        'chat':     objects.Chat,
                        'training': objects.Training}
        self.by_object = dict((value, key) for (key, value) in six.iteritems(self.by_kind))
        self.cache_timeout = float(obj['cache_timeout'])
        self.log_requests = int(obj['log_requests'])
        self.user_key = (obj.get('user_key') or os.getenv('user_key') or None)
        self.http_proxy = (obj.get('http_proxy') or os.getenv('http_proxy') or None)
        self.https_proxy = (obj.get('https_proxy') or os.getenv('https_proxy') or None)
        # We use `get(...) or None` because `get` may return an empty string

        self.validate_certs = config_boolean(obj.get('validate_certs'))
        self.store_json_result = config_boolean(obj.get('store_json_result'))
        self.timeout = float(obj['timeout'])

    def __getitem__(self, key):
        url = urljoin(self.api_url, self.API_PATHS[key])
        return url


class BaseHutoma(object):
    """A base class that allows access to Hutoma'ss API.

    You should **not** directly instantiate instances of this class. Use
    :class:`.Hutoma` instead.

    """

    RETRY_CODES = [502, 503, 504]
    update_checked = False

    def __init__(self, user_agent, site_name=None, handler=None, **kwargs):
        """Initialize our connection with a hutoma server.

        The user_agent is how your application identifies itself. Read the
        official API guidelines for user_agents
        https://github.com/reddit/reddit/wiki/API. Applications using default
        user_agents such as "Python/urllib" are drastically limited.

        site_name allows you to specify which Hutoma site you want to connect to.
        This must match with an entry in hutoma.ini. If site_name is None, then the site
        name will be looked for in the environment variable HUTOMA_SITE. If it
        is not found there, the default site name hutoma will be used.

        All additional parameters specified via kwargs will be used to
        initialize the Config object.
        """
        if not user_agent or not isinstance(user_agent, six.string_types):
            raise TypeError('user_agent must be a non-empty string.')
        if 'bot' in user_agent.lower():
            warn_explicit(
                'The keyword `bot` in your user_agent may be problematic.', UserWarning, '', 0)

        self.config = Config(site_name or os.getenv('HUTOMA_SITE') or 'hutoma', **kwargs)
        self.handler = handler or DefaultHandler()
        self.http = Session()
        self.http.headers['User-Agent'] = self.config.ua_string(user_agent)
        self.http.headers['user_key'] = self.config.user_key
        self.http.validate_certs = self.config.validate_certs

        # This `Session` object is only used to store request information that
        # is used to make prepared requests. It _should_ never be used to make
        # a direct request, thus we raise an exception when it is used.

        def _req_error(*_, **__):
            raise errors.ClientException('Do not make direct requests.')
        self.http.request = _req_error

        if self.config.http_proxy or self.config.https_proxy:
            self.http.proxies = {}
            if self.config.http_proxy:
                self.http.proxies['http'] = self.config.http_proxy
            if self.config.https_proxy:
                self.http.proxies['https'] = self.config.https_proxy
        self.modhash = None

    def _request(self, url, params=None, data=None, files=None, auth=None,
                 timeout=None, raw_response=False, retry_on_error=True,
                 method=None):
        """Given a page url and a dict of params, open and return the page.

        :param url: the url to grab content from.
        :param params: a dictionary containing the GET data to put in the url
        :param data: a dictionary containing the extra data to submit
        :param files: a dictionary specifying the files to upload
        :param auth: Add the HTTP authentication headers (see requests)
        :param timeout: Specifies the maximum time that the actual HTTP request
            can take.
        :param raw_response: return the response object rather than the
            response body
        :param retry_on_error: if True retry the request, if it fails, for up
            to 3 attempts
        :returns: either the response body or the response object

        """
        def build_key_items(url, params, data, auth, files, method):
            request = _prepare_request(self, url, params, data, auth, files, method)

            # Prepare extra arguments
            key_items = []
            for key_value in (params, data, request.cookies, auth):
                if isinstance(key_value, dict):
                    key_items.append(tuple(key_value.items()))
                elif isinstance(key_value, http_cookiejar.CookieJar):
                    key_items.append(tuple(key_value.get_dict().items()))
                else:
                    key_items.append(key_value)
            kwargs = {'_rate_domain': self.config.api_domain,
                      '_rate_delay': int(self.config.api_request_delay),
                      '_cache_ignore': bool(files) or raw_response,
                      '_cache_timeout': int(self.config.cache_timeout)}

            return (request, key_items, kwargs)

        def decode(match):
            return CHR(html_entities.name2codepoint[match.group(1)])

        def handle_redirect():
            response = None
            url = request.url
            while url:  # Manually handle 302 redirects
                request.url = url
                kwargs['_cache_key'] = (normalize_url(request.url),
                                        tuple(key_items))
                response = self.handler.request(
                    request=request.prepare(),
                    proxies=self.http.proxies,
                    timeout=timeout,
                    verify=self.http.validate_certs, **kwargs)

                if self.config.log_requests >= 2:
                    msg = 'status: {0}\n'.format(response.status_code)
                    sys.stderr.write(msg)
                url = _raise_redirect_exceptions(response)
                assert url != request.url
            return response

        timeout = self.config.timeout if timeout is None else timeout
        request, key_items, kwargs = build_key_items(url, params, data,
                                                     auth, files, method)

        remaining_attempts = 3 if retry_on_error else 1
        while True:
            try:
                response = handle_redirect()
                _raise_response_exceptions(response)
                self.http.cookies.update(response.cookies)
                if raw_response:
                    return response
                else:
                    return re.sub('&([^;]+);', decode, response.text)

            except errors.HTTPException as error:
                remaining_attempts -= 1
                # pylint: disable=W0212
                if error._raw.status_code not in self.RETRY_CODES or \
                        remaining_attempts == 0:
                    raise

    def _json_hutoma_objecter(self, json_data):
        """Return an appropriate HutomaObject from json_data when possible."""
        try:
            object_class = self.config.by_kind[json_data['kind']]
        except KeyError:
            if 'json' in json_data:
                if len(json_data) != 1:
                    msg = 'Unknown object type: {0}'.format(json_data)
                    warn_explicit(msg, UserWarning, '', 0)
                return json_data['json']
        else:
            return object_class.from_api_response(self, json_data['data'])
        return json_data

    def evict(self, urls):
        """Evict url(s) from the cache.

        :param urls: An iterable containing normalized urls.
        :returns: The number of items removed from the cache.

        """
        if isinstance(urls, six.string_types):
            urls = (urls,)
        return self.handler.evict(urls)

    # @decorators.oauth_generator
    def get_content(self, url, params=None):
        """Return hutoma content from a URL."""
        return self.request_json(url, params=params)

    # @decorators.raise_api_exceptions
    def request(self, url, params=None, data=None, retry_on_error=False,
                method=None):
        """Make a HTTP request and return the response.

        :param url: the url to grab content from.
        :param params: a dictionary containing the GET data to put in the url
        :param data: a dictionary containing the extra data to submit
        :param retry_on_error: if True retry the request, if it fails, for up
            to 3 attempts
        :param method: The HTTP method to use in the request.
        :returns: The HTTP response.
        """
        return self._request(url, params, data, raw_response=True,
                             retry_on_error=retry_on_error, method=method)

    # @decorators.raise_api_exceptions
    def request_json(self, url, params=None, data=None, as_objects=True,
                     retry_on_error=True, method=None):
        """Get the JSON processed from a page.

        :param url: the url to grab content from.
        :param params: a dictionary containing the GET data to put in the url
        :param data: a dictionary containing the extra data to submit
        :param as_objects: if True return reddit objects else raw json dict.
        :param retry_on_error: if True retry the request, if it fails, for up
            to 3 attempts
        :returns: JSON processed page

        """
        response = self._request(url, params, data, method=method, retry_on_error=retry_on_error)
        hook = self._json_hutoma_objecter if as_objects else None
        # Request url just needs to be available for the objecter to use
        self._request_url = url  # pylint: disable=W0201

        if response == '':
            # Some of the v1 urls don't return anything, even when they're
            # successful.
            return response

        data = json.loads(response, object_hook=hook)
        delattr(self, '_request_url')
        # Update the modhash
        if isinstance(data, dict) and 'data' in data and 'modhash' in data['data']:
            self.modhash = data['data']['modhash']
        return data


class HutomaUserKey(BaseHutoma):
    """This mixin provides bindings for basic functions of Hutoma's API.

    You should **not** directly instantiate instances of this class. Use
    :class:`.Hutoma` instead.

    """
    def __init__(self, *args, **kwargs):
        """Initialize an UnauthenticatedReddit instance."""
        super(HutomaUserKey, self).__init__(*args, **kwargs)
        # initialize to 1 instead of 0, because 0 does not reliably make
        # new requests.
        self._unique_count = 1
        self.user_key = '16066e791af0db0855c3152fc83d649a'

    def get_ai_list(self, *args, **kwargs):
        key = 'ai_list'
        return self.get_content(self.config[key])

    def get_ai(self, aiid):
        key = 'ai'
        url = self.config[key].format(aiid=aiid)
        return self.get_content(url)

from hutoma import objects  # NOQA