# coding=utf8
"""
*Availability: 3+ for all functions; attributes may vary.*

The config class is an abstraction class for accessing the active Willie
configuration file.

The Willie config file is divided to sections, and each section contains keys
and values. A section is an attribute of the config class, and is of type
``ConfigSection``. Each section contains the keys as attributes. For example,
if you want to access key example from section test, use
``config.test.example``. Note that the key names are made lower-case by the
parser, regardless of whether they are upper-case in the file.

The ``core`` section will always be present, and contains configuration used by
the Willie core. Modules are allowed to read those, but must not change them.

The config file can store strings, booleans and lists. If you need to store a
number, cast it to ``int()`` when reading.

For backwards compatibility, every key in the core section is an attribute of
the config class as well as of config.core. For new code, always specify the
name of the section, because this behavior might be removed in the future.

Running the ``config.py`` file directly will give the user an interactive
series of dialogs to create the configuration file. This will guide the user
through creating settings for the Willie core, the settings database, and any
modules which have a configuration function.

The configuration function, if used, must be declared with the signature
``configure(config)``. To add options, use ``interactive_add``, ``add_list``
and ``add_option``.
"""
#Copyright 2012, Edward Powell, embolalia.net
#Copyright © 2012, Elad Alfassa <elad@fedoraproject.org>
#Licensed under the Eiffel Forum License 2.

from __future__ import unicode_literals
from __future__ import print_function
from __future__ import absolute_import

from willie.tools import iteritems
import os
import sys
try:
    import ConfigParser
except ImportError:
    import configparser as ConfigParser
import getpass
import imp
if sys.version_info.major >= 3:
    unicode = str
    basestring = str
    get_input = input
else:
    get_input = lambda x: raw_input(x).decode('utf8')


class ConfigurationError(Exception):
    """Exception type for configuration errors"""

    def __init__(self, value):
        self.value = value

    def __str__(self):
        return 'ConfigurationError: %s' % self.value


class Config(object):
    def __init__(self, path):
        """Return a configuration object.

        The given path will be associated with the configuration, and is
        the file which will be written if save() is called. If load is not
        given or True, the configuration object will load the attributes from
        the file at path.

        A few default values will be set here if they are not defined in the
        config file, or a config file is not loaded. They are documented below.

        """
        self.path = path

        self.parser = ConfigParser.RawConfigParser(allow_no_value=True)
        self.get = self.parser.get
        self.has_option = self.parser.has_option
        self.has_section = self.parser.has_section

        if os.path.isfile(path):
            self.parser.read(self.path)

        # Set defaults
        defaults = [('core', 'port', '6667'),
                    ('core', 'user', 'wily'),
                    ('core', 'name', 'WilyBot'),
                    ('core', 'prefix', r'\.'),
                    ('core', 'admins', ''),
                    ('core', 'verify_ssl', 'True'),
                    ('core', 'timeout', '120'),
                    ]
        self.add_section('core')
        for section, option, defval in defaults:
            if not self.has_option(section, option):
                self.parser.set(section, option, defval)

    def check(self):
        # Generate file if it doesn't exist
        if not os.path.isfile(self.path):
            print("Couldn't find the configuration file. Let's generate it.\n")
            self.configure_core()
            if self.option("Would you like to see if there are any modules "
                           "that need configuring"):
                self.configure_modules()
            self.save()
            print("Configuration file written successfully!")

        # Sanity check on critical options
        if not self.has_section('core'):
            raise ConfigurationError('Missing [core] section from configuration file.')
        if not self.has_option('core', 'nick'):
            raise ConfigurationError(
                'Bot IRC nick not configured, expected option `nick` in [core] section.')
        if not self.has_option('core', 'owner'):
            raise ConfigurationError(
                'Bot owner not configured, expected option `owner` in [core] section.')
        if not self.has_option('core', 'host'):
            raise ConfigurationError(
                'IRC server address not configured, expected option `host` in [core] section.')

    def save(self):
        """Save all changes to the config file."""
        with open(self.path, 'w') as cfgfile:
            self.parser.write(cfgfile)

    class ConfigSection(object):
        """Represents a section of the config file.

        Contains all keys in the section as attributes.

        """
        def __init__(self, name, items, parent):
            object.__setattr__(self, '_name', name)
            object.__setattr__(self, '_parent', parent)
            for item in items:
                value = item[1].strip()
                if not value.lower() == 'none':
                    if value.lower() == 'false':
                        value = False
                    object.__setattr__(self, item[0], value)

        def __getattr__(self, name):
            return None

        def __setattr__(self, name, value):
            object.__setattr__(self, name, value)
            if type(value) is list:
                value = ','.join(value)
            self._parent.parser.set(self._name, name, value)

        def get_list(self, name):
            value = getattr(self, name)
            if not value:
                return []
            if isinstance(value, basestring):
                value = value.split(',')
                # Keep the split value, so we don't have to keep doing this
                setattr(self, name, value)
            return value

    def __getattr__(self, name):
        """"""
        if name in self.parser.sections():
            items = self.parser.items(name)
            section = self.ConfigSection(name, items, self)  # Return a section
            setattr(self, name, section)
            return section
        elif self.parser.has_option('core', name):
            return self.parser.get('core', name)  # For backwards compatibility
        else:
            raise AttributeError("%r object has no attribute %r"
                                 % (type(self).__name__, name))

    def add_section(self, name):
        """Add a section to the config file.

        Returns ``False`` if already exists.

        """
        try:
            return self.parser.add_section(name)
        except ConfigParser.DuplicateSectionError:
            return False

    def add_option(self, section, option, question, default=False):
        """Ask "y/n" and set `option` based in the response.

        Show user in terminal a "y/n" prompt, and set `option` to True or False
        based on the response. If default is passed as true, the default will
        be shown as ``[y]``, else it will be ``[n]``. ``question`` should be
        phrased as a question, but without a question mark at the end. If
        ``option`` is already defined, it will be used instead of ``default``,
        regardless of wheather ``default`` is passed.

        """
        self.add_section(section)
        if self.parser.has_option(section, option):
            default = self.parser.getboolean(section, option)
        answer = self.option(question, default)
        self.parser.set(section, option, str(answer))

    def option(self, question, default=False):
        """Ask "y/n" and return the corresponding boolean answer.

        Show user in terminal a "y/n" prompt, and return true or false based on
        the response. If default is passed as true, the default will be shown
        as ``[y]``, else it will be ``[n]``. ``question`` should be phrased as
        a question, but without a question mark at the end.

        """
        d = 'y' if default else 'n'
        ans = get_input('% (y/n)? [%] ' % question, d) or d
        return ans.lower() == 'y'

    def interactive_add(self, section, option, prompt, default=None, ispass=False):
        """Ask for the value to assign to ``option`` under ``section``.

        Ask user in terminal for the value to assign to ``option`` under
        ``section``. If ``default`` is passed, it will be shown as the default
        value in the prompt. If ``option`` is already defined in ``section``,
        it will be used instead of ``default``, regardless of wheather
        ``default`` is passed.

        """
        self.parser.add_section(section)
        if self.parser.has_option(section, option):
            atr = self.parser.get(section, option)
            if ispass:
                value = getpass.getpass(prompt + ' [%s]: ' % atr) or atr
                self.parser.set(section, option, value)
            else:
                value = get_input(prompt + ' [%s]: ' % atr) or atr
                self.parser.set(section, option, value)
        elif default:
            if ispass:
                value = getpass.getpass(
                    prompt + ' [%s]: ' % default
                ) or default
                self.parser.set(section, option, value)
            else:
                value = get_input(prompt + ' [%s]: ' % default) or default
                self.parser.set(section, option, value)
        else:
            value = ''
            while not value:
                if ispass:
                    value = getpass.getpass(prompt + ': ')
                else:
                    value = get_input(prompt + ': ')
            self.parser.set(section, option, value)

    def add_list(self, section, option, message, prompt):
        """Ask for a list to assign to ``option``.

        Ask user in terminal for a list to assign to ``option``. If ``option``
        is already defined under ``section``, show the user the current values
        and ask if the user would like to keep them. If so, additional values
        can be entered.

        """
        print(message)
        lst = []
        if self.parser.has_option(section, option) and self.parser.get(section,
                                                                       option):
            m = "You currently have " + self.parser.get(section, option)
            if self.option(m + '. Would you like to keep them', True):
                lst = self.parser.get(section, option).split(',')
        mem = get_input(prompt + ' ')
        while mem:
            lst.append(mem)
            mem = get_input(prompt + ' ')
        self.parser.set(section, option, ','.join(lst))

    def configure_core(self):
        self.interactive_add('core', 'nick', 'Enter the nickname for your bot', 'Willie')
        self.interactive_add('core', 'host', 'Enter the server to connect to', 'irc.dftba.net')
        self.add_option('core', 'use_ssl', 'Should the bot connect with SSL')
        self.interactive_add('core', 'port', 'Enter the port to connect on',
                             '6697' if self.core.use_ssl else '6667')
        self.interactive_add('core', 'owner',
            "Enter your own IRC name (or that of the bot's owner)")
        self.add_list('core', 'channels',
                      'Enter the channels to connect to by default, one at a time. '
                      'When done, hit enter again.', 'Channel:')

    def configure_modules(self):
        home = os.getcwd()
        modules_dir = os.path.join(home, 'modules')
        filenames = self.enumerate_modules()
        os.sys.path.insert(0, modules_dir)
        for name, filename in iteritems(filenames):
            try:
                module = imp.load_source(name, filename)
            except Exception as e:
                print("Error loading %s: %s (in config.py)"
                      % (name, e), file=sys.stderr)
            else:
                if hasattr(module, 'configure'):
                    module.configure(self)

    def configure_all(self):
        self.configure_core()
        if self.option("Would you like to see if there are any modules that need configuring"):
            self.configure_modules()

    def enumerate_modules(self, show_all=False):
        """Map the names of modules to the location of their file.

        *Availability: 4.0+*

        Return a dict mapping the names of modules to the location of their
        file.  This searches the regular modules directory and all directories
        specified in the `core.extra` attribute of the `config` object. If two
        modules have the same name, the last one to be found will be returned
        and the rest will be ignored. Modules are found starting in the regular
        directory, followed by `~/.willie/modules`, and then through the extra
        directories in the order that the are specified.

        If `show_all` is given as `True`, the `enable` and `exclude`
        configuration options will be ignored, and all modules will be shown
        (though duplicates will still be ignored as above).

        """
        modules = {}

        # First, add modules from the regular modules directory
        this_dir = os.path.dirname(os.path.abspath(__file__))
        modules_dir = os.path.join(this_dir, 'modules')
        for fn in os.listdir(modules_dir):
            if fn.endswith('.py') and not fn.startswith('_'):
                modules[fn[:-3]] = os.path.join(modules_dir, fn)
        # Next, look in ~/.willie/modules
        if self.core.homedir is not None:
            home_modules_dir = os.path.join(self.core.homedir, 'modules')
        else:
            home_modules_dir = os.path.join(os.path.expanduser('~'), '.willie',
                                            'modules')
        if not os.path.isdir(home_modules_dir):
            os.makedirs(home_modules_dir)
        for fn in os.listdir(home_modules_dir):
            if fn.endswith('.py') and not fn.startswith('_'):
                modules[fn[:-3]] = os.path.join(home_modules_dir, fn)

        # Last, look at all the extra directories. (get_list returns [] if
        # there are none or the option isn't defined, so it'll just skip this
        # bit)
        for directory in self.core.get_list('extra'):
            for fn in os.listdir(directory):
                if fn.endswith('.py') and not fn.startswith('_'):
                    modules[fn[:-3]] = os.path.join(directory, fn)

        # If caller wants all of them, don't apply white and blacklists
        if show_all:
            return modules

        # Apply whitelist, if present
        enable = self.core.get_list('enable')
        if enable:
            enabled_modules = {}
            for module in enable:
                if module in modules:
                    enabled_modules[module] = modules[module]
            modules = enabled_modules

        # Apply blacklist, if present
        exclude = self.core.get_list('exclude')
        for module in exclude:
            if module in modules:
                del modules[module]

        return modules


def check_home_dir(homedir, create=True):
    """Check to see if the home directory exists, and optionally try to create it if not."""
    if os.path.isdir(homedir):
        return homedir
    if create:
        try:
            os.makedirs(homedir)
            return homedir
        except:
            pass


def get_config(homedir, name='default', extension='.cfg'):
    if os.path.isfile(name):
        # we have the full config path
        path = name

    elif check_home_dir(homedir):
        # construct path from name and extension
        if not name.endswith(extension):
            name += extension
        path = os.path.join(homedir, name)

    else:
        # home dir doesn't exist and we can't create it
        print("Couldn't find the config directory.")
        return

    return Config(path)


def enumerate_configs(homedir, extension='.cfg'):
    if not os.path.isdir(homedir):
        return []

    return [item for item in os.listdir(homedir) if item.endswith(extension)]
