from urllib.error import HTTPError
from urllib.request import Request, urlopen
import unittest

from server.tests.test_admin_software_http import (
    customer_payload,
    prepare_owner,
    request_json,
    running_server,
)


def request_bytes(base, path, *, method="GET", body=None, headers=None):
    request = Request(base + path, data=body, method=method, headers=headers or {})
    try:
        response = urlopen(request, timeout=5)
        return response.status, response.headers, response.read()
    except HTTPError as error:
        return error.code, error.headers, error.read()


class CustomerReceiptPhotoHttpTests(unittest.TestCase):
    def test_customer_photo_upload_and_read_are_admin_protected(self):
        with running_server() as (server, base):
            _, owner_headers = prepare_owner(server, base)
            status, created = request_json(base, "/api/admin/customers", method="POST", body=customer_payload(), headers=owner_headers)
            self.assertEqual(status, 201)
            customer_id = created["customer"]["id"]
            photo_path = f"/api/admin/customers/{customer_id}/photo"
            status, _, _ = request_bytes(base, photo_path)
            self.assertEqual(status, 401)

            jpeg = b"\xff\xd8\xff\xe0gravity-test-photo\xff\xd9"
            upload_headers = dict(owner_headers)
            upload_headers["Content-Type"] = "image/jpeg"
            status, _, body = request_bytes(base, photo_path, method="POST", body=jpeg, headers=upload_headers)
            self.assertEqual(status, 200, body)

            read_headers = {"Cookie": owner_headers["Cookie"]}
            status, headers, body = request_bytes(base, photo_path, headers=read_headers)
            self.assertEqual(status, 200)
            self.assertEqual(headers.get_content_type(), "image/jpeg")
            self.assertEqual(body, jpeg)

    def test_verified_membership_prices_are_available_to_admin(self):
        with running_server() as (server, base):
            _, owner_headers = prepare_owner(server, base)
            status, payload = request_json(base, "/api/admin/membership/plans", headers=owner_headers)
            self.assertEqual(status, 200)
            plans = [(item["name"], item["pricePaise"], item["durationMonths"]) for item in payload["plans"]]
            self.assertEqual(plans, [("1 Month", 120000, 1), ("3 Months", 300000, 3), ("1 Year", 1000000, 12)])


if __name__ == "__main__":
    unittest.main()
