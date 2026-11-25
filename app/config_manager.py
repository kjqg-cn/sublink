"""Runtime configuration management for Sublink."""

from contextlib import contextmanager
import contextvars
import os
import sys
import threading
from typing import Any, Dict, Iterator, Optional

from flask import g, has_request_context

from app.core.utils import is_truthy
from app.exts import db

APP_DIR = os.path.dirname(os.path.abspath(__file__))
path = APP_DIR

# Global runtime flags
SkipCert = False
Udp = False
Emoji = False
Hy2PinFallback = False
CustomFeature = False
CustomLoopback = False
CustomNodeName = False

_globals_lock = threading.Lock()

# Thread/context-scoped runtime config snapshot for worker threads outside Flask request context
_thread_runtime_config: contextvars.ContextVar[Optional[Dict[str, bool]]] = contextvars.ContextVar(
    '_thread_runtime_config', default=None
)


@contextmanager
def use_runtime_config(cfg: Dict[str, bool]) -> Iterator[None]:
    """Bind a runtime configuration snapshot to the current execution context/thread."""
    token = _thread_runtime_config.set(dict(cfg))
    try:
        yield
    finally:
        _thread_runtime_config.reset(token)


def sync_config_globals(data: Dict[str, Any]) -> None:
    """Synchronize global config variables with dictionary and app.view under lock."""
    global SkipCert, Udp, Emoji, Hy2PinFallback, CustomFeature, CustomLoopback, CustomNodeName
    with _globals_lock:
        Udp = bool(data.get('udp', False))
        Emoji = bool(data.get('emoji', False))
        SkipCert = bool(data.get('skipcert', False))
        Hy2PinFallback = bool(data.get('hy2_pin_fallback', False))
        CustomFeature = bool(data.get('custom', False))
        CustomLoopback = bool(data.get('custom_loopback', False))
        CustomNodeName = bool(data.get('custom_node_name', False))

        view_mod = sys.modules.get('app.view')
        if view_mod:
            view_mod.Udp = Udp
            view_mod.Emoji = Emoji
            view_mod.SkipCert = SkipCert
            view_mod.Hy2PinFallback = Hy2PinFallback
            view_mod.CustomFeature = CustomFeature
            view_mod.CustomLoopback = CustomLoopback
            view_mod.CustomNodeName = CustomNodeName


def _snapshot_globals() -> Dict[str, bool]:
    with _globals_lock:
        view_mod = sys.modules.get('app.view')
        return {
            'udp': getattr(view_mod, 'Udp', Udp) if view_mod else Udp,
            'skipcert': getattr(view_mod, 'SkipCert', SkipCert) if view_mod else SkipCert,
            'emoji': getattr(view_mod, 'Emoji', Emoji) if view_mod else Emoji,
            'hy2_pin_fallback': getattr(view_mod, 'Hy2PinFallback', Hy2PinFallback) if view_mod else Hy2PinFallback,
            'custom': getattr(view_mod, 'CustomFeature', CustomFeature) if view_mod else CustomFeature,
            'custom_loopback': getattr(view_mod, 'CustomLoopback', CustomLoopback) if view_mod else CustomLoopback,
            'custom_node_name': getattr(view_mod, 'CustomNodeName', CustomNodeName) if view_mod else CustomNodeName,
        }


def get_runtime_config(sync_globals: bool = False) -> Dict[str, bool]:
    """
    Get current runtime config.
    In request context: queries database once and caches in flask.g without mutating
    shared module globals unless sync_globals=True (prevents cross-thread clobbering).
    Outside request context: returns thread-bound snapshot or module globals.
    """
    if has_request_context():
        if hasattr(g, 'runtime_config'):
            if sync_globals:
                sync_config_globals(g.runtime_config)
            return g.runtime_config
        cfg = {
            'udp': False,
            'skipcert': False,
            'emoji': False,
            'hy2_pin_fallback': False,
            'custom': False,
            'custom_loopback': False,
            'custom_node_name': False,
        }
        try:
            from app.model import Config
            configs = db.session.query(Config.key, Config.value).all()
            for key, val in configs:
                cfg[key] = is_truthy(val)
        except Exception:
            cfg = _snapshot_globals()
        g.runtime_config = cfg
        if sync_globals:
            sync_config_globals(cfg)
        return cfg

    override = _thread_runtime_config.get()
    if override is not None:
        return override

    return _snapshot_globals()


def setup_runtime_config() -> None:
    """Pre-request hook to populate g.runtime_config (read-only, no global mutation)."""
    get_runtime_config(sync_globals=False)


def cleanup_runtime_config(exc: Any = None) -> None:
    """Teardown hook to clean up g.runtime_config."""
    if hasattr(g, 'runtime_config'):
        delattr(g, 'runtime_config')


def load_config() -> Dict[str, bool]:
    """Load configuration from database into global variables."""
    try:
        data = {
            'udp': False,
            'skipcert': False,
            'emoji': False,
            'hy2_pin_fallback': False,
            'custom': False,
            'custom_loopback': False,
            'custom_node_name': False,
        }
        from app.model import Config
        configs = db.session.query(Config.key, Config.value).all()
        for key, val in configs:
            data[key] = is_truthy(val)
        sync_config_globals(data)
        if has_request_context():
            g.runtime_config = data
        return data
    except Exception:
        return _snapshot_globals()
