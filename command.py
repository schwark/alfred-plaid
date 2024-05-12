# encoding: utf-8

import sys
import argparse
from workflow import Workflow, PasswordNotFound
from common import qnotify, error, get_stored_data, open_url, wait_for_public_token, get_link_func, CERT_FILE, KEY_FILE
from plaid import Plaid
from server import run_server, stop_server
from common import DB_FILE, get_environment, get_secure_value, set_secure_value, set_current_user, ALL_ENV, ALL_USER, reset_secure_values, get_current_user
from db import TxnDB
import os

log = None

def change_env(wf, env):
    current = get_environment(wf)
    if env != current:
        wf.settings['environment'] = env

def add_item(wf, item):
    if not item: return
    items = get_secure_value(wf, 'items', {})
    items[item['item_id']] = item
    set_secure_value(wf, 'items', items)

def update_items(wf, plaid):
    log.debug('updating items...')
    db = TxnDB(wf.datafile(DB_FILE), wf.logger)
    
    items = get_secure_value(wf, 'items', {})
    accounts = get_stored_data(wf, 'accounts', {})
    merchants = get_stored_data(wf, 'merchants', {})
    categories = get_stored_data(wf, 'categories', {})
    banks = get_stored_data(wf, 'banks', {})
    if not items:
        log.debug('No items found. Please add items first..')
        qnotify('Plaid', 'No Items Found!')
    for item_id in items:
        log.debug('updating item '+item_id)
        single = items[item_id]
        actlist = plaid.get_accounts(single, banks)
        for i in range(len(actlist)):
            log.debug(actlist[i])
            accounts[actlist[i]['account_id']] = actlist[i]
        txns = plaid.get_transactions(single, merchants, categories)
        for t in txns:
            #log.debug(t)
            db.save_txn(t)
    wf.store_data('accounts', accounts)
    wf.store_data('merchants', merchants)
    wf.store_data('categories', categories)
    wf.store_data('banks', banks)
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
    parser.add_argument('--acctid', dest='acctid', nargs='?', default=None)
    # add an optional (nargs='?') --update argument and save its
    # value to 'apikey' (dest). This will be called from a separate "Run Script"
    # action with the API key
    parser.add_argument('--update', dest='update', action='store_true', default=False)
    parser.add_argument('--link', dest='link', action='store_true', default=False)
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
        wf.reset()
        try:
            os.remove(wf.datafile(DB_FILE))
        except OSError:
            pass
        qnotify('Plaid', 'Transaction Data Cleared')

    # Reinitialize if necessary
    if args.reinit:
        reset_secure_values(wf)
        wf.clear_data()
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

    if args.acctid:  # Script was passed an API key
        log.debug("saving filtered account id "+args.acctid)
        accounts = get_stored_data(wf, 'accounts', {})
        if 'all' == args.acctid:
            set_secure_value(wf, 'acct_filter', [])
            qnotify('Plaid', 'Account Filter Removed')
        elif args.acctid in accounts:
            acct_filter = get_secure_value(wf, 'acct_filter', [])
            if args.acctid not in acct_filter:
                acct_filter.append(args.acctid)
                set_secure_value(wf, 'acct_filter', acct_filter)
            name = ','.join([accounts[x]['name'] for x in acct_filter])
            qnotify('Plaid', 'Account Filter: '+name)
        else:
            qnotify('Plaid', 'Account Filter Failed')
        return 0  # 0 means script exited cleanly

    # save User ID if that is passed in
    if args.userid:  # Script was passed an API key
        log.debug("saving user id "+args.userid)
        set_current_user(wf, args.userid)
        qnotify('Plaid', f'User is now {args.userid}')
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
        error('User ID not found')
        return 0

    secret = get_secure_value(wf, 'secret', None, ALL_USER)
    if not secret:
        error('Secret not found')
        return 0
        
    plaid = Plaid(client_id=client_id, secret=secret, user_id=user_id, environment=environ,logger=wf.logger)
            
    # Update items if that is passed in
    if args.update:
        result = update_items(wf, plaid)
        message = 'Accounts & Transactions updated' if result else 'Update failed'
        qnotify('Plaid', message)
        return 0  # 0 means script exited cleanly
    
    if args.kill:
        stop_server(wf)
    
    if args.link:
        item = {}
        try:
            log.debug("trying to link new item...")
            run_server(wf)
            link_token = plaid.get_link_token(item)
            log.debug(f'link token is {link_token}')
            open_url(wf, get_link_func(wf)(link_token))
            public_token = wait_for_public_token(wf)
            log.debug(f'pubtoken is {public_token}')
        finally:
            stop_server(wf)            
        if public_token:
            result = plaid.exchange_public_token(public_token=public_token)
            if 'access_token' in result:
                item['access_token'] = result['access_token']
                item['item_id'] = result['item_id']
                add_item(wf, item)
                result = update_items(wf, plaid)
                qnotify('Plaid', 'Saved Item' if 'access_token' in result else 'Item Save Failed')
            return 0  # 0 means script exited cleanly
        
if __name__ == u"__main__":
    wf = Workflow(libraries=['./lib'], update_settings={
        'github_slug': 'schwark/alfred-plaid'
    })
    log = wf.logger
    sys.exit(wf.run(main))
    