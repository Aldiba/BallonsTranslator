"""
ProjectManager: manages multiple ProjImgTrans instances for multi-project tab support.
ProjectProxy: transparent proxy that routes attribute access to the active project.
"""

import os.path as osp
from typing import Dict, Optional

from qtpy.QtCore import QObject, Signal

from utils.proj_imgtrans import ProjImgTrans
from utils.logger import logger as LOGGER


class ProjectProxy:
    """
    Transparent proxy object that always delegates attribute access
    to the currently active project in ProjectManager.

    This allows all subsystems (Canvas, SceneTextManager, ModuleManager, etc.)
    to hold a single immutable reference that automatically follows
    project switches -- zero downstream code changes needed.

    Usage:
        manager = ProjectManager()
        imgtrans_proj = ProjectProxy(manager)

        # All access routes to manager.active:
        imgtrans_proj.pages           -> manager.active.pages
        imgtrans_proj.current_img     -> manager.active.current_img
        imgtrans_proj.set_current_img(name) -> manager.active.set_current_img(name)
    """

    def __init__(self, manager: 'ProjectManager'):
        object.__setattr__(self, '_manager', manager)

    def __getattr__(self, name: str):
        manager = object.__getattribute__(self, '_manager')
        active = manager.active
        if active is None:
            raise AttributeError(
                f"No active project. Cannot access '{name}'.")
        return getattr(active, name)

    def __setattr__(self, name: str, value):
        if name == '_manager':
            object.__setattr__(self, name, value)
        else:
            manager = object.__getattribute__(self, '_manager')
            active = manager.active
            if active is None:
                raise AttributeError(
                    f"No active project. Cannot set '{name}'.")
            setattr(active, name, value)


class ProjectManager(QObject):
    """
    Manages multiple ProjImgTrans instances.

    Signals:
        active_changed(): emitted when the active project switches
        project_opened(str): emitted with proj_path when a new project is opened
        project_closed(str): emitted with proj_path when a project is closed
    """

    active_changed = Signal()
    project_opened = Signal(str)
    project_closed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._projects: Dict[str, ProjImgTrans] = {}
        self._active_key: Optional[str] = None
        self._project_names: Dict[str, str] = {}

    # ----- Properties -----
    @property
    def active(self) -> Optional[ProjImgTrans]:
        """Return the currently active ProjImgTrans instance, or None."""
        return self._projects.get(self._active_key) if self._active_key else None

    @property
    def active_key(self) -> Optional[str]:
        """Return the key of the currently active project."""
        return self._active_key

    @property
    def count(self) -> int:
        return len(self._projects)

    # ----- Project lifecycle -----
    def _make_key(self, path: str) -> str:
        """Normalize a path into a canonical key."""
        return osp.normpath(osp.abspath(path))

    def open(self, path: str) -> ProjImgTrans:
        """
        Open a project and make it the active one.
        If the project is already open, just switch to it.

        Args:
            path: directory path or json file path

        Returns:
            The ProjImgTrans instance (newly created or existing).
        """
        # --- Check if already open (robust: handles dir ↔ json path mismatch) ---
        existing = self.project_for_key(path)
        if existing is not None:
            for stored_key, proj in self._projects.items():
                if proj is existing:
                    LOGGER.info(f'Project already open: {stored_key}')
                    if self._active_key != stored_key:
                        self.switch_to(stored_key)
                    return existing

        # --- Load the project ---
        proj = ProjImgTrans()
        if osp.isdir(path):
            proj.load(path)
        else:
            proj.load_from_json(path)

        if proj.is_empty:
            LOGGER.warning(f'Opened project has no pages: {path}')

        # --- Determine canonical key ---
        actual_path = proj.proj_path if proj.proj_path else proj.directory
        if actual_path:
            actual_key = self._make_key(actual_path)
        else:
            actual_key = self._make_key(path)

        # Check again with the actual key (in case the loaded project's paths
        # resolve to a different key than the input path)
        if actual_key in self._projects:
            existing = self._projects[actual_key]
            LOGGER.info(f'Project loaded but already exists at key: {actual_key}')
            self.switch_to(actual_key)
            return existing

        # --- Store the project ---
        self._projects[actual_key] = proj
        self._project_names[actual_key] = osp.basename(
            proj.directory) if proj.directory else osp.basename(path)

        was_active = self._active_key
        self._active_key = actual_key

        LOGGER.info(
            f'Opened project: {actual_key} (total: {len(self._projects)})')
        self.project_opened.emit(actual_key)
        if was_active != actual_key:
            self.active_changed.emit()
        return proj

    def switch_to(self, key: str):
        """Switch the active project to the one identified by `key`."""
        # First try exact match (for special keys like __placeholder__)
        if key in self._projects:
            actual_key = key
        else:
            actual_key = self._make_key(key)
            if actual_key not in self._projects:
                for stored_key in self._projects:
                    if self._make_key(stored_key) == actual_key:
                        actual_key = stored_key
                        break
                else:
                    LOGGER.error(f'Project not found: {key}')
                    return

        if self._active_key == actual_key:
            return

        self._active_key = actual_key
        LOGGER.info(f'Switched to project: {actual_key}')
        self.active_changed.emit()

    def close(self, key: str) -> bool:
        """
        Close and remove a project.

        Returns True if the project was found and closed.
        """
        # First try exact match (for special keys like __placeholder__)
        if key in self._projects:
            actual_key = key
        else:
            actual_key = self._make_key(key)
            for stored_key in list(self._projects.keys()):
                if self._make_key(stored_key) == actual_key:
                    actual_key = stored_key
                    break
            else:
                LOGGER.warning(f'Cannot close, project not found: {key}')
                return False

        del self._projects[actual_key]
        self._project_names.pop(actual_key, None)

        LOGGER.info(
            f'Closed project: {actual_key} (remaining: {len(self._projects)})')

        if self._active_key == actual_key:
            # Switch to another project if available
            if self._projects:
                self._active_key = next(iter(self._projects))
                LOGGER.info(
                    f'Auto-switched to: {self._active_key}')
            else:
                self._active_key = None
            self.active_changed.emit()

        self.project_closed.emit(actual_key)
        return True

    def close_all(self):
        """Close all projects."""
        for key in list(self._projects.keys()):
            self.close(key)

    def keys(self):
        """Return all project keys."""
        return self._projects.keys()

    def project_name(self, key: str) -> str:
        """Return the display name for a project key."""
        return self._project_names.get(key, osp.basename(key))

    def project_for_key(self, key: str) -> Optional[ProjImgTrans]:
        """Return the ProjImgTrans for a key, or None."""
        for stored_key, proj in self._projects.items():
            if self._make_key(stored_key) == self._make_key(key):
                return proj
        return None
