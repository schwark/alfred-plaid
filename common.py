import subprocess
from time import sleep
import re
from workflow import PasswordNotFound, web
import json
import os.path
from os import listdir
from os.path import isfile, join, splitext
import base64
from dateutil.parser import parse 


SERVER_HOST='localhost'
SERVER_PORT=8383
SERVER_PROTOCOL='http'
DEFAULT_ENV = 'sandbox'
SECURE_STORE = 'plaid_secure'
ALL_ENV = 'global'
ALL_USER = 'config'
CERT_FILE = 'cert.pem'
KEY_FILE = 'key.pem'
STORAGE = None
ICONS_DEFAULT = {'merchant': {},'category': {},'bank': {}}

def download_file(filename, url):
    r = web.get(url, allow_redirects=True)
    r.save_to_path(filename)

def ensure_icon(wf, dir, site, type, url=None):
    if not site: return None
    site = re.sub(r'[^a-z0-9]','',site.lower())
    size = 64
    dir = ensure_icon_dir(dir, type)
    icon = f'{dir}/{site}.png'
    if not os.path.exists(icon):
        if url and 'bank' == type and not url.startswith('http'): # base64 encoded image
            with open(icon, "wb") as fh:
                fh.write(base64.urlsafe_b64decode(url))
        else:
            url = url if url else (f'https://www.google.com/s2/favicons?domain={site}.com&sz={size}' if 'category' != type else None)
            if url:
                try:
                    download_file(icon, url)
                except Exception as e:
                    wf.logger.debug(e)
                    pass
    return icon if os.path.exists(icon) else '' # to differentiate from None which means never tried

def get_icon(wf, type, icon, icons=None, url=None, force=False):
    #wf.logger.debug(f"getting icon for {type} and {icon}")
    base_dir = wf.datafile(f'{get_environment(wf)}.icons')
    icon = re.sub(r'[^a-z0-9]', '', icon.lower())
    icons = get_stored_data(wf, 'icons', ICONS_DEFAULT) if not icons else icons
    if force or not icons[type]:
        dirs = [f"{base_dir}/{type}/", f"icons/{type}/"]
        for dir in dirs:
            files = [f for f in (listdir(dir) if os.path.exists(dir) else []) if isfile(join(dir, f))]
            for f in files:
                icons[type][splitext(f)[0]] = join(dir,f)
        set_stored_data(wf, 'icons', icons)
        
    result = icons[type][icon] if icon in icons[type] else None
    #wf.logger.debug(f"result is {result}")
    #if result is None and url:
    if not result:
        result = ensure_icon(wf, base_dir, icon, type, url)
        if result is not None: 
            icons[type][icon] = result
    return result

def category_name(wf, category_id, full=False):
    categories = get_stored_data(wf, 'categories', {})
    names = categories[category_id]['list']
    return ','.join(names) if full else names[-1]

def get_bank_icon(wf, institution_id, banks, icons):
    if not institution_id: return None
    bank = banks[institution_id]
    if not 'icon' in bank or not bank['icon']:
        name = bank['name']
        logo = bank['logo']
        banks[institution_id]['icon'] = get_icon(wf, 'bank', name, icons, logo)
    return banks[institution_id]['icon']

def get_merchant_icon(wf, merchant_id, merchants, icons):
    if not merchant_id: return None
    if not 'icon' in merchants[merchant_id]:
        merchant = merchants[merchant_id]['name']
        merchant_url = merchants[merchant_id]['logo']
        merchants[merchant_id]['icon'] = get_icon(wf, 'merchant', merchant, icons, merchant_url)
    return merchants[merchant_id]['icon']

def get_category_icon(wf, category_id, categories, icons):
    if not category_id: return None
    category_id = int(category_id)
    if not 'icon' in categories[category_id]:
        categories[category_id]['icon'] = None
        cats = categories[category_id]['list']
        for i in range(len(cats), 0, -1):
            if categories[category_id]['icon']: break
            #wf.logger.debug(cats)
            cat = cats[i-1]
            words = re.split(r'\s+|\'|,', cat)
            for i in range(len(words),0,-1):
                if categories[category_id]['icon']: break
                substr = ''.join(words[0:i])
                if "s" == substr[-1]: substr = substr[:-1]
                icon = get_icon(wf, 'category', substr.lower(), icons)
                if icon: 
                    categories[category_id]['icon'] = icon
            for i in range(len(words)):
                if categories[category_id]['icon']: break
                substr = ''.join(words[-(i+1):])
                if "s" == substr[-1]: substr = substr[:-1]
                icon = get_icon(wf, 'category', substr.lower(), icons)
                if icon: 
                    categories[category_id]['icon'] = icon
    return categories[category_id]['icon']

def get_db_file(wf):
    return wf.datafile(get_environment(wf)+'.db')

def get_protocol(wf):
    return wf.settings['protocol'] if 'protocol' in wf.settings else SERVER_PROTOCOL

def get_link_func(wf):
    proto = get_protocol(wf)
    return lambda x: f'{proto}://{SERVER_HOST}:{SERVER_PORT}/link.html?link_token={x}'

def get_environment(wf):
    return wf.settings['environment'] if 'environment' in wf.settings else DEFAULT_ENV

def ensure_icon_dir(dir, type):
    dir = f'{dir}/{type}'
    if not os.path.exists(dir):
        os.makedirs(dir)
    return dir

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
        url = get_current_url(wf).lower()
        done = (url and 'missing value' not in url and ('completed=true' in url or ('localhost' not in url and 'plaid' not in url))) or tries > 300
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
    name = f"{get_environment(wf)}.{name}"
    try:
        data = wf.stored_data(name)
    except ValueError:
        pass
    return data if data else default

def set_stored_data(wf, name, data):
    name = f"{get_environment(wf)}.{name}"
    wf.store_data(name, data)

def get_current_user(wf):
    return get_secure_value(wf, 'current_user', None, ALL_USER)

def set_current_user(wf, user):
    set_secure_value(wf, 'current_user', user, ALL_USER)

def get_password(wf, name):
    try:
        items = wf.get_password(name)
    except PasswordNotFound:  # Access Token has not yet been set
        items = '{}'
    items = json.loads(items)
    return items

def save_password(wf, name, value):
    wf.save_password(name, json.dumps(value))
      
def get_storage(wf):
    global STORAGE
    if not STORAGE: STORAGE = get_password(wf, SECURE_STORE)
    return STORAGE

def save_storage(wf):
    global STORAGE
    save_password(wf, SECURE_STORE, STORAGE)

# global values are under env='global'
# across user values are under user='config'
def get_secure_value(wf, key, default=None, user=None, env=None):
    user = user if user else get_current_user(wf)
    env = env if env else get_environment(wf)
    storage = get_storage(wf)
    if env not in storage: return default
    if user and user not in storage[env]: return default
    store = storage[env][user] if user else storage[env]
    if key not in store: return default
    return store[key]

# global values are under env='global'
# across user values are under user='config'
def set_secure_value(wf, key, value, user=None, env=None):
    global STORAGE
    user = user if user else get_current_user(wf)
    env = env if env else get_environment(wf)
    if not STORAGE: STORAGE = {}
    if env not in STORAGE: STORAGE[env] = {}
    if user and user not in STORAGE[env]: STORAGE[env][user] = {}
    store = STORAGE[env][user] if user else STORAGE[env]
    if key not in store: store[key] = {}
    store[key] = value
    save_storage(wf)
        
def reset_secure_values(wf):
    global STORAGE
    STORAGE = {}
    save_storage(wf)
    
def get_category(wf, txn, custom_cats=None):
    merchant_id = (txn['merchant_entity_id'] if 'merchant_entity_id' in txn else None) if type(txn) is dict else txn['merchant_id']
    merchant = (txn['merchant_name'] if 'merchant_name' in txn else None) if type(txn) is dict else txn['merchant']
    txntext = (txn['name'] if 'name' in txn else None) if type(txn) is dict else txn['txntext']
    merchant = merchant if merchant else txntext
    category_id = int(txn['category_id'])
    id = merchant_id if merchant_id else merchant
    custom_categorization = get_stored_data(wf, 'custom_categorization', {}) if custom_cats is None else custom_cats
    return int(custom_categorization[id] if custom_categorization and id in custom_categorization else category_id)

def set_category(wf, id, category_id):
    custom_categorization = get_stored_data(wf, 'custom_categorization', {})
    custom_categorization[id] = category_id
    set_stored_data(wf, 'custom_categorization', custom_categorization)

def extract_filter(query, token, type):
    result = None
    extract = re.findall(fr"{token}\:([^\s]+)",query)
    if extract:
        result = extract[0]
        query = query.replace(f"{token}:{result}",'').replace(r'\s+',' ').strip()
        if('date' == type):
            result = parse(result)
        elif('number' == type):
            result = int(result)
        elif('text' == type):
            pass
    return query,result