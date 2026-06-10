from __future__ import annotations

import unittest

from desktop.models.operation_state import menu_action_enabled


class MenuActionEnabledTests(unittest.TestCase):
    def test_service_actions_require_installed_service(self) -> None:
        actions = menu_action_enabled({"serviceState": "NOT_INSTALLED", "startupRegistered": False})

        self.assertTrue(actions["install_service"])
        self.assertFalse(actions["start_service"])
        self.assertFalse(actions["stop_service"])

    def test_running_service_disables_install_and_start(self) -> None:
        actions = menu_action_enabled({"serviceState": "RUNNING", "startupRegistered": False})

        self.assertFalse(actions["install_service"])
        self.assertFalse(actions["start_service"])
        self.assertTrue(actions["stop_service"])

    def test_stopped_service_can_start_but_not_stop(self) -> None:
        actions = menu_action_enabled({"serviceState": "STOPPED", "startupRegistered": False})

        self.assertFalse(actions["install_service"])
        self.assertTrue(actions["start_service"])
        self.assertFalse(actions["stop_service"])

    def test_startup_actions_are_mutually_exclusive(self) -> None:
        registered = menu_action_enabled({"serviceState": "RUNNING", "startupRegistered": True})
        unregistered = menu_action_enabled({"serviceState": "RUNNING", "startupRegistered": False})

        self.assertFalse(registered["register_startup"])
        self.assertTrue(registered["unregister_startup"])
        self.assertTrue(unregistered["register_startup"])
        self.assertFalse(unregistered["unregister_startup"])


if __name__ == "__main__":
    unittest.main()
