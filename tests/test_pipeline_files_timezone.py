"""Regression tests for timezone handling in FilesPipeline stores.

See issue #7: S3FilesStore and GCSFilesStore converted timezone-aware UTC
datetimes with time.mktime(), which interprets the broken-down time as
local time, shifting last_modified by the local UTC offset. FTPFilesStore
parsed the MDTM response directly as a float instead of as a UTC datetime.

These tests force a non-UTC local timezone so that the bug would be
exposed even when the test runner's default timezone happens to be UTC.
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from unittest import mock

import pytest

from scrapy.pipelines.files import FTPFilesStore, GCSFilesStore, S3FilesStore

requires_tzset = pytest.mark.skipif(
    not hasattr(time, "tzset"), reason="time.tzset() is not available on this platform"
)


@pytest.fixture
def non_utc_local_timezone():
    original_tz = os.environ.get("TZ")
    os.environ["TZ"] = "America/New_York"
    time.tzset()
    try:
        yield
    finally:
        if original_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_tz
        time.tzset()


@requires_tzset
def test_s3_onsuccess_last_modified_is_utc(non_utc_local_timezone) -> None:
    last_modified = datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    boto_key = {"ETag": '"abc123"', "LastModified": last_modified}

    result = S3FilesStore._onsuccess(boto_key)

    assert result["checksum"] == "abc123"
    assert result["last_modified"] == last_modified.timestamp()


@requires_tzset
def test_gcs_onsuccess_last_modified_is_utc(non_utc_local_timezone) -> None:
    updated = datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc)
    blob = mock.Mock()
    blob.updated = updated
    blob.md5_hash = "YWJjMTIz"

    result = GCSFilesStore._onsuccess(blob)

    assert result["last_modified"] == updated.timestamp()


@requires_tzset
def test_ftp_stat_file_parses_mdtm_as_utc(non_utc_local_timezone) -> None:
    store = FTPFilesStore.__new__(FTPFilesStore)
    store.host = "example.com"
    store.port = 21
    store.username = "user"
    store.password = "pass"
    store.basedir = ""
    store.USE_ACTIVE_MODE = False

    ftp_mock = mock.MagicMock()
    ftp_mock.__enter__.return_value = ftp_mock
    ftp_mock.voidcmd.return_value = "213 20230615103000"

    with mock.patch("scrapy.pipelines.files.FTP", return_value=ftp_mock):
        stat_info = store._stat_file("some/path")

    expected = datetime(2023, 6, 15, 10, 30, 0, tzinfo=timezone.utc).timestamp()
    assert stat_info["last_modified"] == expected
