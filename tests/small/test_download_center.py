# -*- coding: utf-8 -*-
# Copyright (C) 2014 Canonical
#
# Authors:
#  Didier Roche
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

"""Tests for the download center module using a local server"""

import os
from os.path import join, getsize
from time import time
from unittest.mock import Mock, call
from ..tools import get_data_dir, CopyingMock, LoggedTestCase
from ..tools.local_server import LocalHttp
from udtc.network.download_center import DownloadCenter


class TestDownloadCenter(LoggedTestCase):
    """This will test the download center by sending one or more download requests"""

    server = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server_dir = join(get_data_dir(), "server-content")
        cls.server = LocalHttp(cls.server_dir)

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def setUp(self):
        super().setUp()
        self.callback = Mock()
        self.fd_to_close = []

    def tearDown(self):
        super().tearDown()
        for fd in self.fd_to_close:
            fd.close()

    def build_server_address(self, path, localhost=False):
        """build server address to path to get requested"""
        return "{}/{}".format(self.server.get_address(localhost=localhost),
                              path)

    def wait_for_callback(self, mock_function_to_be_called):
        """wait for the callback to be called until a timeout.

        Add temp files to the clean file list afterwards"""
        timeout = time() + 5
        while not mock_function_to_be_called.called:
            if time() > timeout:
                raise(BaseException("Function not called within 5 seconds"))
        for calls in mock_function_to_be_called.call_args[0]:
            for request in calls:
                if calls[request].fd:
                    self.fd_to_close.append(calls[request].fd)
                if calls[request].buffer:
                    self.fd_to_close.append(calls[request].buffer)

    def test_download(self):
        """we deliver one successful download"""
        filename = "simplefile"
        request = self.build_server_address(filename)
        DownloadCenter([request], self.callback)
        self.wait_for_callback(self.callback)

        result = self.callback.call_args[0][0][request]
        self.assertTrue(self.callback.called)
        self.assertEqual(self.callback.call_count, 1)
        with open(join(self.server_dir, filename), 'rb') as file_on_disk:
            self.assertEqual(file_on_disk.read(),
                             result.fd.read())
            self.assertTrue('.' not in result.fd.name, result.fd.name)
        self.assertIsNone(result.buffer)
        self.assertIsNone(result.error)

    def test_redirect_download(self):
        """we deliver one successful download after being redirected"""
        filename = "simplefile"
        # We add a suffix to make the server redirect us.
        request = self.build_server_address(filename + "-redirect")
        DownloadCenter([request], self.callback)
        self.wait_for_callback(self.callback)

        result = self.callback.call_args[0][0][request]
        self.assertTrue(self.callback.called)
        self.assertEqual(self.callback.call_count, 1)
        with open(join(self.server_dir, filename), 'rb') as file_on_disk:
            self.assertEqual(file_on_disk.read(),
                             result.fd.read())
        self.assertIsNone(result.buffer)
        self.assertIsNone(result.error)

    def test_download_keep_extensions(self):
        """we deliver successful downloads keeping the extension"""
        filename = "android-studio-fake.tgz"
        request = self.build_server_address(filename)
        DownloadCenter([request], self.callback)
        self.wait_for_callback(self.callback)

        result = self.callback.call_args[0][0][request]
        self.assertTrue(self.callback.called)
        self.assertEqual(self.callback.call_count, 1)
        with open(join(self.server_dir, filename), 'rb'):
            self.assertTrue(result.fd.name.endswith('.tgz'), result.fd.name)

    def test_download_with_md5(self):
        """we deliver once successful download, matching md5sum"""
        filename = "simplefile"
        request = self.build_server_address(filename)
        DownloadCenter([(request, '268a5059001855fef30b4f95f82044ed')], self.callback)
        self.wait_for_callback(self.callback)

        result = self.callback.call_args[0][0][request]
        self.assertTrue(self.callback.called)
        self.assertEqual(self.callback.call_count, 1)
        with open(join(self.server_dir, filename), 'rb') as file_on_disk:
            self.assertEqual(file_on_disk.read(),
                             result.fd.read())
        self.assertIsNone(result.buffer)
        self.assertIsNone(result.error)

    def test_download_with_progress(self):
        """we deliver progress hook while downloading"""
        filename = "simplefile"
        filesize = getsize(join(self.server_dir, filename))
        report = CopyingMock()
        request = self.build_server_address(filename)
        DownloadCenter([request], self.callback, report=report)
        self.wait_for_callback(self.callback)

        self.assertEqual(report.call_count, 2)
        self.assertEqual(report.call_args_list,
                         [call({self.build_server_address(filename): {'size': filesize, 'current': 0}}),
                          call({self.build_server_address(filename): {'size': filesize, 'current': filesize}})])

    def test_download_with_multiple_progress(self):
        """we deliver multiple progress hooks on bigger files"""
        filename = "biggerfile"
        filesize = getsize(join(self.server_dir, filename))
        report = CopyingMock()
        request = self.build_server_address(filename)
        dl_center = DownloadCenter([request], self.callback, report=report)
        self.wait_for_callback(self.callback)

        self.assertEqual(report.call_count, 3)
        self.assertEqual(report.call_args_list,
                         [call({self.build_server_address(filename): {'size': filesize, 'current': 0}}),
                          call({self.build_server_address(filename): {'size': filesize,
                                                                      'current': dl_center.BLOCK_SIZE}}),
                          call({self.build_server_address(filename): {'size': filesize, 'current': filesize}})])

    def test_multiple_downloads(self):
        """we deliver more than on download in parallel"""
        requests = [self.build_server_address("biggerfile"), self.build_server_address("simplefile")]
        DownloadCenter(requests, self.callback)
        self.wait_for_callback(self.callback)

        # ensure we saw 2 different requests
        callback_args, callback_kwargs = self.callback.call_args
        map_result = callback_args[0]
        self.assertIn(self.build_server_address("biggerfile"), map_result)
        self.assertIn(self.build_server_address("simplefile"), map_result)
        # ensure each temp file corresponds to the source content
        for filename in ("biggerfile", "simplefile"):
            with open(join(self.server_dir, filename), 'rb') as file_on_disk:
                self.assertEqual(file_on_disk.read(),
                                 map_result[self.build_server_address(filename)].fd.read())

    def test_multiple_downloads_with_reports(self):
        """we deliver more than on download in parallel"""
        requests = [self.build_server_address("biggerfile"), self.build_server_address("simplefile")]
        report = CopyingMock()
        DownloadCenter(requests, self.callback, report=report)
        self.wait_for_callback(self.callback)

        self.assertEqual(report.call_count, 5)
        # ensure that first call only contains one file
        callback_args, callback_kwargs = report.call_args_list[0]
        map_result = callback_args[0]
        self.assertEqual(len(map_result), 1, str(map_result))
        # ensure that last call is what we expect
        result_dict = {}
        for filename in ("biggerfile", "simplefile"):
            file_size = getsize(join(self.server_dir, filename))
            result_dict[self.build_server_address(filename)] = {'size': file_size,
                                                                'current': file_size}
        self.assertEqual(report.call_args, call(result_dict))

    def test_404_url(self):
        """we return an error for a request including a 404 url"""
        request = self.build_server_address("does_not_exist")
        DownloadCenter([request], self.callback)
        self.wait_for_callback(self.callback)

        # no download means the file isn't in the result
        callback_args, callback_kwargs = self.callback.call_args
        result = callback_args[0][self.build_server_address("does_not_exist")]
        self.assertIn("404", result.error)
        self.assertIn("File not found", result.error)
        self.assertIsNone(result.buffer)
        self.assertIsNone(result.fd)
        self.expect_warn_error = True

    def test_multiple_with_one_404_url(self):
        """we raise an error when we try to download 404 urls"""
        requests = [self.build_server_address("does_not_exist"), self.build_server_address("simplefile")]
        DownloadCenter(requests, self.callback)
        self.wait_for_callback(self.callback)

        # we should have the two content, one in error
        callback_args, callback_kwargs = self.callback.call_args
        map_result = callback_args[0]
        self.assertEqual(len(map_result), 2, str(map_result))
        self.assertIsNotNone(map_result[self.build_server_address("does_not_exist")].error)
        self.assertIsNotNone(map_result[self.build_server_address("simplefile")].fd)
        self.expect_warn_error = True

    def test_download_same_file_multiple_times(self):
        """we only do one download when the same file is requested more than once in the same request"""
        requests = [self.build_server_address("simplefile"), self.build_server_address("simplefile")]
        report = CopyingMock()
        DownloadCenter(requests, self.callback, report=report)
        self.wait_for_callback(self.callback)

        # ensure we only have one file downloaded and mapped back as a result)
        callback_args, callback_kwargs = self.callback.call_args
        map_result = callback_args[0]
        self.assertEqual(len(map_result), 1, str(map_result))
        # ensure we only downloaded one file (didn't send multiple parallel requests)
        self.assertEqual(report.call_count, 2)

    def test_in_memory_download(self):
        """we deliver download on memory objects"""
        filename = "simplefile"
        request = self.build_server_address(filename)
        DownloadCenter([request], self.callback, download=False)
        self.wait_for_callback(self.callback)

        result = self.callback.call_args[0][0][request]
        self.assertTrue(self.callback.called)
        self.assertEqual(self.callback.call_count, 1)
        with open(join(self.server_dir, filename), 'rb') as file_on_disk:
            self.assertEqual(file_on_disk.read(),
                             result.buffer.read())
        self.assertIsNone(result.fd)
        self.assertIsNone(result.error)

    def test_unsupported_protocol(self):
        """Raises an exception when trying to download for an unsupported protocol"""
        filename = "simplefile"
        request = self.build_server_address(filename).replace('http', 'ftp')
        DownloadCenter([request], self.callback, download=False)
        self.wait_for_callback(self.callback)

        result = self.callback.call_args[0][0][request]
        self.assertIn("Protocol not supported", result.error)
        self.assertIsNone(result.buffer)
        self.assertIsNone(result.fd)
        self.expect_warn_error = True

    def test_download_with_wrong_md5(self):
        """we raise an error if we don't have the correct md5sum"""
        filename = "simplefile"
        request = self.build_server_address(filename)
        DownloadCenter([(request, 'AAAAA')], self.callback)
        self.wait_for_callback(self.callback)

        result = self.callback.call_args[0][0][request]
        self.assertIn("Corrupted download", result.error)
        self.assertIsNone(result.buffer)
        self.assertIsNone(result.fd)
        self.expect_warn_error = True

    def test_download_with_no_size(self):
        """we deliver one successful download, even if size isn't provided. Progress returns -1 though"""
        filename = "simplefile-with-no-content-length"
        request = self.build_server_address(filename)
        report = CopyingMock()
        DownloadCenter([request], self.callback, report=report)
        self.wait_for_callback(self.callback)

        result = self.callback.call_args[0][0][request]
        self.assertTrue(self.callback.called)
        self.assertEqual(self.callback.call_count, 1)
        with open(join(self.server_dir, filename), 'rb') as file_on_disk:
            self.assertEqual(file_on_disk.read(),
                             result.fd.read())
        self.assertIsNone(result.buffer)
        self.assertIsNone(result.error)
        self.assertEqual(report.call_count, 2)
        self.assertEqual(report.call_args_list,
                         [call({self.build_server_address(filename): {'size': -1, 'current': 0}}),
                          call({self.build_server_address(filename): {'size': -1, 'current': 8192}})])


class TestDownloadCenterSecure(LoggedTestCase):
    """This will test the download center in secure mode by sending one or more download requests"""

    server = None

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.server_dir = join(get_data_dir(), "server-content")
        cls.server = LocalHttp(cls.server_dir, use_ssl="localhost.pem")

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls.server.stop()

    def setUp(self):
        super().setUp()
        self.callback = Mock()
        self.fd_to_close = []

    def tearDown(self):
        super().tearDown()
        for fd in self.fd_to_close:
            fd.close()

    def test_download(self):
        """we deliver one successful download under ssl with known cert"""
        filename = "simplefile"
        # The host name is important here, since we verify it, so request
        # the localhost address.
        request = TestDownloadCenter.build_server_address(self, filename, True)
        # prepare the cert and set it as the trusted system context
        os.environ['REQUESTS_CA_BUNDLE'] = join(get_data_dir(), 'localhost.pem')
        try:
            DownloadCenter([request], self.callback)
            TestDownloadCenter.wait_for_callback(self, self.callback)

            result = self.callback.call_args[0][0][request]
            self.assertTrue(self.callback.called)
            self.assertEqual(self.callback.call_count, 1)
            with open(os.path.join(self.server_dir, filename), 'rb') as file_on_disk:
                self.assertEqual(file_on_disk.read(),
                                 result.fd.read())
        finally:
            del os.environ['REQUESTS_CA_BUNDLE']

    def test_redirect_download(self):
        """we deliver one successful download after being redirected"""
        filename = "simplefile"
        # We add a suffix to make the server redirect us.
        request = TestDownloadCenter.build_server_address(self,
                                                          filename + "-redirect",
                                                          localhost=True)
        os.environ['REQUESTS_CA_BUNDLE'] = join(get_data_dir(), 'localhost.pem')
        try:
            DownloadCenter([request], self.callback)
            TestDownloadCenter.wait_for_callback(self, self.callback)

            result = self.callback.call_args[0][0][request]
            self.assertTrue(self.callback.called)
            self.assertEqual(self.callback.call_count, 1)
            with open(os.path.join(self.server_dir, filename), 'rb') as file_on_disk:
                self.assertEqual(file_on_disk.read(),
                                 result.fd.read())
            self.assertIsNone(result.buffer)
            self.assertIsNone(result.error)
        finally:
            del os.environ['REQUESTS_CA_BUNDLE']

    def test_with_invalid_certificate(self):
        """we error on invalid ssl certificate"""
        filename = "simplefile"
        request = TestDownloadCenter.build_server_address(self, filename)
        DownloadCenter([request], self.callback)
        TestDownloadCenter.wait_for_callback(self, self.callback)

        result = self.callback.call_args[0][0][request]
        self.assertIn("CERTIFICATE_VERIFY_FAILED", result.error)
        self.assertIsNone(result.buffer)
        self.assertIsNone(result.fd)
        self.expect_warn_error = True
