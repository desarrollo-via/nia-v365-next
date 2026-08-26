import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from bitrix_connector.r1_post_write_close_host_binding import (
    _close_mounted_session_once,
    build_r1_post_write_persistent_host_executor,
)
from bitrix_connector.r1_post_write_close_host_executor import (
    R1PostWritePersistentHostExecutor,
)


class HostBindingTests(unittest.IsolatedAsyncioTestCase):
    def test_product_construction_is_inert(self):
        executor = build_r1_post_write_persistent_host_executor()
        self.assertIs(type(executor), R1PostWritePersistentHostExecutor)

    async def test_exact_dormant_absence_is_already_session_closed(self):
        module = SimpleNamespace(event_scoped_r1_mount=SimpleNamespace(
            owner=None, state="DORMANT", requested=False, enabled=False
        ))
        with patch.dict(sys.modules, {"bitrix_connector.router": module}):
            self.assertTrue(await _close_mounted_session_once())

    async def test_unavailable_absence_is_not_claimed_closed(self):
        module = SimpleNamespace(event_scoped_r1_mount=SimpleNamespace(
            owner=None, state="UNAVAILABLE", requested=True, enabled=False
        ))
        with patch.dict(sys.modules, {"bitrix_connector.router": module}):
            self.assertFalse(await _close_mounted_session_once())


if __name__ == "__main__":
    unittest.main()
