#!/usr/bin/env python
from __future__ import with_statement

import filecmp
import logging

import os
import sys
import errno
import re
from shutil import copy

from fuse import FUSE, FuseOSError, Operations, LoggingMixIn


class VersionFS(LoggingMixIn, Operations):
    def __init__(self):
        # get current working directory as place for versions tree
        self.root = os.path.join(os.getcwd(), '.versiondir')
        # check to see if the versions directory already exists
        if os.path.exists(self.root):
            print 'Version directory already exists.'
        else:
            print 'Creating version directory.'
            os.mkdir(self.root)

    # Helpers
    # =======

    def _full_path(self, partial):
        if partial.startswith("/"):
            partial = partial[1:]
        path = os.path.join(self.root, partial)
        return path

    # Filesystem methods
    # ==================

    def access(self, path, mode):
        # print "access:", path, mode
        full_path = self._full_path(path)
        if not os.access(full_path, mode):
            raise FuseOSError(errno.EACCES)

    def chmod(self, path, mode):
        # print "chmod:", path, mode
        full_path = self._full_path(path)
        return os.chmod(full_path, mode)

    def chown(self, path, uid, gid):
        # print "chown:", path, uid, gid
        full_path = self._full_path(path)
        return os.chown(full_path, uid, gid)

    def getattr(self, path, fh=None):
        # print "getattr:", path
        full_path = self._full_path(path)
        st = os.lstat(full_path)
        return dict((key, getattr(st, key)) for key in ('st_atime', 'st_ctime',
                                                        'st_gid', 'st_mode', 'st_mtime', 'st_nlink', 'st_size',
                                                        'st_uid'))

    def readdir(self, path, fh):
        # print "readdir:", path
        full_path = self._full_path(path)

        dirents = ['.', '..']
        if os.path.isdir(full_path):
            dirents.extend(os.listdir(full_path))

        for r in dirents:
            # Matches basic pattern of filename.extension.v1
            # Only show the latest version in mount
            pattern = re.compile(r'[\w.]+v[0-9]+')

            if not re.match(pattern, r):
                yield r

    def readlink(self, path):
        # print "readlink:", path
        pathname = os.readlink(self._full_path(path))
        if pathname.startswith("/"):
            # Path name is absolute, sanitize it.
            return os.path.relpath(pathname, self.root)
        else:
            return pathname

    def mknod(self, path, mode, dev):
        # print "mknod:", path, mode, dev
        return os.mknod(self._full_path(path), mode, dev)

    def rmdir(self, path):
        # print "rmdir:", path
        full_path = self._full_path(path)
        return os.rmdir(full_path)

    def mkdir(self, path, mode):
        # print "mkdir:", path, mode
        return os.mkdir(self._full_path(path), mode)

    def statfs(self, path):
        # print "statfs:", path
        full_path = self._full_path(path)
        stv = os.statvfs(full_path)
        return dict((key, getattr(stv, key)) for key in ('f_bavail', 'f_bfree',
                                                         'f_blocks', 'f_bsize', 'f_favail', 'f_ffree', 'f_files',
                                                         'f_flag',
                                                         'f_frsize', 'f_namemax'))

    def unlink(self, path):
        # print "unlink:", path
        return os.unlink(self._full_path(path))

    def symlink(self, name, target):
        # print "symlink:", name, target
        return os.symlink(target, self._full_path(name))

    def rename(self, old, new):
        # print "rename:", old, new
        return os.rename(self._full_path(old), self._full_path(new))

    def link(self, target, name):
        # print "link:", target, name
        return os.link(self._full_path(name), self._full_path(target))

    def utimens(self, path, times=None):
        # print "utimens:", path, times
        return os.utime(self._full_path(path), times)

    # File methods
    # ============

    def open(self, path, flags):
        print '** open:', path, '**'
        full_path = self._full_path(path)
        return os.open(full_path, flags)

    def create(self, path, mode, fi=None):
        print '** create:', path, '**'
        full_path = self._full_path(path)
        return os.open(full_path, os.O_WRONLY | os.O_CREAT, mode)

    def read(self, path, length, offset, fh):
        print '** read:', path, '**'
        os.lseek(fh, offset, os.SEEK_SET)
        return os.read(fh, length)

    def write(self, path, buf, offset, fh):
        print '** write:', path, '**'
        os.lseek(fh, offset, os.SEEK_SET)
        return os.write(fh, buf)

    def truncate(self, path, length, fh=None):
        print '** truncate:', path, '**'
        full_path = self._full_path(path)
        with open(full_path, 'r+') as f:
            f.truncate(length)

    def flush(self, path, fh):
        print '** flush', path, '**'
        return os.fsync(fh)

    def release(self, path, fh):
        print '** release', path, '**'

        # Check if opening a versioned file not to create a version
        versioned_pattern = re.compile(r'/\w+\.\w+\.v[0-9]+')
        swp_pattern = re.compile(r'/\.\w+\.\w+\.swp')

        # If not a versioned file, and swp file make versions
        if not re.match(versioned_pattern, path) and not re.match(swp_pattern, path):
            for x in range(6, 0, -1):
                older_path = self._full_path(path) + ".v" + str(x)
                newer_path = self._full_path(path) + ".v" + str(x - 1)

                if x == 1:
                    newer_path = self._full_path(path)
                    if not os.path.isfile(older_path) or \
                            (os.path.isfile(older_path) and not filecmp.cmp(newer_path, older_path)):
                        copy(newer_path, older_path)
                elif x == 2:
                    if os.path.isfile(newer_path) and not filecmp.cmp(newer_path, self._full_path(path)):
                        copy(newer_path, older_path)
                else:
                    if os.path.isfile(newer_path):
                        copy(newer_path, older_path)

        #
        # for i in range(6, 0, -1):
        #     old_versioned_path = self._full_path(path) + ".v" + str(i)
        #     if i == 1:
        #         # Only if versioned file doesnt exist or if the open file isn't equal to v1 file, then make version
        #         if not os.path.isfile(old_versioned_path) \
        #                 or not filecmp.cmp(self._full_path(path), old_versioned_path, shallow=False):
        #             copy(self._full_path(path), old_versioned_path)
        #
        #     else:
        #         versioned_path = self._full_path(path) + ".v" + str(i - 1)
        #
        #         # Only if previous version is a file, and the two are not equal make a new push old version
        #         # further down
        #         if os.path.isfile(versioned_path) and (not os.path.isfile(old_versioned_path) or i == 6):
        #             copy(versioned_path, old_versioned_path)

        return os.close(fh)

    def fsync(self, path, fdatasync, fh):
        print '** fsync:', path, '**'
        return self.flush(path, fh)


def main(mountpoint):
    FUSE(VersionFS(), mountpoint, nothreads=True, foreground=True)


if __name__ == '__main__':
    # logging.basicConfig(level=logging.DEBUG)
    main(sys.argv[1])
