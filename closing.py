"""Check unsaved edits without blocking the native window's closing event."""
from queue import Empty, Queue
from threading import Lock, Thread


class CloseGuard:
    def __init__(self, window, timeout=3):
        self.window = window
        self.timeout = timeout
        self._lock = Lock()
        self._checking = False
        self._approved = False

    def on_closing(self):
        # WinForms calls this on its UI thread. Never evaluate JS, show a
        # marshalled dialog, or join a worker while this callback is running.
        with self._lock:
            if self._approved:
                return True
            if not self._checking:
                self._checking = True
                Thread(target=self._check, daemon=True, name="turbotodos-close").start()
        return False

    def _check(self):
        replies = Queue(maxsize=1)

        def evaluate():
            try:
                dirty = self.window.evaluate_js(
                    "Boolean(window.turboHasUnsavedChanges && window.turboHasUnsavedChanges())"
                )
                replies.put((True, dirty))
            except Exception:
                replies.put((False, None))

        Thread(target=evaluate, daemon=True, name="turbotodos-close-state").start()
        try:
            try:
                known, dirty = replies.get(timeout=self.timeout)
            except Empty:
                known, dirty = False, None
            if not known:
                approved = self.window.create_confirmation_dialog(
                    "Close TurboTodos", "Unable to check save status. Close anyway?"
                )
            elif dirty:
                approved = self.window.create_confirmation_dialog(
                    "Unsaved changes", "Some changes have not been saved. Close anyway?"
                )
            else:
                approved = True
            if approved:
                with self._lock:
                    self._approved = True
                self.window.destroy()
        finally:
            with self._lock:
                self._checking = False
