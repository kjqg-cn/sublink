import datetime
import requests,json
import urllib3
from io import BytesIO
from flask import Blueprint,request,jsonify,render_template,send_file,make_response
from .model import *
import base64,yaml,urllib.parse,os,re,secrets,string
from flask_jwt_extended import jwt_required,get_jwt_identity,create_access_token,create_refresh_token
blue = Blueprint('blue',__name__)
path = os.path.dirname(os.path.abspath(__file__))
subname_list =['vless','vmess','ss','ssr','trojan','hysteria','hy2','hysteria2','http','https']
remote_sub_types = ('http', 'https')
rewritable_node_types = ('vless', 'vmess', 'ss', 'ssr', 'trojan', 'hysteria', 'hy2', 'hysteria2')
hk_name_prefix = '🇭🇰【香港'
# 在这里补充需要识别的国家关键字。
node_name_rewrite_rules = [
    (('SG',), '🇸🇬【新加坡'),
    (('TYO',), '🇯🇵【东京'),
    (('LAX',), '🇺🇸【洛杉矶'),
    (('HOU',), '🇺🇸【休斯顿'),
    (('LON', 'UK'), '🇬🇧【伦敦'),
    (('-DE',), '🇩🇪【莱比锡'),
]
request_timeout = (3, 8)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
TOKEN_ALPHABET = string.ascii_lowercase + string.digits
SUBSCRIPTION_DOWNLOAD_NAME = 'v3订阅'
def new_access_token():
    return ''.join(secrets.choice(TOKEN_ALPHABET) for _ in range(48))

def get_next_sub_sort_order():
    max_order = db.session.query(db.func.max(Sub.sort_order)).scalar()
    return (max_order if max_order is not None else -1) + 1

def get_sub_sort_order(name):
    sub = Sub.query.filter_by(name=name).order_by(Sub.sort_order.asc(), Sub.id.asc()).first()
    return sub.sort_order if sub else get_next_sub_sort_order()

def get_access_token(name):
    sub = Sub.query.filter_by(name=name).first()
    return sub.access_token if sub else None

def ensure_access_token(name):
    subs = Sub.query.filter_by(name=name).all()
    if not subs:
        return None
    token = next((sub.access_token for sub in subs if sub.access_token), None)
    if not token:
        token = new_access_token()
    changed = False
    for sub in subs:
        if sub.access_token != token:
            sub.access_token = token
            changed = True
    if changed:
        db.session.commit()
    return token
def get_country_emoji(hostname):
    import socket
    # print(hostname)
    def is_valid_url(url):
        pattern = re.compile(r'^(https?:\/\/)?([\da-z\.-]+)\.([a-z\.]{2,6})([\/\w \.-]*)*\/?$')
        return bool(pattern.match(url))

    try:
        ip = hostname
        if is_valid_url(ip):
            ip = socket.gethostbyname(hostname)
        response = requests.get(f"http://ipwho.is/{ip}", timeout=request_timeout)
        if response.status_code == 200:
            js = response.json()
            flag = js.get('flag') or {}
            emoji = flag.get("emoji")
            # print(js)
            if emoji:
                return emoji
    except Exception as e:
        print(f'获取入口国旗失败:{hostname} 错误信息:{str(e)}')
    return hostname
def save_ip_address(): # 获取ip地址
    ip_address = request.environ.get('HTTP_X_REAL_IP', request.remote_addr)
    params = {
        'ip':ip_address,
        'json':'true'
    }
    res = requests.get('https://whois.pconline.com.cn/ipJson.jsp', params=params)
    # print(res.url)
    if res.status_code == 200:
        res_text = res.text
        if res_text:
            js = json.loads(res_text)
            timer =datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
            address = js.get('addr')
            login = Login(ip=ip_address,address=address,time=timer)
            try:
                db.session.add(login)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                db.session.flush()
                print('错误信息:'+str(e))
            # print(res_text,type(js))
    # print(res.status_code)
def decode_base64_if_emoji(encoded_text):#base64带emoji解码
    # 先解url编码
    encoded_text = urllib.parse.unquote(encoded_text)
    # 将字符串转换为字节流
    byte_text = encoded_text.encode('utf-8')
    # 使用Base64解码字节流
    decoded_bytes = base64.b64decode(byte_text)
    # 将字节流转换为文本
    decoded_text = decoded_bytes.decode('utf-8')
    return decoded_text
def if_ipv6_address(string): # 判断ipv6
    pattern = r'\[([0-9a-fA-F:]+)\]'
    match = re.search(pattern, string)
    if match:
        ipv6_address = match.group(1)
        return ipv6_address
    else:
        return string
def decode_base64_if(text):  # base64解码
    try:
        name = ''
        decoded_text = text
        at = ''
        if '#' in decoded_text:
            name = '#' + decoded_text.split('#')[1]
            decoded_text = decoded_text.split('#')[0]
        if '@' in decoded_text:
            at = '@' + decoded_text.split('@')[1]
        padding = 4 - (len(decoded_text) % 4)
        # 判断是否需要补齐长度
        # print(decoded_text)
        if padding > 0 and padding < 4:
            # 添加填充字符
            decoded_text += "=" * padding

        decoded_text = base64.b64decode(decoded_text).decode('utf-8')
        # print('解：' + decoded_text)
        return decoded_text + at + name
    except Exception as e:
        # 如果无法解码为Base64，则返回原始文本
        # print(f'不是base64，错误信息：{str(e)}')
        return text
def get_proxy_type(node):
    return node.strip().split('://', 1)[0].lower()
def get_remote_sub_host(url):
    return urllib.parse.urlparse(url).hostname
def encode_base64(text, urlsafe=False):
    if urlsafe:
        return base64.urlsafe_b64encode(text.encode('utf-8')).decode('utf-8').rstrip('=')
    return base64.b64encode(text.encode('utf-8')).decode('utf-8')
def get_host_port(host, port):
    if ':' in host and not host.startswith('['):
        host = f'[{host}]'
    return f'{host}:{port}'
def rewrite_info_host_port(info, host, port='443'):
    prefix = ''
    host_port = info
    if '@' in info:
        prefix, host_port = info.rsplit('@', 1)
        prefix += '@'
    if ':' not in host_port:
        return info, False
    old_host, _, _ = host_port.rpartition(':')
    if old_host.strip('[]') != '127.0.0.1':
        return info, False
    return prefix + get_host_port(host, port), True
def rewrite_node_url(node, info):
    parse = urllib.parse.urlparse(node)
    return urllib.parse.urlunparse((parse.scheme, info, '', '', parse.query, parse.fragment))
def rewrite_node_name_text(name):
    if not name or not name.startswith(hk_name_prefix):
        return name
    name_upper = name.upper()
    for keywords, target_prefix in node_name_rewrite_rules:
        if any(keyword.upper() in name_upper for keyword in keywords):
            return target_prefix + name[len(hk_name_prefix):]
    return name
def rewrite_query_name(parse, key):
    pairs = urllib.parse.parse_qsl(parse.query, keep_blank_values=True)
    new_pairs = []
    changed = False
    for item_key, item_value in pairs:
        if item_key == key:
            new_value = rewrite_node_name_text(item_value)
            changed = changed or new_value != item_value
            item_value = new_value
        new_pairs.append((item_key, item_value))
    if not changed:
        return None
    return urllib.parse.urlencode(new_pairs)
def rewrite_fragment_name(node, parse):
    name = urllib.parse.unquote(parse.fragment)
    new_name = rewrite_node_name_text(name)
    if new_name == name:
        return node
    return urllib.parse.urlunparse((parse.scheme, parse.netloc, parse.path, parse.params, parse.query, urllib.parse.quote(new_name, safe='')))
def rewrite_vmess_name(node, parse):
    if parse.query == '':
        info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
        proxy = json.loads(decode_base64_if(info))
        name = str(proxy.get('ps') or '')
        new_name = rewrite_node_name_text(name)
        if new_name == name:
            return node
        proxy['ps'] = new_name
        return f"{parse.scheme}://{encode_base64(json.dumps(proxy, ensure_ascii=False, separators=(',', ':')))}"
    new_query = rewrite_query_name(parse, 'remarks')
    if new_query is None:
        return node
    return urllib.parse.urlunparse((parse.scheme, parse.netloc, parse.path, parse.params, new_query, parse.fragment))
def rewrite_ssr_name(node, parse):
    info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
    decoded_info = decode_base64_if(info.replace('-', '+').replace('_', '/'))
    parts = decoded_info.split(':', 5)
    if len(parts) < 6:
        return node
    parse2 = urllib.parse.urlparse(parts[5])
    pairs = urllib.parse.parse_qsl(parse2.query, keep_blank_values=True)
    new_pairs = []
    changed = False
    for key, value in pairs:
        if key == 'remarks':
            name = decode_base64_if(value)
            new_name = rewrite_node_name_text(name)
            if new_name != name:
                value = encode_base64(new_name)
                changed = True
        new_pairs.append((key, value))
    if not changed:
        return node
    parts[5] = urllib.parse.urlunparse((parse2.scheme, parse2.netloc, parse2.path, parse2.params, urllib.parse.urlencode(new_pairs), parse2.fragment))
    return f"{parse.scheme}://{encode_base64(':'.join(parts), urlsafe=True)}"
def rewrite_node_name(node):
    try:
        proxy_type = get_proxy_type(node)
        parse = urllib.parse.urlparse(node)
        if proxy_type == 'vmess':
            return rewrite_vmess_name(node, parse)
        if proxy_type == 'ssr':
            return rewrite_ssr_name(node, parse)
        if proxy_type in rewritable_node_types:
            return rewrite_fragment_name(node, parse)
    except Exception as e:
        print(f'节点名称重写失败:{node} 错误信息:{str(e)}')
    return node
def rewrite_remote_node(node, host):
    node = rewrite_loopback_node(node, host)
    return rewrite_node_name(node)
def rewrite_loopback_node(node, host):
    if not host:
        return node
    try:
        proxy_type = get_proxy_type(node)
        parse = urllib.parse.urlparse(node)
        if proxy_type == 'vmess' and parse.query == '':
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            proxy = json.loads(decode_base64_if(info))
            if str(proxy.get('add')).strip('[]') != '127.0.0.1':
                return node
            proxy['add'] = host
            proxy['port'] = '443'
            return f"{parse.scheme}://{encode_base64(json.dumps(proxy, ensure_ascii=False, separators=(',', ':')))}"
        if proxy_type == 'vmess':
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            rewritten_info, changed = rewrite_info_host_port(decode_base64_if(info), host)
            if changed:
                return urllib.parse.urlunparse((parse.scheme, encode_base64(rewritten_info), '', '', parse.query, parse.fragment))
        if proxy_type == 'ssr':
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            decoded_info = decode_base64_if(info.replace('-', '+').replace('_', '/'))
            parts = decoded_info.split(':', 5)
            if len(parts) < 6 or parts[0].strip('[]') != '127.0.0.1':
                return node
            parts[0] = host
            parts[1] = '443'
            return f"{parse.scheme}://{encode_base64(':'.join(parts), urlsafe=True)}"
        if proxy_type in rewritable_node_types:
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            rewritten_info, changed = rewrite_info_host_port(decode_base64_if(info), host)
            if changed:
                return rewrite_node_url(node, rewritten_info)
    except Exception as e:
        print(f'127.0.0.1节点重写失败:{node} 错误信息:{str(e)}')
    return node
def fetch_remote_sub(url):
    try:
        try:
            response = requests.get(url, timeout=request_timeout)
        except requests.exceptions.SSLError as error:
            print(f'远程订阅证书校验失败，临时跳过校验重试:{url} 错误信息:{str(error)}')
            response = requests.get(url, timeout=request_timeout, verify=False)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f'获取远程订阅失败:{url} 错误信息:{str(e)}')
        return []
    text = decode_base64_if(response.text)
    host = get_remote_sub_host(url)
    return [rewrite_remote_node(line.strip(), host) for line in text.splitlines() if line.strip()]
class NodeParse():
    def __init__(self):
        # print('初始化')
        self.proxy_test = ''
    
    def vless(self):
        parse = urllib.parse.urlparse(self.proxy_test)
        # print(f'测试{parse}')
        query = urllib.parse.parse_qs(parse.query)
        # print(query)
        for key, value in query.items():
            query[key] = value[0]
        info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
        urlpath = decode_base64_if(info)  # uuid@服务器:端口
        uuid = decode_base64_if(urlpath.split('@')[0])  # uuid
        proxy_name = urllib.parse.unquote(parse.fragment)  # url解码
        server_port = urlpath.split('@')[1]  # 服务器:端口
        server = if_ipv6_address(server_port.rsplit(':', 1)[0])  # 服务器
        if Emoji:
            proxy_name = get_country_emoji(server) + proxy_name
        port = server_port.rsplit(':', 1)[1]  # 端口
        # vless配置
        proxy = {
            'name': proxy_name,
            'type': 'vless',
            'uuid': uuid,
            'server': server,
            'client-fingerprint': 'chrome',
            'port': int(port),
            'network': query.get('type'),
            'udp': Udp,
            'skip-cert-verify': SkipCert,
            'tfo': False,
            'tls': True if query.get('security') else False,
        }
        # 替换规则
        if query.get('fp'):
            proxy['client-fingerprint'] = query.get('fp')
        if query.get('sni'):
            proxy['servername'] = query.get('sni')
        if query.get('flow'):
            proxy['flow'] = query.get('flow')
        if query.get('security') == 'reality':
            proxy['reality-opts'] = {
                'public-key': query.get('pbk')
            }
            sid = query.get('sid')
            if sid:
                proxy['reality-opts']['short-id'] = sid
        if query.get('type') == 'ws':
            proxy['ws-opts'] = {
                'path': query.get('path')
            }
            host = query.get('host')
            if host:
                proxy['ws-opts']['headers'] = {'Host': host}
        if query.get('cert'):
            if query.get('cert').lower() == 'true':
                proxy['skip-cert-verify'] = True
            else:
                proxy['skip-cert-verify'] = False
        return proxy
    def vmess(self):
        parse = urllib.parse.urlparse(self.proxy_test)
        # parse = urllib.parse.urlparse(decode_base64_if(proxy_test))
        # print(f'测试{parse}')
        # print(f'类型{parse.query}')
        cert = None
        if parse.query != '':
            # print('非标准格式')
            query = urllib.parse.parse_qs(parse.query)
            info = decode_base64_if(parse.netloc)  # 加密方式:uuid@域名:端口
            for key, value in query.items():
                query[key] = value[0]
            name = query.get('remarks')
            uuid = info.split('@')[0].split(':')[1]
            server = info.split('@')[1].rsplit(':', 1)[0]
            port = int(info.split('@')[1].rsplit(':', 1)[1])
            aid = int(query.get('alterId'))
            cipher = info.split('@')[0].split(':')[0]
            network = 'ws' if query.get('obfs') == 'websocket' else ''
            tls = query.get('tls')
            pathA = query.get('path')
            host = query.get('obfsParam')
            if Emoji:
                name = get_country_emoji(server) + name
            cert = query.get('cert')
            # print(server, port, network, uuid, tls)
        else:
            info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
            proxy = json.loads(decode_base64_if(info))
            name = proxy.get('ps')
            uuid = proxy.get('id')
            server = proxy.get('add')
            port = int(proxy.get('port'))
            aid = int(proxy.get('aid'))
            cipher = proxy.get('scy') if proxy.get('scy') else 'auto'
            network = proxy.get('net')
            tls = proxy.get('tls')
            pathA = proxy.get('path')
            host = proxy.get('host')
            cert = proxy.get('cert')
            if Emoji:
                name = get_country_emoji(server) + name

        proxys = {
            'name': name,
            'type': 'vmess',
            'uuid': uuid,
            'server': server,
            'port': port,
            'client-fingerprint': 'chrome',
            'tfo': False,  # 是否启用 TCP Fast Open
            'udp': Udp,
            'skip-cert-verify': SkipCert,  # 是否跳过证书验证
            'alterId': aid,
            'cipher': cipher,
            'network': network,  # 代理的网络类型
            'tls': True if tls != 'none' and tls != '' else False
        }
        if cert:
            proxys['skip-cert-verify'] = str(cert).lower() == 'true'

        if network == 'ws':
            proxys['ws-opts'] = {
                'path': pathA,
            }
            # print(f'测试3{host}')
            if host != None and host != '':
                proxys['ws-opts']['headers'] = {
                    'Host': host
                }
        return proxys
    def ss(self):
        parse = urllib.parse.urlparse(self.proxy_test)
        info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
        urlpath = decode_base64_if(info)
        # print(f'测试{parse}')
        name = urllib.parse.unquote(parse.fragment)
        # print(urlpath)
        server = if_ipv6_address(urlpath.rsplit('@')[-1].rsplit(':', 1)[0])
        port = int(urlpath.rsplit('@')[-1].rsplit(':', 1)[1])
        index = urlpath.rfind("@")  # 找到最后一个 @ 符号的索引
        if Emoji:
            name = get_country_emoji(server) + name
        if index != -1:
            decode = decode_base64_if(urlpath[:index])
            # print('找到'+decode)
        else:
            decode = decode_base64_if(urlpath.split('@')[0])
            # print("未找到 @ 符号")
        # print(urlpath.split('@')[:-1])
        # decode = decode_base64_if(urlpath.split('@')[0])
        cipher = decode.split(':', maxsplit=2)[0]
        password = ':'.join(decode.split(':')[1:])
        # print(cipher, password)
        proxy = {
            'name': name,
            'type': 'ss',
            'server': server,
            'port': port,
            'cipher': cipher,
            'password': password,
            'client-fingerprint': 'chrome',
            'tfo': False,
            'udp': Udp,
            'skip-cert-verify': SkipCert
        }
        return proxy
    def ssr(self):
        parse = urllib.parse.urlparse(self.proxy_test.replace('-', '+').replace('_', '/'))
        # print(f'测试{parse}')
        info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
        # parse = urllib.parse.urlparse(decode_base64_if(proxy_test.replace('-', '+').replace('_', '/')))
        urlpath = decode_base64_if(info)
        query = urllib.parse.parse_qs(parse.query)
        port = int(urlpath.split(':')[1])
        protocol = urlpath.split(':')[2]
        cipher = urlpath.split(':')[3]
        obfs = urlpath.split(':')[4]
        server = if_ipv6_address(urlpath.split(':')[0])
        parse2 = urllib.parse.urlparse(urlpath.rsplit(':', 1)[1])
        password = decode_base64_if(parse2.path.replace('/', ''))
        query2 = urllib.parse.parse_qs(parse2.query)
        name = ""
        # print(query2.get('remarks'),query2 != '')
        if query.get('remarks'):
            name = decode_base64_if(query.get('remarks')[0])
        if query2.get('remarks'):
            name = decode_base64_if(query2.get('remarks')[0])
        if Emoji:
            name = get_country_emoji(server) + name
        proxy = {
            'name': name,
            'type': 'ssr',
            'server': server,
            'port': port,
            'protocol': protocol,
            'cipher': cipher,
            'obfs': obfs,
            'password': password,
            'udp': Udp,
            'skip-cert-verify': SkipCert
        }
        if query.get('cert'):
            if query.get('cert').lower() == 'true':
                proxy['skip-cert-verify'] = True
            else:
                proxy['skip-cert-verify'] = False
        return proxy
    def trojan(self):
        parse = urllib.parse.urlparse(self.proxy_test)
        info = parse.netloc + parse.path if parse.path != '/' else parse.netloc
        urlpath = decode_base64_if(info)
        # print(f'测试{parse}')
        name = urllib.parse.unquote(parse.fragment)
        query = urllib.parse.parse_qs(parse.query)
        password = urlpath.split('@')[0]
        server = if_ipv6_address(urlpath.split('@')[1].rsplit(':', 1)[0])
        port = int(urlpath.split('@')[1].rsplit(':', 1)[1])
        if Emoji:
            name = get_country_emoji(server) + name
        proxy = {
            'name': name,
            'type': 'trojan',
            'server': server,
            'port': port,
            'password': password,
            'client-fingerprint': 'chrome',
            'udp': Udp,
            'skip-cert-verify': SkipCert
        }
        for key, value in query.items():
            query[key] = value[0]
        if query.get('fp'):
            proxy['client-fingerprint'] = query.get('fp')
        if query.get('sni'):
            proxy['sni'] = query.get('sni')
        if query.get('flow'):
            proxy['flow'] = query.get('flow')
        if query.get('type'):
            if query.get('type') == 'ws':
                proxy['network'] = query.get('type')
                proxy['ws-opts'] = {
                    'path': query.get('path')
                }
                host = query.get('host')
                if host:
                    proxy['ws-opts']['headers'] = {'Host': host}
        if query.get('cert'):
            if query.get('cert').lower() == 'true':
                proxy['skip-cert-verify'] = True
            else:
                proxy['skip-cert-verify'] = False
        return proxy
    def hysteria(self):
        parse = urllib.parse.urlparse(self.proxy_test)
        # parse = urllib.parse.urlparse(decode_base64_if(proxy_test))
        urlpath = decode_base64_if(parse.netloc)
        # print(f'测试{parse}')
        name = urllib.parse.unquote(parse.fragment)
        query = urllib.parse.parse_qs(parse.query)
        server = if_ipv6_address(urlpath.split(':')[0])
        port = int(urlpath.split(':')[1])
        if Emoji:
            name = get_country_emoji(server) + name
        proxy = {
            'name': name,
            'type': 'hysteria',
            'server': server,
            'port': port,
            'client-fingerprint': 'chrome',
            'protocol': 'udp',
            'udp': Udp,
            'skip-cert-verify': SkipCert
        }
        for key, value in query.items():
            query[key] = value[0]
        if query.get('auth'):
            proxy['auth_str'] = query.get('auth')
        if query.get('upmbps'):
            proxy['up'] = query.get('upmbps')
        if query.get('downmbps'):
            proxy['down'] = query.get('downmbps')
        if query.get('alpn'):
            proxy['alpn'] = [query.get('alpn')]
        if query.get('peer'):
            proxy['sni'] = query.get('peer')
        if query.get('cert'):
            if query.get('cert').lower() == 'true':
                proxy['skip-cert-verify'] = True
            else:
                proxy['skip-cert-verify'] = False
        return proxy
    def hysteria2(self):
        parse = urllib.parse.urlparse(self.proxy_test)
        # parse = urllib.parse.urlparse(decode_base64_if(proxy_test))
        urlpath = decode_base64_if(parse.netloc)
        # print(f'测试{parse}')
        name = urllib.parse.unquote(parse.fragment)
        query = urllib.parse.parse_qs(parse.query)
        password = urlpath.split('@')[0]
        server = if_ipv6_address(urlpath.split('@')[1].rsplit(':', 1)[0])
        port = int(urlpath.split('@')[1].rsplit(':', 1)[1])
        if Emoji:
            name = get_country_emoji(server) + name
        proxy = {
            'name': name,
            'type': 'hysteria2',
            'server': server,
            'port': port,
            'password': password,
            'auth': password,
            'client-fingerprint': 'chrome',
            'udp': Udp,
            'skip-cert-verify': SkipCert
        }

        # proxy['skip-cert-verify'] = bool(query.get('cert', [str(SkipCert)])[0].capitalize())
        for key, value in query.items():
            query[key] = value[0]
        if query.get('sni'):
            proxy['sni'] = query.get('sni')
        if query.get('obfs') != 'none' and query.get('obfs') != None:
            proxy['obfs'] = query.get('obfs')
        if query.get('obfs-password'):
            proxy['obfs-password'] = query.get('obfs-password')
        if query.get('cert'):
            if query.get('cert').lower() == 'true':
                proxy['skip-cert-verify'] = True
            else:
                proxy['skip-cert-verify'] = False
        return proxy
def clash_encode(subs): #clash编码
    # 初始化 Clash 配置
    clash_config = {
            'proxies':[],
            'proxy-groups': []
        }
    proxy_name_list = []
    # 解析并添加节点到 Clash 配置
    for sub in subs:
        proxy_type = get_proxy_type(sub.node)  # 节点类型
        proxy_test = sub.node.strip()  # 节点信息
        # print(proxy_type,proxy_test)
        def clash():
            if proxy_type == 'vless':
                node_parse = NodeParse()  # 创建 NodeParse 实例
                node_parse.proxy_test = proxy_test
                proxy = node_parse.vless()
                clash_config['proxies'].append(proxy)
                proxy_name_list.append(proxy['name'])
            if proxy_type == 'vmess':
                node_parse = NodeParse()  # 创建 NodeParse 实例
                node_parse.proxy_test = proxy_test
                proxy = node_parse.vmess()
                clash_config['proxies'].append(proxy)
                proxy_name_list.append(proxy['name'])
            if proxy_type == 'ss':
                node_parse = NodeParse()  # 创建 NodeParse 实例
                node_parse.proxy_test = proxy_test
                proxy = node_parse.ss()
                clash_config['proxies'].append(proxy)
                proxy_name_list.append(proxy['name'])
            if proxy_type == 'ssr':
                node_parse = NodeParse()  # 创建 NodeParse 实例
                node_parse.proxy_test = proxy_test
                proxy = node_parse.ssr()
                clash_config['proxies'].append(proxy)
                proxy_name_list.append(proxy['name'])
            if proxy_type == 'trojan':
                node_parse = NodeParse()  # 创建 NodeParse 实例
                node_parse.proxy_test = proxy_test
                proxy = node_parse.trojan()
                clash_config['proxies'].append(proxy)
                proxy_name_list.append(proxy['name'])
            if proxy_type == 'hysteria':
                node_parse = NodeParse()  # 创建 NodeParse 实例
                node_parse.proxy_test = proxy_test
                proxy = node_parse.hysteria()
                clash_config['proxies'].append(proxy)
                proxy_name_list.append(proxy['name'])
            if proxy_type == 'hy2' or proxy_type == 'hysteria2':
                node_parse = NodeParse()  # 创建 NodeParse 实例
                node_parse.proxy_test = proxy_test
                proxy = node_parse.hysteria2()
                clash_config['proxies'].append(proxy)
                proxy_name_list.append(proxy['name'])
        def safe_clash():
            try:
                clash()
            except Exception as e:
                print(f'clash节点解析失败:{proxy_test} 错误信息:{str(e)}')

        if proxy_type in remote_sub_types:
            url = proxy_test
            for sub2 in fetch_remote_sub(url):
                proxy_type = get_proxy_type(sub2)
                proxy_test = sub2
                safe_clash()
        else:
            safe_clash()
    # 将 Clash 配置转为 YAML 格式
    with open(path + '/db/clash.yaml', 'r', encoding='utf-8') as file:
        data = yaml.safe_load(file)
        data['proxies'] = clash_config['proxies']
        proxy_groups = data.get('proxy-groups')

        for proxy_group in proxy_groups:
            for proxies in proxy_group['proxies']:
                if proxies == 'auto':  # 判断是否包含auto字符串
                    proxy_group['proxies'].remove('auto')
                    for name_list in proxy_name_list:
                        proxy_group['proxies'].append(name_list)
            # print(proxy_group['proxies'])
        # print(data)
        clash_config_yaml = yaml.dump(data, sort_keys=False, allow_unicode=True)
        return clash_config_yaml
def surge_encode(subs):
    # 初始化 Clash 配置
    surge_config = {
        'proxy': [],
    }
    proxy_name_list = []
    # 解析并添加节点到 Clash 配置
    for sub in subs:
        proxy_type = get_proxy_type(sub.node)  # 节点类型
        proxy_test = sub.node.strip()  # 节点信息
        def surge():
            if proxy_type == 'ss':
                node_parse = NodeParse()  # 创建 NodeParse 实例
                node_parse.proxy_test = proxy_test
                proxy = node_parse.ss()
                proxys = f"{proxy.get('name')} = ss, {proxy.get('server')}, {proxy.get('port')}, encrypt-method={proxy.get('cipher')}," \
                         f"password={proxy.get('password')}, tfo={proxy.get('tfo')}, udp-relay={proxy.get('udp')}"
                surge_config['proxy'].append(proxys)
                proxy_name_list.append(proxy['name'])
            if proxy_type == 'vmess':
                node_parse = NodeParse()  # 创建 NodeParse 实例
                node_parse.proxy_test = proxy_test
                proxy = node_parse.vmess()
                proxys = f"{proxy.get('name')} = vmess,{proxy.get('server')},{proxy.get('port')},username={proxy.get('uuid')}," \
                         f"tls={proxy.get('tls')},vmess-aead=true,skip-cert-verify={proxy.get('skip-cert-verify')},tfo={proxy.get('tfo')},udp-relay={proxy.get('udp')}"
                if proxy.get('network') == 'ws':
                    proxys += f",ws=true,ws-path={proxy['ws-opts']['path']},sni={proxy.get('server')}"
                    if proxy['ws-opts'].get('headers') != '' and proxy['ws-opts'].get('headers') != None:
                        proxys += f",ws-headers=Host:{proxy['ws-opts']['headers']['Host']}"
                surge_config['proxy'].append(proxys)
                proxy_name_list.append(proxy['name'])
            if proxy_type == 'trojan':
                node_parse = NodeParse()  # 创建 NodeParse 实例
                node_parse.proxy_test = proxy_test
                proxy = node_parse.trojan()
                proxys = f"{proxy.get('name')} = trojan,{proxy.get('server')},{proxy.get('port')},password={proxy.get('password')}," \
                         f"skip-cert-verify={proxy.get('skip-cert-verify')},tfo={proxy.get('tfo')},udp-relay={proxy.get('udp')}"
                if proxy.get('sni'):
                    proxys += f",sni={proxy['sni']}"
                if proxy.get('network') == 'ws':
                    proxys += f",ws=true,ws-path={proxy['ws-opts']['path']}"
                    if proxy['ws-opts'].get('headers') != '' and proxy['ws-opts'].get('headers') != None:
                        proxys += f",ws-headers=Host:{proxy['ws-opts']['headers']['Host']}"
                surge_config['proxy'].append(proxys)
                proxy_name_list.append(proxy['name'])
            if proxy_type == 'hy2' or proxy_type == 'hysteria2':
                node_parse = NodeParse()  # 创建 NodeParse 实例
                node_parse.proxy_test = proxy_test
                proxy = node_parse.hysteria2()
                proxys = f"{proxy.get('name')} = hysteria2,{proxy.get('server')},{proxy.get('port')},password={proxy.get('password')}," \
                         f"skip-cert-verify={proxy.get('skip-cert-verify')},udp-relay={proxy.get('udp')}"
                if proxy.get('sni'):
                    proxys += f",sni={proxy['sni']}"
                surge_config['proxy'].append(proxys)
                proxy_name_list.append(proxy['name'])
        def safe_surge():
            try:
                surge()
            except Exception as e:
                print(f'surge节点解析失败:{proxy_test} 错误信息:{str(e)}')
        if proxy_type in remote_sub_types:
            url = proxy_test
            for sub2 in fetch_remote_sub(url):
                proxy_type = get_proxy_type(sub2)
                proxy_test = sub2
                safe_surge()
        else:
            safe_surge()
    config_file = path + '/db/surge.conf'
    def add_key_value_to_proxy(new_key_value):
        with open(config_file, 'r', encoding='utf-8') as file:
            surge_config = file.read()
        # 找到 PROXY 节点的位置
        proxy_index = surge_config.find('[Proxy]')
        if proxy_index != -1:
            # 在 PROXY 节点的末尾添加新的键值对
            surge_config = surge_config[:proxy_index] + surge_config[proxy_index:].replace('[Proxy]',
                                                                                           f'[Proxy]\n{new_key_value}',
                                                                                           1)
        else:
            print("Proxy section not found in the configuration file.")

        return surge_config
    # 调用方法，传入配置文件路径和新的键值对
    config_text = add_key_value_to_proxy('\n'.join(surge_config['proxy']))
    autos = ','.join(proxy_name_list)
    config_text = re.sub('auto', autos, config_text)

    return config_text
@blue.route('/sub/<string:target>/<path:name>',methods=['GET']) #订阅地址
def get_sub_url(target,name):
    if request.method == 'GET':
        subs = Sub.query.filter_by(access_token=name).order_by(Sub.sort_order.asc(), Sub.id.asc()).all()
        if not subs:
            try:
                legacy_name = decode_base64_if_emoji(name)
            except Exception:
                return jsonify({'code': 400, 'msg': '订阅地址格式错误'}), 400
            subs = Sub.query.filter_by(name=legacy_name, legacy_enabled=True).order_by(
                Sub.sort_order.asc(), Sub.id.asc()
            ).all()
        # print(target, subs)
        if not subs:
            return jsonify({
                'code':400,
                'msg':'订阅不存在'
            })

        if target == 'clash':
            data = clash_encode(subs)
            response = make_response(
                send_file(BytesIO(data.encode('utf-8')), mimetype='text/plain', as_attachment=False,
                          download_name=SUBSCRIPTION_DOWNLOAD_NAME))

            # 设置响应头
            # response.headers['subscription-userinfo'] = 'total=22333829939200;remarks=123123'
            return response
        if target == 'v2ray':
            data = []
            for sub in subs:
                proxy_type = get_proxy_type(sub.node)  # 节点类型
                proxy_test = sub.node.strip()  # 节点信息
                if proxy_type in remote_sub_types:
                    url = proxy_test
                    data.extend(fetch_remote_sub(url))
                    continue
                if proxy_test:
                    data.append(proxy_test)
            encoded_node = base64.b64encode('\n'.join(data).encode('utf-8')).decode('utf-8')
            response = make_response(send_file(BytesIO(encoded_node.encode('utf-8')), mimetype='text/html', as_attachment=False,
                                    download_name=f'{SUBSCRIPTION_DOWNLOAD_NAME}.txt'))
            # response.headers['subscription-userinfo'] = 'remarks=22333829939200;'
            return response
        if target == 'surge':
            interval = f'#!MANAGED-CONFIG {request.url} interval=86400 strict=false' #更新时间
            data = interval + '\n' + surge_encode(subs)
            response = make_response(
                send_file(BytesIO(data.encode('utf-8')), mimetype='text/plain', as_attachment=False,
                          download_name=SUBSCRIPTION_DOWNLOAD_NAME))
            # response.headers['subscription-userinfo'] = 'remarks=22333829939200;'
            return response
        return jsonify({
            'code':400,
            'msg':'不支持的订阅类型'
        }), 400
@blue.route('/clash_config',methods=['POST']) #clash配置修改
@jwt_required()
def clash_config():
    if request.method == 'POST':
        data = request.get_json()
        index = data.get('index')
        # print(index)
        if index == 'read':
            with open(path + '/db/clash.yaml', 'r', encoding='utf-8') as file:
                return jsonify({
                    'code':200,
                    'msg':file.read()
                })
        if index == 'save':
            text = data.get('text')
            if text == '':
                return jsonify({
                    'code': 400,
                    'msg': '不能为空'
                })
            with open(path + '/db/clash.yaml', 'w', encoding='utf-8') as file:
                file.write(text)
                return jsonify({
                    'code':200,
                    'msg':'保存成功'
                })
@blue.route('/surge_config',methods=['POST']) #surge配置修改
@jwt_required()
def surge_config():
    if request.method == 'POST':
        data = request.get_json()
        index = data.get('index')
        # print(index)
        if index == 'read':
            with open(path + '/db/surge.conf', 'r', encoding='utf-8') as file:
                return jsonify({
                    'code':200,
                    'msg':file.read()
                })
        if index == 'save':
            text = data.get('text')
            if text == '':
                return jsonify({
                    'code': 400,
                    'msg': '不能为空'
                })
            with open(path + '/db/surge.conf', 'w', encoding='utf-8') as file:
                file.write(text)
                return jsonify({
                    'code':200,
                    'msg':'保存成功'
                })

@blue.route('/') #前台程序
def get_index():
    return render_template('index.html')
@blue.route('/login',methods=['POST'])
def get_login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({
                'code': 404,
                'msg': '账号不存在'
            })
        if user.username == username and user.password == password:
            access_token = create_access_token(identity=username)
            refresh_token = create_refresh_token(identity=username)
            save_ip_address() # 记录登录ip
            return jsonify({
                'code': 200,
                'token':access_token,
                'refresh':refresh_token,
                'msg': '登录成功'
            })
        else:
            return jsonify({
                'code':404,
                'msg':'账号或者密码错误'
            })
@blue.route('/refresh' ,methods=['POST']) #刷新令牌
@jwt_required(refresh=True)
def get_refresh():
    if request.method == 'POST':
        current_user = get_jwt_identity()
        if current_user:
            token = create_access_token(current_user)
            return token
        else:
            return '没获取到'
@blue.route('/create_sub',methods=['POST']) # 新建订阅
@jwt_required()
def get_create_sub():
    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        nodes = data.get('node')
        # print(name,nodes)
        if Sub.query.filter_by(name=name).first():
            return jsonify({
                'code':400,
                'msg':'订阅名字已经存在'
            })
        sort_order = get_next_sub_sort_order()
        access_token = new_access_token()
        for i in nodes:
            if len(i.split('|')) >= 2:
                node = i.split('|')[0]
                remarks = i.split('|')[1]
            else:
                node = i
                remarks = ''
            found = any(keyword in node for keyword in subname_list)
            # print(found, node)
            if node != '' and found:
                sub = Sub(name=name, node=node, remarks=remarks, sort_order=sort_order,
                          access_token=access_token, legacy_enabled=False)
                try:
                    db.session.add(sub)
                    db.session.commit()
                except Exception as e:
                    db.session.rollback()
                    db.session.flush()
                    return jsonify({
                        'code':400,
                        'msg':'错误信息：' + str(e)
                    })
        return jsonify({
            'code':200,
            'msg':'创建成功'
        })
            # print('节点：' + node)
            # print('备注：' + remarks)
@blue.route('/create_node',methods=['POST']) # 新建节点
@jwt_required()
def create_node():
    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        remarks = data.get('remarks')
        node = data.get('node')
        found = any(keyword in node for keyword in subname_list)
        # print(node,found)
        if not found:
            return jsonify({
                'code': 400,
                'msg': '不是有效的协议,请检查后重新输入'
            })
        if node != '':
            current_sub = Sub.query.filter_by(name=name).order_by(Sub.id.asc()).first()
            sub = Sub(
                name=name,
                node=node,
                remarks=remarks,
                sort_order=current_sub.sort_order if current_sub else get_next_sub_sort_order(),
                access_token=current_sub.access_token if current_sub else new_access_token(),
                legacy_enabled=current_sub.legacy_enabled if current_sub else False
            )
            try:
                db.session.add(sub)
                db.session.commit()
                return jsonify({
                    'code': 200,
                    'msg': '创建成功'
                })
            except Exception as e:
                db.session.rollback()
                db.session.flush()
                return jsonify({
                    'code':400,
                    'msg':'错误信息：' + str(e)
                })
@blue.route('/get_subs',methods=['POST']) #获取所有的订阅
@jwt_required()
def get_subs():
    if request.method == 'POST':
        subs = Sub.query.order_by(Sub.sort_order.asc(), Sub.id.asc()).all()
        for name in {sub.name for sub in subs}:
            ensure_access_token(name)
        if subs:
            subs = Sub.query.order_by(Sub.sort_order.asc(), Sub.id.asc()).all()
        data = []
        for sub in subs:
            item = {
                'id':sub.id,
                'name':sub.name,
                'node':sub.node,
                'remarks':sub.remarks if sub.remarks !='' else '无备注',
                'sort_order':sub.sort_order,
                'access_token':sub.access_token,
                'legacy_enabled':sub.legacy_enabled
            }
            data.append(item)
        return jsonify(data)
@blue.route('/rename_sub/<path:name>',methods=['POST']) #修改订阅名称
@jwt_required()
def rename_sub(name):
    if request.method == 'POST':
        subs = Sub.query.filter_by(name=name).all()
        data = request.get_json()
        newName = data.get('newName')
        if Sub.query.filter_by(name=newName).first():
            return jsonify({
                'code': 400,
                'msg': f'名字已存在'
            })
        for sub in subs:
            sub.name = newName
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                db.session.flush()
                return jsonify({
                    'code': 400,
                    'msg':f'错误{str(e)}'
                })
        return jsonify({
            'code':200,
            'msg':'成功'
        })
@blue.route('/get_sub/<path:name>',methods=['POST']) #获取单个订阅
@jwt_required()
def get_sub(name):
    if request.method == 'POST':
        subs = Sub.query.filter_by(name=name).order_by(Sub.sort_order.asc(), Sub.id.asc()).all()
        data = []
        for sub in subs:
            item = {
                'id':sub.id,
                'name':sub.name,
                'node':sub.node,
                'remarks':sub.remarks if sub.remarks !='' else 'null',
                'access_token':sub.access_token
            }
            data.append(item)
        return jsonify(data)
@blue.route('/del_sub/<path:name>',methods=['POST']) #删除指定订阅
@jwt_required()
def del_sub(name):
    if request.method == 'POST':
        # print(name)
        subs = Sub.query.filter_by(name=name).all()
        # print(name,subs)
        if not subs:
            return jsonify({
                'code': 400,
                'msg': '不存在'
            })
        for sub in subs:
            try:
                db.session.delete(sub)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                db.session.flush()
                return jsonify({
                    'code': 400,
                    'msg': '错误信息:'+str(e)
                })
        return jsonify({
            'code': 200,
            'msg': '删除成功'
        })
@blue.route('/del_sub_node/<int:id>',methods=['POST']) #删除指定节点
@jwt_required()
def del_sub_node(id):
    if request.method == 'POST':
        sub = Sub.query.filter_by(id=id).first()
        if not Sub:
            return jsonify({
                'code': 400,
                'msg': '不存在'
            })
        try:
            db.session.delete(sub)
            db.session.commit()
            return jsonify({
                'code': 200,
                'msg': '删除成功'
            })
        except Exception as e:
            db.session.rollback()
            db.session.flush()
            return jsonify({
                'code': 400,
                'msg': '错误信息:'+str(e)
            })
@blue.route('/set_sub',methods=['POST']) # 修改节点
@jwt_required()
def get_set_sub():
    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        newNodes = data.get('newNode') or []
        subs = Sub.query.filter_by(name=name).order_by(Sub.id.asc()).all()
        if not subs:
            return jsonify({'code': 400, 'msg': '订阅不存在'})
        sort_order = subs[0].sort_order if subs else get_next_sub_sort_order()
        access_token = subs[0].access_token if subs else new_access_token()
        legacy_enabled = subs[0].legacy_enabled if subs else False
        parsed_nodes = []
        for item in newNodes:
            node, separator, remarks = item.partition('|')
            node = node.strip()
            remarks = remarks.strip() if separator else ''
            if not node:
                continue
            if not any(keyword in node for keyword in subname_list):
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
            return jsonify({'code': 400, 'msg': '错误信息：' + str(e)})
@blue.route('/sort_subs', methods=['POST'])
@jwt_required()
def sort_subs():
    names = request.get_json().get('names', [])
    if not isinstance(names, list) or len(names) != len(set(names)):
        return jsonify({'code': 400, 'msg': '订阅排序数据不正确'})
    existing_names = [row[0] for row in db.session.query(Sub.name).distinct().all()]
    if set(names) != set(existing_names):
        return jsonify({'code': 400, 'msg': '订阅列表已变化，请刷新后重试'})
    try:
        for sort_order, name in enumerate(names):
            Sub.query.filter_by(name=name).update({'sort_order': sort_order})
        db.session.commit()
        return jsonify({'code': 200, 'msg': '订阅排序已保存'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 400, 'msg': '错误信息：' + str(e)})
@blue.route('/set_sub_legacy/<path:name>', methods=['POST'])
@jwt_required()
def set_sub_legacy(name):
    data = request.get_json(silent=True) or {}
    enabled = data.get('enabled')
    if not isinstance(enabled, bool):
        return jsonify({'code': 400, 'msg': '旧地址兼容状态不正确'})
    if not Sub.query.filter_by(name=name).first():
        return jsonify({'code': 400, 'msg': '订阅不存在'})
    try:
        Sub.query.filter_by(name=name).update(
            {'legacy_enabled': enabled}, synchronize_session=False
        )
        db.session.commit()
        return jsonify({
            'code': 200,
            'msg': '旧地址兼容已开启' if enabled else '旧地址兼容已关闭'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'code': 400, 'msg': '错误信息：' + str(e)})
@blue.route('/set_node',methods=['POST']) # 修改单个节点
@jwt_required()
def get_set_node():
    if request.method == 'POST':
        data = request.get_json()
        id = data.get('id')
        node = data.get('node')
        remarks = data.get('remarks')
        sub = Sub.query.filter_by(id=id).first()
        found = any(keyword in node for keyword in subname_list)
        if not found:
            return jsonify({
                'code': 400,
                'msg': '节点格式不对'
            })
        if sub:
            sub.node = node
            sub.remarks = remarks
            try:
                db.session.commit()
                return jsonify({
                    'code': 200,
                    'msg': '修改成功'
                })
            except Exception as e:
                db.session.rollback()
                db.session.flush()
                return jsonify({
                    'code': 400,
                    'msg': '错误信息：' + str(e)
                })
@blue.route('/set_user',methods=['POST']) # 修改账号信息
@jwt_required()
def get_set_user():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        newUserName = data.get('newUserName')
        password = data.get('password')
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({
                'code':400,
                'msg':'账号不正确'
            })
        user.username = newUserName
        user.password = password
        try:
            db.session.commit()
            return jsonify({
                'code': 200,
                'msg': '修改成功'
            })
        except Exception as e:
            db.session.rollback()
            db.session.flush()
            return jsonify({
                'code': 400,
                'msg': '错误信息:'+str(e)
            })
@blue.route('/decode_sub',methods=['POST']) # 订阅解析
@jwt_required()
def decode_sub():
    if request.method == 'POST':
        data = request.get_json()
        urls = data.get('urls')
        datas = []
        for url in urls:
            response = requests.get(url)
            # print(response.status_code)
            if response.status_code == 200:
                print(decode_base64_if(response.text))
                datas.append(decode_base64_if(response.text))
            else:
                return jsonify({
                    'code': response.status_code,
                    'msg': response.text
                })
        return jsonify({
            'code': 200,
            'msg': datas
        })
@blue.route('/get_ip_address',methods=['POST']) # 获取已经登录过的ip记录
@jwt_required()
def get_ip_address():
    if request.method == 'POST':
        logins = Login.query.order_by(Login.time.desc()).all()
        data = []
        for i in logins:
            login = {
                'id':i.id,
                'ip':i.ip,
                'address':i.address,
                'time':i.time
            }
            data.append(login)
        return jsonify(data)
@blue.route("/set_conifg",methods=['POST'])
@jwt_required()
def set_config():
    if request.method == 'POST':
        data = request.get_json()
        udp = data.get('udp')
        skipcert = data.get('skipcert')
        emoji = data.get('emoji')
        list = [('udp',udp),('skipcert',skipcert),('emoji',emoji)]
        for key,value in list:
            Config.query.filter_by(key=key).delete()
            config = Config(key=key,value=value)
            db.session.add(config)
        try:
           db.session.commit()
           global SkipCert,Udp,Emoji
           SkipCert = bool(skipcert)
           Udp = bool(udp)
           Emoji = bool(emoji)
           return jsonify({
               'code':200,
               'msg':'设置保存成功'
           })
        except Exception as e:
              db.session.rollback()
              db.session.flush()
              return jsonify({
                'code':400,
                'msg':'错误信息：'+str(e)
              })
@blue.route("/get_conifg",methods=['POST'])
@jwt_required()
def get_config():
    if request.method == 'POST':
        config = Config.query.all()
        data = {}
        global SkipCert,Udp,Emoji
        for i in config:
            data[i.key] = True if i.value == '1' else False
            if i.key == 'udp':
                Udp = True if i.value == '1' else False
            if i.key == 'emoji':
                Emoji = True if i.value == '1' else False    
            if i.key == 'skipcert':
                SkipCert = True if i.value == '1' else False
        print(Udp,SkipCert,Emoji)
        return jsonify(data)
SkipCert = False
Udp = False
Emoji = False
