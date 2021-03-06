# -*- coding: utf-8 -*-
from django.conf import settings

from zerver.lib.test_classes import ZulipTestCase, UploadSerializeMixin
from zerver.lib.test_helpers import use_s3_backend, override_settings

from io import StringIO
from boto.s3.connection import S3Connection
import ujson
import urllib
import base64

class ThumbnailTest(ZulipTestCase):

    @use_s3_backend
    def test_s3_source_type(self) -> None:
        def get_file_path_urlpart(uri: str, size: str='') -> str:
            base = '/user_uploads/'
            url_in_result = 'smart/filters:no_upscale()/%s/source_type/s3'
            if size:
                url_in_result = '/%s/%s' % (size, url_in_result)
            upload_file_path = uri[len(base):]
            hex_uri = base64.urlsafe_b64encode(upload_file_path.encode()).decode('utf-8')
            return url_in_result % (hex_uri)

        conn = S3Connection(settings.S3_KEY, settings.S3_SECRET_KEY)
        conn.create_bucket(settings.S3_AUTH_UPLOADS_BUCKET)

        self.login(self.example_email("hamlet"))
        fp = StringIO("zulip!")
        fp.name = "zulip.jpeg"

        result = self.client_post("/json/user_uploads", {'file': fp})
        self.assert_json_success(result)
        json = ujson.loads(result.content)
        self.assertIn("uri", json)
        uri = json["uri"]
        base = '/user_uploads/'
        self.assertEqual(base, uri[:len(base)])

        quoted_uri = urllib.parse.quote(uri[1:], safe='')

        # Test original image size.
        result = self.client_get("/thumbnail?url=%s&size=original" % (quoted_uri))
        self.assertEqual(result.status_code, 302, result)
        expected_part_url = get_file_path_urlpart(uri)
        self.assertIn(expected_part_url, result.url)

        # Test thumbnail size.
        result = self.client_get("/thumbnail?url=%s&size=thumbnail" % (quoted_uri))
        self.assertEqual(result.status_code, 302, result)
        expected_part_url = get_file_path_urlpart(uri, '0x100')
        self.assertIn(expected_part_url, result.url)

        # Tests the /api/v1/thumbnail api endpoint with standard API auth
        self.logout()
        result = self.api_get(
            self.example_email("hamlet"),
            '/thumbnail?url=%s&size=original' %
            (quoted_uri,))
        self.assertEqual(result.status_code, 302, result)
        expected_part_url = get_file_path_urlpart(uri)
        self.assertIn(expected_part_url, result.url)

        # Test with another user trying to access image using thumbor.
        self.login(self.example_email("iago"))
        result = self.client_get("/thumbnail?url=%s&size=original" % (quoted_uri))
        self.assertEqual(result.status_code, 403, result)
        self.assert_in_response("You are not authorized to view this file.", result)

    def test_external_source_type(self) -> None:
        def run_test_with_image_url(image_url: str) -> None:
            # Test original image size.
            self.login(self.example_email("hamlet"))
            quoted_url = urllib.parse.quote(image_url, safe='')
            encoded_url = base64.urlsafe_b64encode(image_url.encode()).decode('utf-8')
            result = self.client_get("/thumbnail?url=%s&size=original" % (quoted_url))
            self.assertEqual(result.status_code, 302, result)
            expected_part_url = '/smart/filters:no_upscale()/' + encoded_url + '/source_type/external'
            self.assertIn(expected_part_url, result.url)

            # Test thumbnail size.
            result = self.client_get("/thumbnail?url=%s&size=thumbnail" % (quoted_url))
            self.assertEqual(result.status_code, 302, result)
            expected_part_url = '/0x100/smart/filters:no_upscale()/' + encoded_url + '/source_type/external'
            self.assertIn(expected_part_url, result.url)

            # Test api endpoint with standard API authentication.
            self.logout()
            user_profile = self.example_user("hamlet")
            result = self.api_get(user_profile.email,
                                  "/thumbnail?url=%s&size=thumbnail" % (quoted_url,))
            self.assertEqual(result.status_code, 302, result)
            expected_part_url = '/0x100/smart/filters:no_upscale()/' + encoded_url + '/source_type/external'
            self.assertIn(expected_part_url, result.url)

            # Test api endpoint with legacy API authentication.
            user_profile = self.example_user("hamlet")
            result = self.client_get("/thumbnail?url=%s&size=thumbnail&api_key=%s" % (
                quoted_url, user_profile.api_key))
            self.assertEqual(result.status_code, 302, result)
            expected_part_url = '/0x100/smart/filters:no_upscale()/' + encoded_url + '/source_type/external'
            self.assertIn(expected_part_url, result.url)

            # Test a second logged-in user; they should also be able to access it
            user_profile = self.example_user("iago")
            result = self.client_get("/thumbnail?url=%s&size=thumbnail&api_key=%s" % (quoted_url, user_profile.api_key))
            self.assertEqual(result.status_code, 302, result)
            expected_part_url = '/0x100/smart/filters:no_upscale()/' + encoded_url + '/source_type/external'
            self.assertIn(expected_part_url, result.url)

            # Test with another user trying to access image using thumbor.
            # File should be always accessible to user in case of external source
            self.login(self.example_email("iago"))
            result = self.client_get("/thumbnail?url=%s&size=original" % (quoted_url))
            self.assertEqual(result.status_code, 302, result)
            expected_part_url = '/smart/filters:no_upscale()/' + encoded_url + '/source_type/external'
            self.assertIn(expected_part_url, result.url)

        image_url = 'https://images.foobar.com/12345'
        run_test_with_image_url(image_url)

        image_url = 'http://images.foobar.com/12345'
        run_test_with_image_url(image_url)

    def test_local_file_type(self) -> None:
        def get_file_path_urlpart(uri: str, size: str='') -> str:
            base = '/user_uploads/'
            url_in_result = 'smart/filters:no_upscale()/%s/source_type/local_file'
            if size:
                url_in_result = '/%s/%s' % (size, url_in_result)
            upload_file_path = uri[len(base):]
            hex_uri = base64.urlsafe_b64encode(upload_file_path.encode()).decode('utf-8')
            return url_in_result % (hex_uri)

        self.login(self.example_email("hamlet"))
        fp = StringIO("zulip!")
        fp.name = "zulip.jpeg"

        result = self.client_post("/json/user_uploads", {'file': fp})
        self.assert_json_success(result)
        json = ujson.loads(result.content)
        self.assertIn("uri", json)
        uri = json["uri"]
        base = '/user_uploads/'
        self.assertEqual(base, uri[:len(base)])

        # Test original image size.
        # We remove the forward slash infront of the `/user_uploads/` to match
        # bugdown behaviour.
        quoted_uri = urllib.parse.quote(uri[1:], safe='')
        result = self.client_get("/thumbnail?url=%s&size=original" % (quoted_uri))
        self.assertEqual(result.status_code, 302, result)
        expected_part_url = get_file_path_urlpart(uri)
        self.assertIn(expected_part_url, result.url)

        # Test thumbnail size.
        result = self.client_get("/thumbnail?url=%s&size=thumbnail" % (quoted_uri))
        self.assertEqual(result.status_code, 302, result)
        expected_part_url = get_file_path_urlpart(uri, '0x100')
        self.assertIn(expected_part_url, result.url)

        # Test with a unicode filename.
        fp = StringIO("zulip!")
        fp.name = "μένει.jpg"

        result = self.client_post("/json/user_uploads", {'file': fp})
        self.assert_json_success(result)
        json = ujson.loads(result.content)
        self.assertIn("uri", json)
        uri = json["uri"]

        # We remove the forward slash infront of the `/user_uploads/` to match
        # bugdown behaviour.
        quoted_uri = urllib.parse.quote(uri[1:], safe='')
        result = self.client_get("/thumbnail?url=%s&size=original" % (quoted_uri))
        self.assertEqual(result.status_code, 302, result)
        expected_part_url = get_file_path_urlpart(uri)
        self.assertIn(expected_part_url, result.url)
        self.logout()

        # Tests the /api/v1/thumbnail api endpoint with HTTP basic auth.
        user_profile = self.example_user("hamlet")
        result = self.api_get(
            self.example_email("hamlet"),
            '/thumbnail?url=%s&size=original' %
            (quoted_uri,))
        self.assertEqual(result.status_code, 302, result)
        expected_part_url = get_file_path_urlpart(uri)
        self.assertIn(expected_part_url, result.url)

        # Tests the /api/v1/thumbnail api endpoint with ?api_key
        # auth.
        user_profile = self.example_user("hamlet")
        result = self.client_get(
            '/thumbnail?url=%s&size=original&api_key=%s' %
            (quoted_uri, user_profile.api_key))
        self.assertEqual(result.status_code, 302, result)
        expected_part_url = get_file_path_urlpart(uri)
        self.assertIn(expected_part_url, result.url)

        # Test with another user trying to access image using thumbor.
        self.login(self.example_email("iago"))
        result = self.client_get("/thumbnail?url=%s&size=original" % (quoted_uri))
        self.assertEqual(result.status_code, 403, result)
        self.assert_in_response("You are not authorized to view this file.", result)

    @override_settings(THUMBOR_URL='127.0.0.1:9995')
    def test_with_static_files(self) -> None:
        self.login(self.example_email("hamlet"))
        uri = '/static/images/cute/turtle.png'
        quoted_uri = urllib.parse.quote(uri[1:], safe='')
        result = self.client_get("/thumbnail?url=%s&size=original" % (quoted_uri))
        self.assertEqual(result.status_code, 302, result)
        self.assertEqual(uri, result.url)

    def test_with_thumbor_disabled(self) -> None:
        self.login(self.example_email("hamlet"))
        fp = StringIO("zulip!")
        fp.name = "zulip.jpeg"

        result = self.client_post("/json/user_uploads", {'file': fp})
        self.assert_json_success(result)
        json = ujson.loads(result.content)
        self.assertIn("uri", json)
        uri = json["uri"]
        base = '/user_uploads/'
        self.assertEqual(base, uri[:len(base)])

        quoted_uri = urllib.parse.quote(uri[1:], safe='')

        with self.settings(THUMBOR_URL=''):
            result = self.client_get("/thumbnail?url=%s&size=original" % (quoted_uri))
        self.assertEqual(result.status_code, 302, result)
        self.assertEqual(uri, result.url)

        uri = 'https://www.google.com/images/srpr/logo4w.png'
        quoted_uri = urllib.parse.quote(uri, safe='')
        with self.settings(THUMBOR_URL=''):
            result = self.client_get("/thumbnail?url=%s&size=original" % (quoted_uri))
        self.assertEqual(result.status_code, 302, result)
        self.assertEqual(uri, result.url)

        uri = 'http://www.google.com/images/srpr/logo4w.png'
        quoted_uri = urllib.parse.quote(uri, safe='')
        with self.settings(THUMBOR_URL=''):
            result = self.client_get("/thumbnail?url=%s&size=original" % (quoted_uri))
        self.assertEqual(result.status_code, 302, result)
        base = 'https://external-content.zulipcdn.net/7b6552b60c635e41e8f6daeb36d88afc4eabde79/687474703a2f2f7777772e676f6f676c652e636f6d2f696d616765732f737270722f6c6f676f34772e706e67'
        self.assertEqual(base, result.url)

    def test_with_different_THUMBOR_URL(self) -> None:
        self.login(self.example_email("hamlet"))
        fp = StringIO("zulip!")
        fp.name = "zulip.jpeg"

        result = self.client_post("/json/user_uploads", {'file': fp})
        self.assert_json_success(result)
        json = ujson.loads(result.content)
        self.assertIn("uri", json)
        uri = json["uri"]
        base = '/user_uploads/'
        self.assertEqual(base, uri[:len(base)])

        quoted_uri = urllib.parse.quote(uri[1:], safe='')
        hex_uri = base64.urlsafe_b64encode(uri[len('/user_uploads/'):].encode()).decode('utf-8')
        with self.settings(THUMBOR_URL='http://test-thumborhost.com'):
            result = self.client_get("/thumbnail?url=%s&size=original" % (quoted_uri))
        self.assertEqual(result.status_code, 302, result)
        base = 'http://test-thumborhost.com/'
        self.assertEqual(base, result.url[:len(base)])
        expected_part_url = '/smart/filters:no_upscale()/' + hex_uri + '/source_type/local_file'
        self.assertIn(expected_part_url, result.url)

    def test_with_different_sizes(self) -> None:
        def get_file_path_urlpart(uri: str, size: str='') -> str:
            base = '/user_uploads/'
            url_in_result = 'smart/filters:no_upscale()/%s/source_type/local_file'
            if size:
                url_in_result = '/%s/%s' % (size, url_in_result)
            upload_file_path = uri[len(base):]
            hex_uri = base64.urlsafe_b64encode(upload_file_path.encode()).decode('utf-8')
            return url_in_result % (hex_uri)

        self.login(self.example_email("hamlet"))
        fp = StringIO("zulip!")
        fp.name = "zulip.jpeg"

        result = self.client_post("/json/user_uploads", {'file': fp})
        self.assert_json_success(result)
        json = ujson.loads(result.content)
        self.assertIn("uri", json)
        uri = json["uri"]
        base = '/user_uploads/'
        self.assertEqual(base, uri[:len(base)])

        # Test with size supplied as a query parameter.
        # size=thumbnail should return a 0x100 sized image.
        # size=original should return the original resolution image.
        quoted_uri = urllib.parse.quote(uri[1:], safe='')
        result = self.client_get("/thumbnail?url=%s&size=thumbnail" % (quoted_uri))
        self.assertEqual(result.status_code, 302, result)
        expected_part_url = get_file_path_urlpart(uri, '0x100')
        self.assertIn(expected_part_url, result.url)

        result = self.client_get("/thumbnail?url=%s&size=original" % (quoted_uri))
        self.assertEqual(result.status_code, 302, result)
        expected_part_url = get_file_path_urlpart(uri)
        self.assertIn(expected_part_url, result.url)

        # Test with size supplied as a query parameter where size is anything
        # else than original or thumbnail. Result should be an error message.
        result = self.client_get("/thumbnail?url=%s&size=480x360" % (quoted_uri))
        self.assertEqual(result.status_code, 403, result)
        self.assert_in_response("Invalid size.", result)

        # Test with no size param supplied. In this case as well we show an
        # error message.
        result = self.client_get("/thumbnail?url=%s" % (quoted_uri))
        self.assertEqual(result.status_code, 400, "Missing 'size' argument")
