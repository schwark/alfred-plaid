# encoding: utf-8

import sys
import argparse
from workflow import Workflow, PasswordNotFound
from common import qnotify, error, get_stored_data, open_url, wait_for_public_token, get_link_func, CERT_FILE, KEY_FILE, set_stored_data, ICONS_DEFAULT
from plaid import Plaid
from server import run_server, stop_server
from common import get_environment, get_secure_value, set_secure_value, set_current_user, ALL_ENV, ALL_USER, reset_secure_values, get_current_user, get_db_file, get_protocol, set_category, get_category, category_name, get_category_icon, get_bank_icon
from db import TxnDB
from time import time

log = None

def change_env(wf, env):
    wf.settings['environment'] = env
    
def update_items(wf, plaid):
    items = get_secure_value(wf, 'items', {})
    banks = get_stored_data(wf, 'banks', {})
    icons = get_stored_data(wf, 'icons', ICONS_DEFAULT)
    for item_id in items:
        item = items[item_id]
        result = plaid.get_item(item['access_token'])
        item['institution_id'] = result['item']['institution_id']
        item['error'] = result['item']['error']
        item['consent_expiration_time'] = result['item']['consent_expiration_time']
        items[item['item_id']] = item
        if item['institution_id'] not in banks:
            bank = plaid.get_institution_by_id(item['institution_id'])
            if bank:
                banks[item['institution_id']] = bank
                banks[item['institution_id']]['icon'] = get_bank_icon(wf, item['institution_id'], banks, icons)
    set_secure_value(wf, 'items', items)
    set_stored_data(wf, 'banks', banks)
    set_stored_data(wf, 'icons', icons)

def add_item(wf, item):
    if not item: return
    items = get_secure_value(wf, 'items', {})
    items[item['item_id']] = item
    set_secure_value(wf, 'items', items)
    
def update_categories(wf, plaid):
    log.debug('updating categories...')
    categories = get_stored_data(wf, 'categories', {})
    icons = get_stored_data(wf, 'icons', ICONS_DEFAULT)
    newcats = plaid.get_categories(wf)
    categories = {**categories, **newcats}
    for category_id in categories:
        icon = get_category_icon(wf, category_id, categories, icons)
        if icon: categories[category_id]['icon'] = icon
    categories[0] = {'id': 0, 'list':[], 'icon': None}
    #log.debug(categories)
    set_stored_data(wf, 'categories', categories)
    set_stored_data(wf, 'icons', icons)
    return categories

def reset_cursors(wf):
    items = get_secure_value(wf, 'items', {})
    for item in items:
        items[item]['txn_cursor'] = None
    set_secure_value(wf, 'items', items)

def update_transactions(wf, plaid):
    log.debug('updating transactions...')
    txns = None
    db = TxnDB(get_db_file(wf), wf.logger)
    
    start = time()
    update_items(wf, plaid)
    log.debug(f"{(time() - start):0.3f} to update items")
    start = time()
    items = get_secure_value(wf, 'items', {})
    accounts = get_secure_value(wf, 'accounts', {})
    nicks = get_secure_value(wf, 'nicks', {})
    merchants = get_stored_data(wf, 'merchants', {})
    categories = get_stored_data(wf, 'categories', {})
    banks = get_stored_data(wf, 'banks', {})
    log.debug(f"{(time() - start):0.3f} to load stored data")
    if 0 not in categories:
        start = time()
        categories = update_categories(wf, plaid)
        log.debug(f"{(time() - start):0.3f} to update categories")
    if not items:
        log.debug('No items found. Please add items first..')
        qnotify('Plaid', 'No Items Found!')
    for item_id in items:
        try:
            log.debug('updating item '+item_id)
            single = items[item_id]
            if items[item_id]['error']: 
                log.debug(f"{banks[single['institution_id']]['name']} has an error.. Skipping..")
                qnotify('Plaid', f"{banks[single['institution_id']]['name']} needs auth update")
                continue
            start = time()
            actlist = plaid.get_accounts(single, banks)
            log.debug(f"{(time() - start):0.3f} to get accounts")
            if 'ITEM_LOGIN_REQUIRED' == actlist:
                items[item_id]['error'] = actlist
                log.debug(f'{item_id} item has error {actlist}')
                qnotify('Plaid', f"{banks[single['institution_id']]['name']} needs auth update")
            elif type(actlist) is list and 'error' in items[item_id] and items[item_id]['error']:
                items[item_id]['error'] = None
            for i in range(len(actlist)):
                log.debug(actlist[i])
                if actlist[i]['account_id'] in nicks:
                    actlist[i]['nick'] = nicks[actlist[i]['account_id']]
                accounts[actlist[i]['account_id']] = actlist[i]
            start = time()
            txns = plaid.get_transactions(single, merchants)
            for t in txns:
                log.debug(t)
                db.save_txn(t, wf)
            log.debug(f"{(time() - start):0.3f} to get and save transactions")
        except: 
            pass
    set_secure_value(wf, 'items', items)            
    set_secure_value(wf, 'accounts', accounts)
    set_stored_data(wf, 'merchants', merchants)
    set_stored_data(wf, 'categories', categories)
    set_stored_data(wf, 'banks', banks)
    return txns
    
def main(wf):
    # build argument parser to parse script args and collect their
    # values
    parser = argparse.ArgumentParser()
    # add an optional (nargs='?') --apikey argument and save its
    # value to 'apikey' (dest). This will be called from a separate "Run Script"
    # action with the API key
    parser.add_argument('--clientid', dest='clientid', nargs='?', default=None)
    parser.add_argument('--secret', dest='secret', nargs='?', default=None)
    parser.add_argument('--userid', dest='userid', nargs='?', default=None)
    parser.add_argument('--pubtoken', dest='pubtoken', nargs='?', default=None)
    parser.add_argument('--environment', dest='environment', nargs='?', default=None)
    parser.add_argument('--proto', dest='proto', nargs='?', default=None)
    parser.add_argument('--category_id', dest='category_id', nargs='?', default=None)
    parser.add_argument('--merchant_id', dest='merchant_id', nargs='?', default=None)
    parser.add_argument('--merchant', dest='merchant', nargs='?', default=None)
    parser.add_argument('--txntext', dest='txntext', nargs='?', default=None)
    parser.add_argument('--acctid', dest='acctid', nargs='?', default=None)
    parser.add_argument('--nick', dest='nick', nargs='?', default=None)
    parser.add_argument('--filter', dest='filter', action='store_true', default=False)
    # add an optional (nargs='?') --update argument and save its
    # value to 'apikey' (dest). This will be called from a separate "Run Script"
    # action with the API key
    parser.add_argument('--update', dest='update', action='store_true', default=False)
    parser.add_argument('--refresh', dest='refresh', nargs='?', default=False)
    parser.add_argument('--upcat', dest='upcat', action='store_true', default=False)
    parser.add_argument('--link', dest='link', nargs='?', default=None)
    parser.add_argument('--kill', dest='kill', action='store_true', default=False)
    # reinitialize 
    parser.add_argument('--reinit', dest='reinit', action='store_true', default=False)
    parser.add_argument('--clear', dest='clear', action='store_true', default=False)

    # add an optional query and save it to 'query'
    parser.add_argument('query', nargs='?', default=None)
    # parse the script's arguments
    args = parser.parse_args(wf.args)

    log.debug("args are "+str(args))

    words = args.query.split(' ') if args.query else []

    # list of commands
    commands = {
    }
    
    if args.clear or args.reinit:
        current_environment = get_environment(wf)
        reset_cursors(wf)
        set_secure_value(wf, 'accounts', {})
        wf.clear_settings()
        wf.clear_data(lambda x: current_environment in x)
        change_env(wf, current_environment)
        qnotify('Plaid', f'{current_environment.capitalize()} Transaction Data Cleared')

    # Reinitialize if necessary
    if args.reinit:
        reset_secure_values(wf)
        wf.reset()
        qnotify('Plaid', 'Workflow reinitialized')
        return 0

    ####################################################################
    # Save the provided API key
    ####################################################################

    # save Client ID if that is passed in
    if args.clientid:  # Script was passed an API key
        log.debug("saving client id "+args.clientid)
        set_secure_value(wf, 'client_id', args.clientid, ALL_USER, ALL_ENV)
        qnotify('Plaid', 'Client ID Saved')
        return 0  # 0 means script exited cleanly

    
    log.debug(f"{args.category_id} : {args.merchant}")
    if args.category_id and (args.merchant_id or args.merchant or args.txntext):
        merchants = get_stored_data(wf, 'merchants', {})
        category_id = int(args.category_id)
        id = args.merchant_id if args.merchant_id is not None else args.merchant
        set_category(wf, id, category_id)
        merchant = merchants[args.merchant_id]['name'] if args.merchant_id else args.merchant
        category = category_name(wf, category_id)
        db = TxnDB(get_db_file(wf), wf.logger)
        db.update_txn_category(category_id, args.merchant_id, merchant, args.txntext, category_name(wf, category_id, True))
        qnotify('Plaid', f'{merchant} is now {category}')
        return 0  # 0 means script exited cleanly
    
    # save User ID if that is passed in
    if args.userid:  # Script was passed an API key
        log.debug("saving user id "+args.userid)
        set_current_user(wf, args.userid)
        qnotify('Plaid', f'{get_environment(wf)} user is now {args.userid}')
        return 0  # 0 means script exited cleanly

    # save Secret if that is passed in
    if args.secret:  # Script was passed an Hub ID
        log.debug("saving secret "+args.secret)
        set_secure_value(wf, 'secret', args.secret, ALL_USER)
        qnotify('Plaid', f'Secret Saved for {get_environment(wf)}')
        return 0  # 0 means script exited cleanly

    # save Secret if that is passed in
    if args.environment:  # Script was passed an Hub ID
        log.debug("saving environment "+args.environment)
        # save the key
        change_env(wf, str(args.environment))
        qnotify('Plaid', f"Environment is {args.environment}")
        return 0  # 0 means script exited cleanly
    
    if args.proto:
        log.debug("saving protocol "+args.proto)
        wf.settings['protocol'] = args.proto
        qnotify('Plaid', f"Protocol is now {args.proto}")
        return 0

    ####################################################################
    # Check that we have an Client ID/Secret saved
    ####################################################################

    environ = get_environment(wf)
    
    client_id = get_secure_value(wf, 'client_id', None, ALL_USER, ALL_ENV)
    if not client_id:
        error('Client ID not found')
        return 0

    user_id = get_current_user(wf)
    if not user_id:
        error(f'{get_environment(wf)} User ID not found')
        return 0

    secret = get_secure_value(wf, 'secret', None, ALL_USER)
    if not secret:
        error('Secret not found')
        return 0
        
    plaid = Plaid(client_id=client_id, secret=secret, user_id=user_id, wf=wf)
                
    if args.refresh:
        items = get_secure_value(wf, 'items', {})
        banks = get_stored_data(wf, 'banks', {})
        rlist = list(items.values()) if 'all' == args.refresh else [items[args.refresh]]
        name = 'All' if 'all' == args.refresh else banks[items[args.refresh]['institution_id']]['name']
        log.debug("forcing refresh of transactions..")
        for item in rlist:
            plaid.force_refresh(item['access_token'])
        qnotify('Plaid', f"Forced Refresh of {name} Transactions")
        return 0

    if args.acctid:  # Script was passed an account ID
        accounts = get_secure_value(wf, 'accounts', {})
        if args.filter:
            log.debug("saving filtered account id "+args.acctid)
            acct_id = args.acctid[:-1] if '-' == args.acctid[-1] else args.acctid
            if 'all' == acct_id:
                set_secure_value(wf, 'acct_filter', [])
                qnotify('Plaid', 'Account Filter Removed')
            elif acct_id in accounts:
                acct_filter = get_secure_value(wf, 'acct_filter', [])
                if acct_id not in acct_filter:
                    acct_filter.append(acct_id)
                else:
                    acct_filter.remove(acct_id)
                set_secure_value(wf, 'acct_filter', acct_filter)
                name = ','.join([accounts[x]['name'] for x in acct_filter])
                qnotify('Plaid', 'Account Filter: '+name if name else 'Account Filter Removed')
            else:
                qnotify('Plaid', 'Account Filter Failed')
            return 0  # 0 means script exited cleanly
        if args.nick:
            nicks = get_secure_value(wf, 'nicks', {})
            log.debug("adding nickname to "+args.acctid)
            nicks[args.acctid] = args.nick
            set_secure_value(wf, 'nicks', nicks)
            accounts[args.acctid]['nick'] = args.nick
            set_secure_value(wf, 'accounts', accounts)
            name = accounts[args.acctid]['name']
            qnotify('Plaid', f'{name} nicknamed to {args.nick}')
            return 0

    # Update items if that is passed in
    if args.update:
        message = 'Accounts & Transactions updated'
        try:
            result = update_transactions(wf, plaid)
        except Exception as e:
            log.debug(e)
            message = 'Update failed'    
        qnotify('Plaid', message)
        return 0  # 0 means script exited cleanly
    
    if args.upcat:
        result = update_categories(wf, plaid)
        message = 'Categories updated' if result else 'Update failed'
        qnotify('Plaid', message)
        return 0  # 0 means script exited cleanly
    
    if args.kill:
        stop_server(wf)
    
    if args.link:
        items = get_secure_value(wf, 'items', {})
        item = items[args.link] if args.link in items else {}
        try:
            proto = get_protocol(wf)
            run_server(wf)
            link_token = plaid.get_link_token(item, proto)
            log.debug(f'link token is {link_token}')
            open_url(wf, get_link_func(wf)(link_token))
            public_token = wait_for_public_token(wf)
            log.debug(f'pubtoken is {public_token}')
        finally:
            stop_server(wf)            
        if public_token:
            result = plaid.exchange_public_token(public_token=public_token)
            if 'access_token' in result:
                banks = get_stored_data(wf, 'banks', {})
                item['access_token'] = result['access_token']
                item['item_id'] = result['item_id']
                add_item(wf, item)
                name = banks[item['institution_id']]['name']
                update_items(wf, plaid)
                qnotify('Plaid', f'Saved {name} Item' if 'access_token' in result else f'{name} Item Save Failed')
                result = update_transactions(wf, plaid)
            return 0  # 0 means script exited cleanly
        
if __name__ == u"__main__":
    wf = Workflow(libraries=['./lib'], update_settings={
        'github_slug': 'schwark/alfred-plaid'
    })
    log = wf.logger
    sys.exit(wf.run(main))
    