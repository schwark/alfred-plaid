import subprocess
from time import sleep
import re
from workflow import Workflow, ICON_WEB, ICON_NOTE, ICON_BURN, ICON_SWITCH, ICON_HOME, ICON_COLOR, ICON_INFO, ICON_SYNC, web, PasswordNotFound
import json
import os.path
from urllib.request import urlretrieve

SERVER_HOST='localhost'
SERVER_PORT=8383
USE_HTTPS=False
LINK_URL= lambda x: f'http{'s' if USE_HTTPS else ''}://{SERVER_HOST}:{SERVER_PORT}/link.html?link_token={x}'
DEFAULT_ENV = 'sandbox'
DB_FILE = 'txns.db'

def get_environment(wf):
    environ = get_stored_data(wf, 'plaid_environment')
    environ = DEFAULT_ENV if not environ else environ.decode('utf-8')
    return environ

def ensure_icon(site, type, url=None):
    if not site: return None
    site = site.lower().replace(r'[^a-z0-9]','')
    size = 32
    icon = f'icons/{type}/{site}.png'
    if not os.path.exists(icon):
        #url = url if url else f'https://icon.horse/icon/{site}.com'
        url = url if url else (f'https://www.google.com/s2/favicons?domain={site}.com&sz={size}' if 'category' != type else None)
        if url:
            try:
                urlretrieve(url, icon)
            except:
                pass
    return icon if os.path.exists(icon) else None

def get_cmd_output(wf, cmd):
    output = (subprocess.check_output(cmd, shell=True)).decode('utf-8')
    wf.logger.debug(f'{cmd} : {output}')
    return output
    
def open_url(wf, url):
    wf.logger.debug(f'opening url in Safari... {url}')
    get_cmd_output(wf, f'open -a Safari "{url}"')
    
def get_current_url(wf):
    url = get_cmd_output(wf, "osascript -e 'tell application \"Safari\" to get URL of front document'")
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
        done = (url and 'completed=true' in url) or tries > 300
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

def get_password(wf, name):
    try:
        items = wf.get_password(name)
    except PasswordNotFound:  # Access Token has not yet been set
        items = '{}'
    items = json.loads(items)
    return items

def save_password(wf, name, value):
    wf.save_password(name, json.dumps(value))
