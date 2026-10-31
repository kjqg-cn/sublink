"""Sublink HTTP route controller and backward-compatible facade."""

from io import BytesIO
import json
import os
import sys
import types
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlsplit

from flask import Blueprint, g, has_request_context, jsonify, make_response, render_template, request, send_file
from flask_jwt_extended import create_access_token, create_refresh_token, get_jwt_identity, jwt_required
import requests
import yaml

from app import config_manager
from app.config_manager import (
    APP_DIR, CustomFeature, CustomLoopback, CustomNodeName, Emoji, SkipCert, Udp,
    cleanup_runtime_config, get_runtime_config, load_config, path, setup_runtime_config, sync_config_globals,
)
from app.core.generator import (
    clash_encode, expand_node_list, get_singbox_bandwidth, get_singbox_outbound,
    get_singbox_tls, get_singbox_transport, get_unique_proxy_name, get_unique_singbox_tag, inject_surge_proxies,
    load_singbox_template, parse_clash_node, parse_singbox_node, parse_surge_node,
    singbox_encode, singbox_node_types, surge_encode, v2ray_encode, validate_singbox_template,
)
from app.core.parsers import (
    NodeParse, parse_hysteria, parse_hysteria2, parse_ss, parse_ssr, parse_trojan, parse_vless, parse_vmess,
)
from app.core.rewrite import (
    get_node_server, hk_name_prefix, is_ipv6_node_server, node_name_rewrite_rules, rewritable_node_types,
    rewrite_fragment_name, rewrite_info_host_port, rewrite_loopback_node, rewrite_node_name,
    rewrite_node_name_ipv6_text, rewrite_node_name_text, rewrite_node_url, rewrite_query_name, rewrite_remote_node,
    rewrite_ssr_name, rewrite_vmess_name,
)
from app.core.utils import (
    SUBSCRIPTION_DOWNLOAD_NAME, TOKEN_ALPHABET, decode_base64_if, decode_base64_if_emoji,
    encode_base64, get_host_port, get_proxy_type, get_remote_sub_host, if_ipv6_address,
    is_truthy, new_access_token, parse_server_port, remote_sub_types, subname_list,
)
from app.exts import db
from app.model import Config, Login, Sub, User
from app.remote import fetch_remote_sub, get_country_emoji, request_timeout, save_ip_address

blue = Blueprint('blue', __name__)


# ---------------------------------------------------------------------------
# Database & Route Helpers
# ---------------------------------------------------------------------------

def _commit_response(msg: str, error_prefix: str = '错误信息：'):
    """Commit current db transaction and return JSON response."""
    try:
        db.session.commit()
        return jsonify({'code': 200, 'msg': msg})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 400, 'msg': f'{error_prefix}{str(e)}'})


def _handle_config_file(filename: str, validator: Optional[Callable[[str], Optional[str]]] = None):
    """Generic reader/writer handler for client configuration files."""
    data = request.get_json() or {}
    index = data.get('index')
    config_file = os.path.join(path, 'db', filename)
    if index == 'read':
        with open(config_file, 'r', encoding='utf-8') as file:
            return jsonify({'code': 200, 'msg': file.read()})
    if index == 'save':
        text = data.get('text')
        if not text:
            return jsonify({'code': 400, 'msg': '不能为空'})
        if validator:
            err = validator(text)
            if err:
                return jsonify({'code': 400, 'msg': err})
        with open(config_file, 'w', encoding='utf-8') as file:
            file.write(text)
        return jsonify({'code': 200, 'msg': '保存成功'})
    return jsonify({'code': 400, 'msg': '不支持的操作'})


def _validate_clash_yaml(text: str) -> Optional[str]:
    try:
        parsed_yaml = yaml.safe_load(text)
        if not isinstance(parsed_yaml, dict):
            return '配置格式错误: YAML 根节点必须为字典结构'
    except Exception as e:
        return f'配置格式错误:{str(e)}'
    return None


def _validate_singbox_json(text: str) -> Optional[str]:
    try:
        config_dict = json.loads(text)
        validate_singbox_template(config_dict)
    except (ValueError, json.JSONDecodeError) as e:
        return f'配置格式错误:{str(e)}'
    return None


def get_next_sub_sort_order() -> int:
    max_order = db.session.query(db.func.max(Sub.sort_order)).scalar()
    return (max_order if max_order is not None else -1) + 1


def get_sub_sort_order(name: str) -> int:
    sub = Sub.query.filter_by(name=name).order_by(Sub.sort_order.asc(), Sub.id.asc()).first()
    return sub.sort_order if sub else get_next_sub_sort_order()


def get_access_token(name: str) -> Optional[str]:
    sub = Sub.query.filter_by(name=name).first()
    return sub.access_token if sub else None


def ensure_access_token(name: str) -> Optional[str]:
    subs = Sub.query.filter_by(name=name).all()
    if not subs:
        return None
    token = next((sub.access_token for sub in subs if sub.access_token), None) or new_access_token()
    changed = False
    for sub in subs:
        if sub.access_token != token:
            sub.access_token = token
            changed = True
    if changed:
        db.session.commit()
    return token


# ---------------------------------------------------------------------------
# Request Lifecycle Hooks
# ---------------------------------------------------------------------------

@blue.before_request
def setup_request_runtime_config():
    setup_runtime_config()


@blue.teardown_app_request
def teardown_request_runtime_config(exc=None):
    cleanup_runtime_config(exc)


# ---------------------------------------------------------------------------
# Subscription & Config Endpoints
# ---------------------------------------------------------------------------

@blue.route('/sub/<string:target>/<path:name>', methods=['GET'])
def get_sub_url(target: str, name: str):
    subs = Sub.query.filter_by(access_token=name).order_by(Sub.sort_order.asc(), Sub.id.asc()).all()
    if not subs:
        try:
            legacy_name = decode_base64_if_emoji(name)
        except Exception:
            return jsonify({'code': 400, 'msg': '订阅地址格式错误'}), 400
        subs = Sub.query.filter_by(name=legacy_name, legacy_enabled=True).order_by(
            Sub.sort_order.asc(), Sub.id.asc()
        ).all()
    if not subs:
        return jsonify({'code': 400, 'msg': '订阅不存在'})

    if target == 'clash':
        data = clash_encode(subs)
        return make_response(send_file(BytesIO(data.encode('utf-8')), mimetype='text/plain',
                                       as_attachment=False, download_name=SUBSCRIPTION_DOWNLOAD_NAME))
    if target == 'v2ray':
        data = v2ray_encode(subs)
        return make_response(send_file(BytesIO(data.encode('utf-8')), mimetype='text/html',
                                       as_attachment=False, download_name=f'{SUBSCRIPTION_DOWNLOAD_NAME}.txt'))
    if target == 'surge':
        data = f'#!MANAGED-CONFIG {request.url} interval=86400 strict=false\n' + surge_encode(subs)
        return make_response(send_file(BytesIO(data.encode('utf-8')), mimetype='text/plain',
                                       as_attachment=False, download_name=SUBSCRIPTION_DOWNLOAD_NAME))
    if target == 'sing-box':
        try:
            data = singbox_encode(subs)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            return jsonify({'code': 500, 'msg': f'sing-box 配置生成失败:{str(e)}'}), 500
        return make_response(send_file(BytesIO(data.encode('utf-8')), mimetype='application/json',
                                       as_attachment=False, download_name=f'{SUBSCRIPTION_DOWNLOAD_NAME}.json'))
    return jsonify({'code': 400, 'msg': '不支持的订阅类型'}), 400


@blue.route('/clash_config', methods=['POST'])
@jwt_required()
def clash_config():
    return _handle_config_file('clash.yaml', _validate_clash_yaml)


@blue.route('/surge_config', methods=['POST'])
@jwt_required()
def surge_config():
    return _handle_config_file('surge.conf')


@blue.route('/singbox_config', methods=['POST'])
@jwt_required()
def singbox_config():
    return _handle_config_file('sing-box.json', _validate_singbox_json)


@blue.route('/')
def get_index():
    return render_template('index.html')


@blue.route('/next')
def get_index_next():
    index_path = os.path.join(path, 'static', 'next', 'index.html')
    if not os.path.exists(index_path):
        return '新版前端尚未构建，请先在 web/next 执行 npm run build', 404
    return send_file(index_path)


# ---------------------------------------------------------------------------
# Auth Endpoints
# ---------------------------------------------------------------------------

@blue.route('/login', methods=['POST'])
def get_login():
    data = request.get_json() or {}
    username = data.get('username')
    password = data.get('password')
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'code': 404, 'msg': '账号或者密码错误'})
    if user.username == username and user.password == password:
        access_token = create_access_token(identity=username)
        refresh_token = create_refresh_token(identity=username)
        save_ip_address()
        return jsonify({'code': 200, 'token': access_token, 'refresh': refresh_token, 'msg': '登录成功'})
    return jsonify({'code': 404, 'msg': '账号或者密码错误'})


@blue.route('/refresh', methods=['POST'])
@jwt_required(refresh=True)
def get_refresh():
    current_user = get_jwt_identity()
    return create_access_token(current_user) if current_user else '没获取到'


# ---------------------------------------------------------------------------
# Node & Subscription Management Endpoints
# ---------------------------------------------------------------------------

@blue.route('/create_sub', methods=['POST'])
@jwt_required()
def get_create_sub():
    data = request.get_json() or {}
    name = data.get('name')
    nodes = data.get('node') or []
    if Sub.query.filter_by(name=name).first():
        return jsonify({'code': 400, 'msg': '订阅名字已经存在'})
    sort_order = get_next_sub_sort_order()
    access_token = new_access_token()
    added, invalid = 0, []
    for item in nodes:
        node, _, remarks = item.partition('|')
        node, remarks = node.strip(), remarks.strip()
        if not node:
            continue
        if any(kw in node for kw in subname_list):
            db.session.add(Sub(name=name, node=node, remarks=remarks, sort_order=sort_order,
                               access_token=access_token, legacy_enabled=False))
            try:
                db.session.commit()
                added += 1
            except Exception as e:
                db.session.rollback()
                return jsonify({'code': 400, 'msg': f'错误信息：{str(e)}'})
        else:
            invalid.append(node[:40])
    if added == 0:
        return jsonify({'code': 400, 'msg': '没有可用的节点，请检查节点格式'})
    if invalid:
        return jsonify({'code': 200, 'msg': f'创建成功，已跳过 {len(invalid)} 个无效节点'})
    return jsonify({'code': 200, 'msg': '创建成功'})


@blue.route('/create_node', methods=['POST'])
@jwt_required()
def create_node():
    data = request.get_json() or {}
    name = data.get('name')
    remarks = data.get('remarks')
    node = (data.get('node') or '').strip()
    if not any(kw in node for kw in subname_list):
        return jsonify({'code': 400, 'msg': '不是有效的协议,请检查后重新输入'})
    if not node:
        return jsonify({'code': 400, 'msg': '节点内容不能为空'})
    cur = Sub.query.filter_by(name=name).order_by(Sub.id.asc()).first()
    db.session.add(Sub(
        name=name, node=node, remarks=remarks,
        sort_order=cur.sort_order if cur else get_next_sub_sort_order(),
        access_token=cur.access_token if cur else new_access_token(),
        legacy_enabled=cur.legacy_enabled if cur else False
    ))
    return _commit_response('创建成功')


@blue.route('/get_subs', methods=['POST'])
@jwt_required()
def get_subs():
    subs = Sub.query.order_by(Sub.sort_order.asc(), Sub.id.asc()).all()
    for name in {s.name for s in subs}:
        ensure_access_token(name)
    if subs:
        subs = Sub.query.order_by(Sub.sort_order.asc(), Sub.id.asc()).all()
    return jsonify([{
        'id': s.id, 'name': s.name, 'node': s.node, 'remarks': s.remarks,
        'sort_order': s.sort_order, 'access_token': s.access_token, 'legacy_enabled': s.legacy_enabled
    } for s in subs])


@blue.route('/rename_sub/<path:name>', methods=['POST'])
@jwt_required()
def rename_sub(name: str):
    subs = Sub.query.filter_by(name=name).all()
    new_name = (request.get_json() or {}).get('newName')
    if Sub.query.filter_by(name=new_name).first():
        return jsonify({'code': 400, 'msg': '名字已存在'})
    for s in subs:
        s.name = new_name
    return _commit_response('成功', error_prefix='错误')


@blue.route('/get_sub/<path:name>', methods=['POST'])
@jwt_required()
def get_sub(name: str):
    subs = Sub.query.filter_by(name=name).order_by(Sub.sort_order.asc(), Sub.id.asc()).all()
    return jsonify([{
        'id': s.id, 'name': s.name, 'node': s.node, 'remarks': s.remarks,
        'access_token': s.access_token, 'legacy_enabled': s.legacy_enabled
    } for s in subs])


@blue.route('/del_sub/<path:name>', methods=['POST'])
@jwt_required()
def del_sub(name: str):
    subs = Sub.query.filter_by(name=name).all()
    if not subs:
        return jsonify({'code': 400, 'msg': '不存在'})
    for s in subs:
        db.session.delete(s)
    return _commit_response('删除成功', error_prefix='错误信息:')


@blue.route('/del_sub_node/<int:id>', methods=['POST'])
@jwt_required()
def del_sub_node(id: int):
    sub = Sub.query.filter_by(id=id).first()
    if not sub:
        return jsonify({'code': 400, 'msg': '不存在'})
    db.session.delete(sub)
    return _commit_response('删除成功', error_prefix='错误信息:')


@blue.route('/set_sub', methods=['POST'])
@jwt_required()
def get_set_sub():
    data = request.get_json() or {}
    name = data.get('name')
    subs = Sub.query.filter_by(name=name).order_by(Sub.id.asc()).all()
    if not subs:
        return jsonify({'code': 400, 'msg': '订阅不存在'})
    sort_order = subs[0].sort_order if subs else get_next_sub_sort_order()
    access_token = subs[0].access_token if subs else new_access_token()
    legacy_enabled = subs[0].legacy_enabled if subs else False
    parsed_nodes = []
    for item in (data.get('newNode') or []):
        node, sep, remarks = item.partition('|')
        node, remarks = node.strip(), remarks.strip() if sep else ''
        if not node:
            continue
        if not any(kw in node for kw in subname_list):
            return jsonify({'code': 400, 'msg': f'节点格式不正确：{node[:40]}'})
        parsed_nodes.append((node, remarks))
    if not parsed_nodes:
        return jsonify({'code': 400, 'msg': '至少保留一个有效节点'})
    try:
        Sub.query.filter_by(name=name).delete(synchronize_session=False)
        db.session.add_all([
            Sub(name=name, node=node, remarks=remarks, sort_order=sort_order,
                access_token=access_token, legacy_enabled=legacy_enabled)
            for node, remarks in parsed_nodes
        ])
        db.session.commit()
        return jsonify({'code': 200, 'msg': '修改成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 400, 'msg': f'错误信息：{str(e)}'})


@blue.route('/sort_subs', methods=['POST'])
@jwt_required()
def sort_subs():
    names = (request.get_json() or {}).get('names', [])
    if not isinstance(names, list) or len(names) != len(set(names)):
        return jsonify({'code': 400, 'msg': '订阅排序数据不正确'})
    existing = [r[0] for r in db.session.query(Sub.name).distinct().all()]
    if set(names) != set(existing):
        return jsonify({'code': 400, 'msg': '订阅列表已变化，请刷新后重试'})
    try:
        for order, name in enumerate(names):
            Sub.query.filter_by(name=name).update({'sort_order': order})
        db.session.commit()
        return jsonify({'code': 200, 'msg': '订阅排序已保存'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 400, 'msg': f'错误信息：{str(e)}'})


@blue.route('/set_sub_legacy/<path:name>', methods=['POST'])
@jwt_required()
def set_sub_legacy(name: str):
    data = request.get_json(silent=True) or {}
    enabled = data.get('enabled')
    if not isinstance(enabled, bool):
        return jsonify({'code': 400, 'msg': '旧地址兼容状态不正确'})
    if not Sub.query.filter_by(name=name).first():
        return jsonify({'code': 400, 'msg': '订阅不存在'})
    try:
        Sub.query.filter_by(name=name).update({'legacy_enabled': enabled}, synchronize_session=False)
        db.session.commit()
        return jsonify({'code': 200, 'msg': '旧地址兼容已开启' if enabled else '旧地址兼容已关闭'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 400, 'msg': f'错误信息：{str(e)}'})


@blue.route('/set_node', methods=['POST'])
@jwt_required()
def get_set_node():
    data = request.get_json() or {}
    node = (data.get('node') or '').strip()
    sub = Sub.query.filter_by(id=data.get('id')).first()
    if not any(kw in node for kw in subname_list):
        return jsonify({'code': 400, 'msg': '节点格式不对'})
    if not sub:
        return jsonify({'code': 404, 'msg': '节点不存在'})
    sub.node, sub.remarks = node, data.get('remarks')
    return _commit_response('修改成功')


@blue.route('/set_user', methods=['POST'])
@jwt_required()
def get_set_user():
    data = request.get_json() or {}
    current_user = get_jwt_identity()
    target_username = data.get('username')
    if not current_user or current_user != target_username:
        return jsonify({'code': 403, 'msg': '无权修改其他用户账号'})
    user = User.query.filter_by(username=target_username).first()
    if not user:
        return jsonify({'code': 400, 'msg': '账号不正确'})
    new_username = data.get('newUserName')
    password = data.get('password')
    if not new_username or not password or not str(new_username).strip() or not str(password).strip():
        return jsonify({'code': 400, 'msg': '用户名和密码不能为空'})
    new_username = str(new_username).strip()
    if new_username != target_username and User.query.filter_by(username=new_username).first():
        return jsonify({'code': 400, 'msg': '用户名已存在'})
    user.username = new_username
    user.password = password
    return _commit_response('修改成功', error_prefix='错误信息:')


@blue.route('/decode_sub', methods=['POST'])
@jwt_required()
def decode_sub():
    data = request.get_json() or {}
    raw_urls = data.get('urls')
    if not raw_urls:
        return jsonify({'code': 400, 'msg': 'URL不能为空'})
    urls = raw_urls if isinstance(raw_urls, list) else [raw_urls]
    datas = []
    for url in urls:
        if not isinstance(url, str) or not url.strip():
            return jsonify({'code': 400, 'msg': 'URL不能为空'})
        url = url.strip()
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in ('http', 'https'):
            return jsonify({'code': 400, 'msg': f'仅支持 http 或 https 协议: {url}'})
        try:
            try:
                resp = requests.get(url, timeout=(3, 10))
            except requests.exceptions.SSLError as ssl_err:
                print(f'远程订阅证书校验失败，临时跳过校验重试:{url} 错误信息:{str(ssl_err)}')
                resp = requests.get(url, timeout=(3, 10), verify=False)
            if resp.status_code == 200:
                datas.append(decode_base64_if(resp.text))
            else:
                return jsonify({'code': resp.status_code, 'msg': resp.text})
        except Exception as e:
            return jsonify({'code': 400, 'msg': f'拉取订阅失败: {str(e)}'})
    return jsonify({'code': 200, 'msg': datas})


@blue.route('/get_ip_address', methods=['POST'])
@jwt_required()
def get_ip_address():
    logins = Login.query.order_by(Login.time.desc()).all()
    return jsonify([{'id': i.id, 'ip': i.ip, 'address': i.address, 'time': i.time} for i in logins])


# ---------------------------------------------------------------------------
# Global Runtime Config Endpoints
# ---------------------------------------------------------------------------

@blue.route('/set_conifg', methods=['POST'])
@jwt_required()
def set_config():
    data = request.get_json() or {}
    keys = ['udp', 'skipcert', 'emoji', 'custom', 'custom_loopback', 'custom_node_name']
    for key in keys:
        if key in data:
            val = is_truthy(data.get(key))
            Config.query.filter_by(key=key).delete()
            db.session.add(Config(key=key, value='1' if val else '0'))
    try:
        db.session.commit()
        cfg = dict(get_runtime_config())
        for key in keys:
            if key in data:
                cfg[key] = is_truthy(data.get(key))
        if has_request_context():
            g.runtime_config = cfg
        sync_config_globals(cfg)
        return jsonify({'code': 200, 'msg': '设置保存成功'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 400, 'msg': f'错误信息：{str(e)}'})


@blue.route('/get_conifg', methods=['POST'])
@jwt_required()
def get_config():
    if has_request_context() and hasattr(g, 'runtime_config'):
        delattr(g, 'runtime_config')
    return jsonify(get_runtime_config())


# ---------------------------------------------------------------------------
# Module proxy class for test-compatibility (patch.object / global assignments)
# ---------------------------------------------------------------------------

_CONFIG_GLOBAL_NAMES = {
    'CustomFeature',
    'CustomLoopback',
    'CustomNodeName',
    'Emoji',
    'SkipCert',
    'Udp',
    'path',
}


class _ViewModule(types.ModuleType):
    """Module proxy providing transparent two-way synchronization with config_manager."""

    def __getattribute__(self, name: str) -> Any:
        if name in _CONFIG_GLOBAL_NAMES:
            return getattr(config_manager, name)
        return super().__getattribute__(name)

    def __setattr__(self, name: str, value: Any) -> None:
        if name in _CONFIG_GLOBAL_NAMES:
            setattr(config_manager, name, value)
        super().__setattr__(name, value)


sys.modules[__name__].__class__ = _ViewModule
