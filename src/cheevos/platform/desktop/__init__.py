"""Desktop (macOS/Linux) shim that runs PyUI screens in a window or headless.

Development only: excluded from the device package. Modules here other than ``__main__`` and
``script`` import PyUI at the top level, so import them only after
:func:`cheevos.ui.pyui.bootstrap.add_pyui_to_path` has run.
"""
