# -*- coding: utf-8 -*-
# Copyright (C) 2014 Canonical
#
# Authors:
#  Juan Olivares
#
# This program is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation; version 3.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA


"""Generic Build Tool module."""

from gettext import gettext as _
import logging
import platform

from os.path import join
import udtc.frameworks.baseinstaller
from udtc.network.download_center import DownloadCenter
from udtc.tools import create_launcher, get_application_desktop_file
from udtc.ui import UI


logger = logging.getLogger(__name__)


class BuildToolCategory(udtc.frameworks.BaseCategory):
    def __init__(self):
        super().__init__(name=_("Build Tool"), description=_("Build Tools"),
                         logo_path=None)


class Maven(udtc.frameworks.baseinstaller.BaseInstaller):    
    """The Apache Foundation distribution."""
    DOWNLOAD_URL_PAT = "http://www.apache.org/dist/maven/maven-3/{release}/binaries" \
                       "apache-maven-{release}-bin.tar.gz{suf}"
    RELEASE = '3.2.3'

    def __init__(self, category):
        super().__init__(name=_("Maven"),
                         description=_("Apache Maven 3 (3.2.3)"),
                         category=category, only_on_archs=['i386', 'amd64'],
                         download_page=None,
                         dir_to_decompress_in_tarball='apache-maven',
                         packages_requirements=['openjdk-7-jdk'])

    def download_provider_page(self):
        """First, we need to fetch the MD5, then kick off the proceedings.

        This could actually be done in parallel, in a future version.
        """
        logger.debug("Preparing to download MD5.")

        md5_url = self.DOWNLOAD_URL_PAT.format(release=RELEASE, suf='.md5')

        def done(download_result):
            res = download_result[md5_url]

            if res.error:
                logger.error(res.error)
                UI.return_main_screen()
                return

            # Should be ASCII anyway.
            md5 = res.buffer.getvalue().decode('utf-8').split()[0]
            logger.debug("Downloaded MD5 is {}".format(md5))

            logger.debug("Preparing to download the main archive.")

            download_url = self.DOWNLOAD_URL_PAT.format(release=RELEASE, suf='')

            self.download_requests.append((download_url, md5))
            self.start_download_and_install()

        DownloadCenter(urls=[md5_url], on_done=done, download=False)

    def create_launcher(self):
        """Create the env variables"""
        # add maven to PATH
        paths_to_add = [os.path.join(self.install_path, "bin")]
        add_to_user_path(paths_to_add, self.name)

    @property
    def is_installed(self):
        # check path and requirements
        if not super().is_installed:
            return False
        if not join(self.install_path, "apapche-maven"):
            logger.debug("{} binary isn't installed".format(self.name))
            return False
        return True
