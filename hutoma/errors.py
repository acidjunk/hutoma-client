"""
Error classes.

Includes two main exceptions: ClientException, when something goes
wrong on our end, and APIExeception for when something goes wrong on the
server side. A number of classes extend these two main exceptions for more
specific exceptions.
"""

from __future__ import print_function, unicode_literals

import inspect
import six
import sys


class HutomaException(Exception):
    """The base Hutoma Exception class.

    Ideally, this can be caught to handle any exception from Hutoma.

    """


class ClientException(HutomaException):
    """Base exception class for errors that don't involve the remote API."""

    def __init__(self, message=None):
        """Construct a ClientException.

        :param message: The error message to display.

        """
        if not message:
            message = 'Clientside error'
        super(ClientException, self).__init__()
        self.message = message

    def __str__(self):
        """Return the message of the error."""
        return self.message


class UserKeyRequired(ClientException):
    """Indicates that a user_key required."""

    def __init__(self, function, message=None):
        """Construct a UserKeyRequired exception.

        :param function: The function that requires user_key authentication.
        :param message: A custom message to associate with the exception.
            Default: `function` requires a user_key

        """
        if not message:
            message = '{0} requires a user_key'.format(function)
        super(UserKeyRequired, self).__init__(message)


class ValidAIRequired(ClientException):
    """Indicates that a AI is required."""

    def __init__(self, function):
        """Construct a ValidAIRequired exception.

        :param function: The function that requires a valid AI.

        """
        message = '{0} requires a AI'.format(function)
        super(ValidAIRequired, self).__init__(message)


class HTTPException(HutomaException):
    """Base class for HTTP related exceptions."""

    def __init__(self, _raw, message=None):
        """Construct a HTTPException.

        :params _raw: The internal request library response object. This object
            is mapped to attribute `_raw` whose format may change at any time.

        """
        if not message:
            message = 'HTTP error'
        super(HTTPException, self).__init__()
        self._raw = _raw
        self.message = message

    def __str__(self):
        """Return the message of the error."""
        return self.message


class Forbidden(HTTPException):
    """Raised when the user does not have permission to the entity."""


class NotFound(HTTPException):
    """Raised when the requested entity is not found."""


class RedirectException(HutomaException):
    """Raised when a redirect response occurs that is not expected."""

    def __init__(self, request_url, response_url, message=None):
        """Construct a RedirectException.

        :param request_url: The url requested.
        :param response_url: The url being redirected to.
        :param message: A custom message to associate with the exception.

        """
        if not message:
            message = ('Unexpected redirect '
                       'from {0} to {1}').format(request_url, response_url)
        super(RedirectException, self).__init__()
        self.request_url = request_url
        self.response_url = response_url
        self.message = message

    def __str__(self):
        """Return the message of the error."""
        return self.message


class APIException(HutomaException):
    """Base exception class for a Hutoma API error message exception.

    All exceptions of this type should have their own subclass.

    """

    def __init__(self, error_type, message, field='', response=None):
        """Construct an APIException.

        :param error_type: The error type set on hutoma's end.
        :param message: The associated message for the error.
        :param field: The input field associated with the error, or ''.
        :param response: The HTTP response that resulted in the exception.

        """
        super(APIException, self).__init__()
        self.error_type = error_type
        self.message = message
        self.field = field
        self.response = response

    def __str__(self):
        """Return a string containing the error message and field."""
        if hasattr(self, 'ERROR_TYPE'):
            return '`{0}` on field `{1}`'.format(self.message, self.field)
        else:
            return '({0}) `{1}` on field `{2}`'.format(self.error_type,
                                                       self.message,
                                                       self.field)


class ExceptionList(APIException):
    """Raised when more than one exception occurred."""

    def __init__(self, errors):
        """Construct an ExceptionList.

        :param errors: The list of errors.

        """
        super(ExceptionList, self).__init__(None, None)
        self.errors = errors

    def __str__(self):
        """Return a string representation for all the errors."""
        ret = '\n'
        for i, error in enumerate(self.errors):
            ret += '\tError {0}) {1}\n'.format(i, six.text_type(error))
        return ret


class BadUserKey(APIException):
    """An exception to indicate an invalid user_key was used."""

    ERROR_TYPE = 'BAD_USER_KEY'


class NoAIFound(APIException):
    """An exception when a AI isn't found."""

    ERROR_TYPE = 'NO_AI_FOUND'


class RateLimitExceeded(APIException):
    """An exception for when something has happened too frequently.

    Contains a `sleep_time` attribute for the number of seconds that must
    transpire prior to the next request.

    """

    ERROR_TYPE = 'RATE_LIMIT'

    def __init__(self, error_type, message, field, response):
        """Construct an instance of the RateLimitExceeded exception.

        The parameters match that of :class:`APIException`.

        The `sleep_time` attribute is extracted from the response object.

        """
        super(RateLimitExceeded, self).__init__(error_type, message,
                                                field, response)
        self.sleep_time = self.response['ratelimit']


def _build_error_mapping():
    def predicate(obj):
        return inspect.isclass(obj) and hasattr(obj, 'ERROR_TYPE')

    tmp = {}
    for _, obj in inspect.getmembers(sys.modules[__name__], predicate):
        tmp[obj.ERROR_TYPE] = obj
    return tmp
ERROR_MAPPING = _build_error_mapping()
