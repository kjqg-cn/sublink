"""Runtime configuration management for Sublink."""

import os
import sys
from typing import Any, Dict

from flask import g, has_request_context

from app.core.utils import is_truthy
from app.exts import db

APP_DIR = os.path.dirname(os.path.abspath(__file__))
path = APP_DIR

# Global runtime flags
SkipCert = False
Udp = False
Emoji = False
CustomFeature = False
CustomLoopback = False
CustomNodeName = False


def sync_config_globals(data: Dict[str, Any]) -> None:
    """Synchronize global config variables with dictionary and app.view."""
    global SkipCert, Udp, Emoji, CustomFeature, CustomLoopback, CustomNodeName
    Udp = data.get('udp', False)
    Emoji = data.get('emoji', False)
    SkipCert = data.get('skipcert', False)
    CustomFeature = data.get('custom', False)
    CustomLoopback = data.get('custom_loopback', False)
    CustomNodeName = data.get('custom_node_name', False)

    view_mod = sys.modules.get('app.view')
    if view_mod:
        view_mod.Udp = Udp
        view_mod.Emoji = Emoji
        view_mod.SkipCert = SkipCert
        view_mod.CustomFeature = CustomFeature
        view_mod.CustomLoopback = CustomLoopback
        view_mod.CustomNodeName = CustomNodeName


def get_runtime_config() -> Dict[str, bool]:
    """
    Get current runtime config.
    In request context: queries database once and caches in flask.g.
    Outside request context: returns current global values.
    """
    view_mod = sys.modules.get('app.view')
    curr_udp = getattr(view_mod, 'Udp', Udp) if view_mod else Udp
    curr_skipcert = getattr(view_mod, 'SkipCert', SkipCert) if view_mod else SkipCert
    curr_emoji = getattr(view_mod, 'Emoji', Emoji) if view_mod else Emoji
    curr_custom = getattr(view_mod, 'CustomFeature', CustomFeature) if view_mod else CustomFeature
    curr_loopback = getattr(view_mod, 'CustomLoopback', CustomLoopback) if view_mod else CustomLoopback
    curr_node_name = getattr(view_mod, 'CustomNodeName', CustomNodeName) if view_mod else CustomNodeName

    if has_request_context():
        if hasattr(g, 'runtime_config'):
            return g.runtime_config
        cfg = {
            'udp': False,
            'skipcert': False,
            'emoji': False,
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
            cfg = {
                'udp': curr_udp,
                'skipcert': curr_skipcert,
                'emoji': curr_emoji,
                'custom': curr_custom,
                'custom_loopback': curr_loopback,
                'custom_node_name': curr_node_name,
            }
        g.runtime_config = cfg
        sync_config_globals(cfg)
        return cfg

    return {
        'udp': curr_udp,
        'skipcert': curr_skipcert,
        'emoji': curr_emoji,
        'custom': curr_custom,
        'custom_loopback': curr_loopback,
        'custom_node_name': curr_node_name,
    }


def setup_runtime_config() -> None:
    """Pre-request hook to populate g.runtime_config."""
    get_runtime_config()


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
        return {
            'udp': Udp,
            'skipcert': SkipCert,
            'emoji': Emoji,
            'custom': CustomFeature,
            'custom_loopback': CustomLoopback,
            'custom_node_name': CustomNodeName,
        }
