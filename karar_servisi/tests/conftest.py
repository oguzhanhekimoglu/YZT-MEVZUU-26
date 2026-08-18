"""Repository-local pytest workspace with Windows-safe permissions."""

from __future__ import annotations

import os
import shutil
import warnings
from pathlib import Path
from uuid import uuid4

import pytest
from _pytest.cacheprovider import Cache
from _pytest.config import Config
from _pytest.tmpdir import TempPathFactory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTEST_WORK_ROOT = PROJECT_ROOT / ".pytest_cache" / "runtime"


class WritableTempPathFactory(TempPathFactory):
    """Create unique pytest directories without Windows' restrictive 0700 ACL."""

    def mktemp(self, basename: str, numbered: bool = True) -> Path:
        """Create a collision-free directory under the session workspace."""
        basename = self._ensure_relative_to_basetemp(basename)
        if not numbered:
            path = self.getbasetemp() / basename
            path.mkdir()
            return path

        while True:
            path = self.getbasetemp() / f"{basename}-{uuid4().hex}"
            try:
                path.mkdir()
            except FileExistsError:
                continue
            return path


def _is_session_workspace(path: Path) -> bool:
    return path.parent.resolve() == PYTEST_WORK_ROOT.resolve()


@pytest.hookimpl(trylast=True)
def pytest_configure(config: Config) -> None:
    """Route tmp_path, tmpdir, and pytest cache to one unique repo-local run."""
    run_id = f"{os.getpid()}-{uuid4().hex}"
    run_root = PYTEST_WORK_ROOT / run_id
    run_root.mkdir(parents=True)
    cache_root = run_root / "cache"
    cache_root.mkdir()

    factory = WritableTempPathFactory(
        given_basetemp=None,
        retention_count=0,
        retention_policy="none",
        trace=config.trace.get("tmpdir"),
        basetemp=run_root / "tmp",
        _ispytest=True,
    )
    factory.getbasetemp().mkdir()

    config._tmp_path_factory = factory
    config.cache = Cache(cache_root, config, _ispytest=True)
    config._operational_decision_test_run_root = run_root


@pytest.hookimpl(trylast=True)
def pytest_unconfigure(config: Config) -> None:
    """Remove only this pytest process' verified session workspace."""
    run_root = getattr(config, "_operational_decision_test_run_root", None)
    if not isinstance(run_root, Path) or not _is_session_workspace(run_root):
        return

    try:
        shutil.rmtree(run_root)
    except FileNotFoundError:
        pass
    except OSError as error:
        warnings.warn(
            f"pytest session workspace could not be removed: {error}",
            ResourceWarning,
            stacklevel=1,
        )

    for directory in (PYTEST_WORK_ROOT, PYTEST_WORK_ROOT.parent):
        try:
            directory.rmdir()
        except OSError:
            break
