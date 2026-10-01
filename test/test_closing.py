import threading
import time
import unittest
from unittest.mock import Mock
from closing import CloseGuard


class CloseTests(unittest.TestCase):
    def test_close_callback_returns_before_javascript_finishes(self):
        release=threading.Event();destroyed=threading.Event()
        window=Mock();window.evaluate_js.side_effect=lambda script:release.wait(1) and False
        window.destroy.side_effect=destroyed.set
        guard=CloseGuard(window)
        self.assertFalse(guard.on_closing())
        self.assertFalse(guard.on_closing())
        self.assertFalse(destroyed.is_set())
        release.set();self.assertTrue(destroyed.wait(1))
        self.assertTrue(guard.on_closing())
        window.create_confirmation_dialog.assert_not_called()
        window.evaluate_js.assert_called_once()

    def test_dirty_cancel_then_retry(self):
        window=Mock();window.evaluate_js.return_value=True
        window.create_confirmation_dialog.side_effect=[False,True]
        guard=CloseGuard(window);guard._check()
        window.destroy.assert_not_called()
        guard._check();window.destroy.assert_called_once()
        self.assertTrue(guard.on_closing())

    def test_unresponsive_engine_has_bounded_fallback(self):
        release=threading.Event();window=Mock()
        window.evaluate_js.side_effect=lambda script:release.wait(1)
        window.create_confirmation_dialog.return_value=False
        guard=CloseGuard(window,timeout=.02)
        start=time.monotonic();guard._check()
        self.assertLess(time.monotonic()-start,.5)
        self.assertIn('Unable to check',window.create_confirmation_dialog.call_args.args[1])
        window.destroy.assert_not_called();release.set()

    def test_engine_error_still_allows_confirmed_close(self):
        window=Mock();window.evaluate_js.side_effect=RuntimeError('engine unavailable')
        window.create_confirmation_dialog.return_value=True
        CloseGuard(window)._check();window.destroy.assert_called_once()


if __name__=='__main__':unittest.main()
