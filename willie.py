#!/usr/bin/env python2.7
# coding=utf8
"""
Willie - An IRC Bot
Copyright © 2008, Sean B. Palmer, inamidst.com
Copyright © 2012-2014, Elad Alfassa <elad@fedoraproject.org>
Licensed under the Eiffel Forum License 2.

http://willie.dftba.net
"""
from __future__ import unicode_literals
from __future__ import print_function

import sys
from willie.tools import stderr

if sys.version_info < (2, 7):
    stderr('Error: Requires Python 2.7 or later. Try python2.7 willie')
    sys.exit(1)
elif sys.version_info.major == 3 and sys.version_info.minor < 3:
    stderr('Error: When running on Python 3, Python 3.3 is required.')
    sys.exit(1)

import os
import argparse
import signal

from willie.__init__ import run, __version__
from willie import config as cfg
from willie import tools


def main(argv=None):
    homedir = os.path.join(os.path.expanduser('~'), '.willie')

    # Exit if running as root
    try:
        if os.getuid() == 0 or os.geteuid() == 0:
            stderr('Error: Do not run Willie with root privileges.')
            sys.exit(1)
    except AttributeError:
        # Windows doesn't have os.getuid/os.geteuid
        pass

    # Parse the command line
    parser = argparse.ArgumentParser(description='Willie IRC Bot', usage='%(prog)s [options]')
    parser.add_argument('-c', '--config', metavar='filename', default='default',
                        help='Use a specific configuration file')
    parser.add_argument('-d', '--fork', action='store_true', dest='daemonize',
                        help='Daemonize willie')
    parser.add_argument('-q', '--quit', action='store_true', dest='quit',
                        help='Gracefully quit Willie')
    parser.add_argument('-k', '--kill', action='store_true', dest='kill',
                        help='Kill Willie')
    parser.add_argument('--exit-on-error', action='store_true', dest='exit_on_error',
                        help='Exit immediately on every error instead of trying to recover')
    parser.add_argument('-l', '--list', action='store_true', dest='list_configs',
                        help='List all config files found')
    parser.add_argument('-m', '--migrate', action='store_true', dest='migrate_configs',
                        help='Migrate config files to the new format')
    parser.add_argument('--quiet', action='store_true', dest='quiet',
                        help='Suppress all output')
    parser.add_argument('-w', '--configure-all', action='store_true', dest='wizard',
                        help='Run the configuration wizard')
    parser.add_argument('--configure-modules', action='store_true', dest='mod_wizard',
                        help=('Run the configuration wizard, but only for the '
                              'module configuration options'))
    parser.add_argument('-v', '--version', action='store_true', dest='version',
                        help='Show version number and exit')
    opts = parser.parse_args()

    try:
        if opts.version:
            print('Wily %s (running on python %s.%s.%s)' % (__version__,
                                                            sys.version_info.major,
                                                            sys.version_info.minor,
                                                            sys.version_info.micro))
            print('https://github.com/saltire/wily')
            return

        if opts.list_configs:
            configs = cfg.enumerate_configs(homedir)
            print('Config files in ~/.willie:')
            if len(configs) is 0:
                print('\tNone found')
            else:
                for config in configs:
                    print('\t%s' % config)
            print('-------------------------')
            return

        config = cfg.get_config(homedir, opts.config)

        if opts.wizard:
            config.configure_all()
            config.save()
            return
        elif opts.mod_wizard:
            config.configure_modules()
            config.save()
            return

        config.check()

        if config.has_option('core', 'homedir'):
            homedir = config.core.homedir
        else:
            config.core.homedir = homedir

        # Configure logging
        if not config.core.logdir:
            config.core.logdir = os.path.join(homedir, 'logs')
        if not os.path.isdir(config.logdir):
            os.mkdir(config.logdir)
        logfile = os.path.join(config.logdir, 'stdio.log')

        config.exit_on_error = opts.exit_on_error
        config._is_daemonized = opts.daemonize

        sys.stderr = tools.OutputRedirect(logfile, True, opts.quiet)
        sys.stdout = tools.OutputRedirect(logfile, False, opts.quiet)

        # Handle --quit, --kill and saving the PID to file
        pid_dir = config.core.pid_dir or homedir
        basename = os.path.splitext(os.path.basename(opts.config))[0]
        pid_file_path = os.path.join(pid_dir, 'willie-%s.pid' % basename)

        old_pid = None
        if os.path.isfile(pid_file_path):
            with open(pid_file_path, 'r') as pid_file:
                try:
                    old_pid = int(pid_file.read())
                except ValueError:
                    pass

        if old_pid is not None and tools.check_pid(old_pid):
            if opts.quit:
                stderr('Signaling Willie to stop gracefully.')
                if hasattr(signal, 'SIGUSR1'):
                    os.kill(old_pid, signal.SIGUSR1)
                else:
                    os.kill(old_pid, signal.SIGTERM)
                sys.exit(0)
            elif opts.kill:
                stderr('Killing Willie.')
                os.kill(old_pid, signal.SIGKILL)
                sys.exit(0)
            else:
                stderr("There's already a Willie instance running with this config file.")
                stderr("Try using the --quit or the --kill options.")
                sys.exit(1)
        elif opts.quit or opts.kill:
            stderr('Willie is not running!')
            sys.exit(1)

        if opts.daemonize:
            child_pid = os.fork()
            if child_pid is not 0:
                sys.exit()

        with open(pid_file_path, 'w') as pid_file:
            pid_file.write(str(os.getpid()))

        config.pid_file_path = pid_file_path

        # Initialize and run Willie
        run(config)

    except KeyboardInterrupt:
        print("\n\nInterrupted.")
        os._exit(1)


if __name__ == '__main__':
    main()
