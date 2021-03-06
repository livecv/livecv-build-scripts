import sys
import os
import getopt
import json
import shutil
import argparse

from livepm.lib.command import Command
from livepm.lib.configuration import Configuration
from livepm.lib.process import *
from livepm.lib.filesystem import FileSystem

class DeployCommand(Command):
    name = 'deploy'
    description = 'Deploy and pack a live package'

    def __init__(self):
        pass

    def parse_args(self, argv):
        parser = argparse.ArgumentParser(description='Deploy a live package')
        parser.add_argument('--source', '-s', default=None, help='Path to source directory or package file.')
        parser.add_argument('--options', '-o', default=None, help='Specific deploy options.')
        parser.add_argument('--build', '-b', default=None, help='Custom build directory. Default directory is build.')
        parser.add_argument('--makedoc', default=None, help='Enable documentation generation.')
        parser.add_argument('package_path', default='', help="Path to a livekeys package or package file.")
        parser.add_argument('release_id', default='', help="Id of release.")

        args = parser.parse_args(argv)

        self.package_file = Configuration.findpackage(os.path.abspath(args.package_path))
        self.release_id   = args.release_id
        self.source_dir   = args.source if args.source else os.path.dirname(self.package_file)
        self.build_dir    = args.build if args.build else self.source_dir + '/build'
        self.makedoc      = args.makedoc if args.makedoc else None

        self.source_dir = os.path.abspath(self.source_dir)
        # usage = 'Usage: livekeys_deploypy [-b <self.build_dir>] <buildfile> <self.release_id>'

    def __call__(self):

        print('\nParsing build file \'' + self.package_file + '\'...')

        with open(self.package_file) as jsonfile:
            packagejson = json.load(jsonfile)

        config = Configuration(packagejson)
        if ( not config.has_release(self.release_id) ):
            raise Exception("Failed to find release id:" + self.release_id)

        print('  Version:' + str(config.version))
        print('  Modules:')
        for key, value in config.components.items():
            print('   * ' + str(value))

        print('  Dependencies:')
        for value in config.dependencies:
            print('   * ' + str(value))

        release = config.release(self.release_id)
        releasedir = os.path.abspath(os.path.join(self.build_dir, release.compiler))

        print('\nConfiguration found: ' + self.release_id)
        print('  Source dir: \'' + self.source_dir + '\'')
        print('  Release dir: \'' + releasedir + '\'')
        print('  Compiler: \'' + release.compiler + '\'')

        release.init_environment()
        print('  Environment:')
        for key, value in release.environment.items():
            print('   * ' + key + '[' + value + ']: \'' + os.environ[key] + '\'')

        buildname = release.release_name()
        deploydir = os.path.abspath(releasedir + '/../' + buildname)
        releasename = release.name.replace('.', '-')

        deploydirroot = deploydir + '/' + releasename + '/'
        if releasename == 'livekeys' and sys.platform.lower() == 'darwin':
            deploydirroot = deploydir + '/'

        print('\nCleaning deploy dir: \'' + deploydir + '\'')

        if (os.path.isdir(deploydir)):
            shutil.rmtree(deploydir)

        print('Creating deploy dir: \'' + deploydirroot + '\'')
        os.makedirs(deploydirroot)

        print('\nExecuting deployment steps:')
        for value in release.deploysteps:
            print('\n *** ' + str(value).upper() + ' *** \n')
            value(self.source_dir, releasedir, os.environ)

        if ( self.makedoc ):
            self.makedoc = os.path.abspath(self.makedoc)

            print('\n *** Creating documentation *** \n')
            doc_outpath = os.path.join(deploydir, release.document) if release.document else os.path.join(deploydir, releasename, 'doc')
            os.makedirs(doc_outpath)
            proc = Process.run(['node'] + [self.makedoc] + ['--output-path', doc_outpath] + [self.source_dir], os.path.dirname(self.makedoc), os.environ)
            Process.trace('LIVEDOC: ', proc, end='')

        print('\nRemoving junk...')

        jl = ''

        for subdir, dirs, files in os.walk(deploydirroot):
            for file in files:
                filepath = os.path.join(subdir, file)
                if ( file == '.gitignore' ):
                    os.remove(filepath)
                    jl += ' * Removed:' + filepath + '; '
        # print(jl)

        print('\nCreating archive...')
        archive_name = ''
        archive_root_dir = ''
        archive_extension = ''

        if ( sys.platform.lower().startswith("win") ):
            archive_name = deploydirroot + '/..'
            archive_root_dir = deploydir
            archive_extension = "zip"
        elif sys.platform.lower() == 'darwin':
            archive_name = deploydirroot
            archive_root_dir = deploydirroot
            archive_extension = "gztar"

            if Process.exists('create-dmg'):
                proc = Process.run(['create-dmg', 'livekeys.app'], deploydirroot)
                Process.trace('CREATEDMG: ', proc, end='')
                for index, appfile in enumerate(FileSystem.listEntries(os.path.join(deploydirroot, '*.dmg'))):
                    appfile_name = os.path.basename(appfile)
                    print('CREATEDMG File: ' + appfile_name)
                    os.rename(appfile, os.path.join(deploydirroot, '..', appfile_name))
        else:
            archive_name = deploydir
            archive_root_dir = deploydir
            archive_extension = "gztar"

        print(" * Archive Name: " + archive_name + "[" + archive_extension + "]")
        print(" * Archive Root dir: " + archive_root_dir)
        shutil.make_archive(archive_name, archive_extension, archive_root_dir)

        print("Done")