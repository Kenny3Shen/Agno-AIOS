from __future__ import annotations

import inspect
import unittest

from api.config import Settings


class BootstrapAdminTest(unittest.TestCase):
    def test_bootstrap_admin_is_disabled_by_default(self) -> None:
        settings = Settings.model_validate({})

        self.assertEqual(settings.bootstrap_admin_email, "")
        self.assertEqual(settings.bootstrap_admin_password.get_secret_value(), "")

    def test_bootstrap_admin_env_aliases_are_supported(self) -> None:
        settings = Settings.model_validate(
            {
                "AGNO_BOOTSTRAP_ADMIN_EMAIL": "admin@example.com",
                "AGNO_BOOTSTRAP_ADMIN_PASSWORD": "AdminPass123!",
            }
        )

        self.assertEqual(settings.bootstrap_admin_email, "admin@example.com")
        self.assertEqual(
            settings.bootstrap_admin_password.get_secret_value(),
            "AdminPass123!",
        )

    def test_bootstrap_admin_upserts_superuser_admin(self) -> None:
        from api.auth import database

        source = inspect.getsource(database.bootstrap_admin_user)

        self.assertIn('ON CONFLICT (email) DO UPDATE', source)
        self.assertIn("is_superuser = true", source)
        self.assertIn("role = 'admin'", source)
        self.assertIn("PasswordHelper", source)


if __name__ == "__main__":
    unittest.main()
