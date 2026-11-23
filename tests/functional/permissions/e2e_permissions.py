from resdk.exceptions import ResolweServerError

from ..base import USER_EMAIL, BaseResdkFunctionalTest


class TestPermissions(BaseResdkFunctionalTest):
    def setUp(self):
        super().setUp()

        self.test_collection = self.res.collection.create(name="Test collection")
        self.collection2 = None

    def tearDown(self):
        super().tearDown()

        self.test_collection.delete(force=True)
        if self.collection2:
            self.collection2.delete(force=True)

    def test_permissions(self):
        # User doesn't have the permission to view the collection.
        with self.assertRaises(LookupError):
            self.user_res.collection.get(self.test_collection.id)

        self.test_collection.permissions.set_user(USER_EMAIL, "view")

        # User can see the collection, but cannot edit it.
        user_collection = self.user_res.collection.get(self.test_collection.id)
        user_collection.name = "Different name"
        with self.assertRaises(ResolweServerError):
            user_collection.save()

        self.test_collection.permissions.set_user(USER_EMAIL, "edit")

        # User can edit the collection.
        user_collection.name = "Different name"
        user_collection.save()

        self.test_collection.permissions.set_user(USER_EMAIL, "view")

        # Edit permission is removed again.
        user_collection.name = "Different name 2"
        with self.assertRaises(ResolweServerError):
            user_collection.save()

    def test_get_holders_with_perm(self):
        self.test_collection.permissions.set_user(USER_EMAIL, "edit")
        self.test_collection.permissions.set_public("view")
        # The admin has no full name, so the server names it by its username,
        # which is the one the account was created with, not its email.
        admin_name = self.res.user.get(current_only=True).username

        self.assertEqual(len(self.test_collection.permissions.owners), 1)
        self.assertEqual(
            self.test_collection.permissions.owners[0].get_name(), admin_name
        )

        self.assertEqual(len(self.test_collection.permissions.editors), 2)
        self.assertEqual(
            self.test_collection.permissions.editors[0].get_name(), admin_name
        )
        self.assertEqual(
            self.test_collection.permissions.editors[1].get_name(), "E2E Tester"
        )

        self.assertEqual(len(self.test_collection.permissions.viewers), 3)
        self.assertEqual(
            self.test_collection.permissions.viewers[0].first_name, admin_name
        )

        self.assertEqual(
            self.test_collection.permissions.viewers[1].first_name, "E2E Tester"
        )
        self.assertEqual(self.test_collection.permissions.viewers[2].username, "public")

    def test_copy_from(self):
        # Create collection with only user permissions
        self.collection2 = self.user_res.collection.create(name="Test collection 2")
        self.collection2.permissions.fetch()
        self.assertEqual(len(self.collection2.permissions._permissions), 1)

        self.test_collection.permissions.set_public("view")
        self.collection2.permissions.copy_from(self.test_collection)
        self.assertEqual(len(self.collection2.permissions._permissions), 3)
