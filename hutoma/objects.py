from __future__ import print_function, unicode_literals
import six
from six.moves.urllib.parse import (  # pylint: disable=F0401
    parse_qs, urlparse, urlunparse)
from heapq import heappop, heappush
from json import dumps
from requests.compat import urljoin
from warnings import warn_explicit

from .errors import ClientException

HUTOMA_KEYS = ('AIID')

class HutomaObject(object):

    @classmethod
    def from_api_response(cls, hutoma_session, json_dict):
        """Return an instance of the appropriate class from the json_dict."""
        return cls(hutoma_session, json_dict=json_dict)

    def __init__(self, hutoma_session, json_dict=None, fetch=True,
                 info_url=None, underscore_names=None, uniq=None):
        """Create a new object from the dict of attributes returned by the API.

        The fetch parameter specifies whether to retrieve the object's
        information from the API (only matters when it isn't provided using
        json_dict).

        """
        self._info_url = info_url or hutoma_session.config['info']
        self.hutoma_session = hutoma_session
        self._underscore_names = underscore_names
        self._uniq = uniq
        self._has_fetched = self._populate(json_dict, fetch)

    def __eq__(self, other):
        """Return whether the other instance equals the current."""
        return (isinstance(other, HutomaObject) and
                self.fullname == other.fullname)

    def __getattr__(self, attr):
        """Return the value of the `attr` attribute."""
        if attr != '__setstate__' and not self._has_fetched:
            self._has_fetched = self._populate(None, True)
            return getattr(self, attr)
        msg = '\'{0}\' has no attribute \'{1}\''.format(type(self), attr)
        raise AttributeError(msg)

    def __getstate__(self):
        """Needed for `pickle`.

        Without this, pickle protocol version 0 will make HTTP requests
        upon serialization, hence slowing it down significantly.
        """
        return self.__dict__

    def __ne__(self, other):
        """Return whether the other instance differs from the current."""
        return not self == other

    def __reduce_ex__(self, _):
        """Needed for `pickle`.

        Without this, `pickle` protocol version 2 will make HTTP requests
        upon serialization, hence slowing it down significantly.
        """
        return self.__reduce__()

    def __setattr__(self, name, value):
        """Set the `name` attribute to `value."""
        if value and name in HUTOMA_KEYS:
            if isinstance(value, bool):
                pass
            elif not value or value == '[deleted]':
                value = None
            else:
                value = AI(self.session, value, fetch=False)
        object.__setattr__(self, name, value)

    def __str__(self):
        """Return a string representation of the HutomaObject."""
        retval = self.__unicode__()
        if not six.PY3:
            retval = retval.encode('utf-8')
        return retval
    
    def _get_json_dict(self):
        # (disabled for entire function) pylint: disable=W0212
        scope = self.session.has_scope

        params = {'uniq': self._uniq} if self._uniq else {}
        response = self.session.request_json(
            self._info_url, params=params, as_objects=False)

        return response['data']

    def _populate(self, json_dict, fetch):
        if json_dict is None:
            json_dict = self._get_json_dict() if fetch else {}

        if self.session.config.store_json_result is True:
            self.json_dict = json_dict
        else:
            self.json_dict = None

        # TODO: Remove this hack
        if isinstance(json_dict, list):
            json_dict = {'_tmp': json_dict}

        for name, value in six.iteritems(json_dict):
            if self._underscore_names and name in self._underscore_names:
                name = '_' + name
            setattr(self, name, value)

        self._post_populate(fetch)
        return bool(json_dict) or fetch

    def _post_populate(self, fetch):
        """Called after populating the attributes of the instance."""

    @property
    def fullname(self):
        """Return the object's fullname.

        A fullname is an object's kind mapping like `t3` followed by an
        underscore and the object's base36 id, e.g., `t1_c5s96e0`.

        """
        by_object = self.session.config.by_object
        return '{0}_{1}'.format(by_object[self.__class__], self.id)


class Editable(HutomaObject):
    """Interface for Hutoma objects that can be edited and deleted."""

    def delete(self):
        """Delete this object.

        :returns: The json response from the server.

        """
        url = self.session.config['del']
        data = {'id': self.fullname}
        response = self.session.request_json(url, data=data)
        self.session.evict(self.session.config['user'])
        return response

    def edit(self, text):
        """Replace the body of the object with `text`.

        :returns: The updated object.

        """
        url = self.session.config['edit']
        data = {'thing_id': self.fullname,
                'text': text}
        response = self.session.request_json(url, data=data)
        self.session.evict(self.session.config['user'])
        return response['data']['things'][0]


class AIList(HutomaObject):
    pass


class AI(Editable):
    """A moderator action."""

    def __init__(self, session, json_dict=None, fetch=False):
        """Construct an instance of the ModAction object."""
        super(AI, self).__init__(session, json_dict, fetch)


class Folder(Editable):
    pass


class Chat(HutomaObject):
    pass


class Speak(HutomaObject):
    pass


class Training(HutomaObject):
    pass