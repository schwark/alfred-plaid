import subprocess
from time import sleep
import re
from workflow import Workflow, ICON_WEB, ICON_NOTE, ICON_BURN, ICON_SWITCH, ICON_HOME, ICON_COLOR, ICON_INFO, ICON_SYNC, web, PasswordNotFound
import json
import os.path
from urllib.request import urlretrieve
import shutil

SERVER_HOST='localhost'
SERVER_PORT=8383
SERVER_PROTOCOL='http'
DEFAULT_ENV = 'sandbox'
DB_FILE = 'txns.db'
SECURE_STORE = 'plaid_secure'
ALL_ENV = 'global'
ALL_USER = 'config'
CERT_FILE = 'cert.pem'
KEY_FILE = 'key.pem'

def get_protocol(wf):
    return wf.settings['protocol'] if 'protocol' in wf.settings else SERVER_PROTOCOL

def get_link_func(wf):
    proto = get_protocol(wf)
    return lambda x: f'{proto}://{SERVER_HOST}:{SERVER_PORT}/link.html?link_token={x}'

def get_environment(wf):
    return wf.settings['environment'] if 'environment' in wf.settings else DEFAULT_ENV

def ensure_icon_dir(datadir, type):
    dir = f'{datadir}/icons/{type}'
    if not os.path.exists(dir):
        if 'category' == type:
            shutil.copytree(f'icons/{type}', f'{datadir}/icons/')
        else:
            os.makedirs(dir)
    return dir

def ensure_icon(datadir, site, type, url=None):
    if not site: return None
    site = site.lower().replace(r'[^a-z0-9]','')
    size = 64
    dir = ensure_icon_dir(datadir, type)
    icon = f'{dir}/{site}.png'
    if not os.path.exists(icon):
        #url = url if url else f'https://icon.horse/icon/{site}.com'
        url = url if url else (f'https://www.google.com/s2/favicons?domain={site}.com&sz={size}' if 'category' != type else None)
        if url:
            try:
                urlretrieve(url, icon)
            except:
                pass
    return icon if os.path.exists(icon) else None

def get_cmd_output(cmd, wf=None):
    output = (subprocess.check_output(cmd, shell=True)).decode('utf-8')
    if wf: wf.logger.debug(f'{cmd} : {output}')
    return output
    
def open_url(wf, url):
    wf.logger.debug(f'opening url in Safari... {url}')
    get_cmd_output(f'open -a Safari "{url}"', wf)
    
def get_current_url(wf):
    url = get_cmd_output("osascript -e 'tell application \"Safari\" to get URL of front document'", wf)
    wf.logger.debug(f'current url is {url}')
    return url

def wait_for_public_token(wf):
    done = False
    tries = 0
    url = None
    token = None
    while(not done):
        tries = tries + 1
        url = get_current_url(wf)
        done = (url and 'missing value' not in url and ('completed=true' in url or 'localhost' not in url)) or tries > 300
        sleep(1)
    if(url):
        parts = re.search('public_token=([^&]+)', url, re.IGNORECASE)
        if(parts): token = parts.group(1)
    return token
     
def qnotify(title, text):
    print(text)

def error(text):
    print(text)
    exit(0)

def get_stored_data(wf, name, default={}):
    try:
        data = wf.stored_data(name)
    except ValueError:
        pass
    return data if data else default

def get_current_user(wf):
    return wf.settings['user'] if 'user' in wf.settings else None

def set_current_user(wf, user):
    wf.settings['user'] = user

def get_password(wf, name):
    try:
        items = wf.get_password(name)
    except PasswordNotFound:  # Access Token has not yet been set
        items = '{}'
    items = json.loads(items)
    return items

def save_password(wf, name, value):
    wf.save_password(name, json.dumps(value))

# global values are under env='global'
# across user values are under user='config'
def get_secure_value(wf, key, default=None, user=None, env=None):
    user = user if user else get_current_user(wf)
    env = env if env else get_environment(wf)
    storage = get_password(wf, SECURE_STORE)
    if env not in storage: return default
    if user and user not in storage[env]: return default
    store = storage[env][user] if user else storage[env]
    if key not in store: return default
    return store[key]

# global values are under env='global'
# across user values are under user='config'
def set_secure_value(wf, key, value, user=None, env=None):
    user = user if user else get_current_user(wf)
    env = env if env else get_environment(wf)
    storage = get_password(wf, SECURE_STORE)
    if env not in storage: storage[env] = {}
    if user and user not in storage[env]: storage[env][user] = {}
    store = storage[env][user] if user else storage[env]
    if key not in store: store[key] = {}
    current = store[key]
    if current != value:
        store[key] = value
        save_password(wf, SECURE_STORE, storage)   
        
def reset_secure_values(wf):
    save_password(wf, SECURE_STORE, {}) 
