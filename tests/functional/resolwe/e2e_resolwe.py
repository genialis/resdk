import resdk

from ..base import BaseResdkFunctionalTest


class TestRun(BaseResdkFunctionalTest):
    def setUp(self):
        super().setUp()
        self.collection = self.res.collection.create(name="Test collection")
        self.data = None

    def tearDown(self):
        # self.data is deleted along with collection
        self.collection.delete(force=True)

    def test_run(self):
        self.data = self.res.run(
            slug="test-sleep-progress",
            input={"t": 1},
            descriptor_schema="reads",
            descriptor={"description": "Lorem ipsum ..."},
            collection=self.collection,
            data_name="Test run data",
        )

        self.assertTrue(isinstance(self.data, resdk.resources.Data))
        self.assertEqual(self.data.process.slug, "test-sleep-progress")
        self.assertEqual(self.data.input, {"t": 1})
        self.assertEqual(self.data.descriptor_schema.slug, "reads")

        self.assertEqual(self.data.descriptor["description"], "Lorem ipsum ...")

        self.assertEqual(self.data.collection, self.collection)
        self.assertEqual(self.data.name, "Test run data")


class TestDataUsage(BaseResdkFunctionalTest):
    expected_fields = {
        "user_id",
        "username",
        "full_name",
        "data_size",
        "data_size_normalized",
        "data_count",
        "data_count_normalized",
        "collection_count",
        "collection_count_normalized",
        "sample_count",
        "sample_count_normalized",
    }

    def setUp(self):
        super().setUp()
        self.data1 = self.res.run(slug="test-sleep-progress")

        # Normal user needs to get permissions to run this process
        process = self.res.process.get(slug="test-sleep-progress")
        process.permissions.set_public("view")
        self.data2 = self.user_res.run(slug="test-sleep-progress")

    def tearDown(self):
        self.data1.delete(force=True)
        self.data2.delete(force=True)

    def test_normal_user(self):
        usage_info = self.user_res.data_usage()
        self.assertEqual(len(usage_info), 1)
        self.assertEqual(set(usage_info[0].keys()), self.expected_fields)

    def test_admin_user(self):
        usage_info = self.res.data_usage()
        self.assertEqual(len(usage_info), 2)
        self.assertEqual(set(usage_info[0].keys()), self.expected_fields)

    def test_ordering(self):
        usage_info = self.res.data_usage(ordering=["-username"])
        self.assertEqual(len(usage_info), 2)
        # The usernames are the ones the accounts were created with, not the
        # emails, so read them from the server.
        usernames = [
            connection.user.get(current_only=True).username
            for connection in (self.res, self.user_res)
        ]
        self.assertEqual(
            [usage["username"] for usage in usage_info],
            sorted(usernames, reverse=True),
        )
