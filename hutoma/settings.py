from __future__ import print_function, unicode_literals

import os
import sys

try:
    import ConfigParser as config_parser
except ImportError:
    import configparser  # NOQA pylint: disable=F0401


def _load_configuration():
    """Attempt to load settings from various hutoma.ini files."""
    config = config_parser.RawConfigParser()
    module_dir = os.path.dirname(sys.modules[__name__].__file__)
    if 'APPDATA' in os.environ:  # Windows
        os_config_path = os.environ['APPDATA']
    elif 'XDG_CONFIG_HOME' in os.environ:  # Modern Linux
        os_config_path = os.environ['XDG_CONFIG_HOME']
    elif 'HOME' in os.environ:  # Legacy Linux
        os_config_path = os.path.join(os.environ['HOME'], '.config')
    else:
        os_config_path = None
    locations = [os.path.join(module_dir, 'hutoma.ini'), 'hutoma.ini']
    if os_config_path is not None:
        locations.insert(1, os.path.join(os_config_path, 'hutoma.ini'))
    if not config.read(locations):
        raise Exception('Could not find config file in any of: {0}'
                        .format(locations))
    return config
CONFIG = _load_configuration()
del _load_configuration