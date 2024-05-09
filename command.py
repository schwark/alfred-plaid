# encoding: utf-8

import sys
import argparse
from workflow import Workflow, PasswordNotFound
from common import qnotify, error, get_stored_data, open_url, wait_for_public_token, LINK_URL, DEFAULT_ENV, get_password, save_password
from plaid import Plaid
from server import run_server, stop_server
from common import DB_FILE
from db import TxnDB
import os

log = None

def add_item(wf, item):
    if not item: return
    items = get_password(wf, 'plaid_items')
    items[item['item_id']] = item
    save_password(wf, 'plaid_items', items)

def update_items(wf, plaid):
    log.debug('updating items...')
    db = TxnDB(DB_FILE, wf.logger)
    
    items = get_password(wf, 'plaid_items')
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
            os.remove(DB_FILE)
        except OSError:
            pass
        qnotify('Plaid', 'Data Cleared')

    # Reinitialize if necessary
    if args.reinit:
        wf.delete_password('plaid_client_id')
        wf.delete_password('plaid_secret')
        wf.delete_password('plaid_user_id')
        wf.delete_password('plaid_items')
        qnotify('Plaid', 'Workflow reinitialized')
        return 0

    ####################################################################
    # Save the provided API key
    ####################################################################

    # save Client ID if that is passed in
    if args.clientid:  # Script was passed an API key
        log.debug("saving client id "+args.clientid)
        # save the key
        wf.save_password('plaid_client_id', args.clientid)
        qnotify('Plaid', 'Client ID Saved')
        return 0  # 0 means script exited cleanly

    if args.acctid:  # Script was passed an API key
        log.debug("saving filtered account id "+args.acctid)
        accounts = get_stored_data(wf, 'accounts', {})
        if 'all' == args.acctid:
            wf.save_password('plaid_acct_id', '')
            qnotify('Plaid', 'Account Filter Removed')
        elif args.acctid in accounts:
            # save the key
            wf.save_password('plaid_acct_id', args.acctid)
            qnotify('Plaid', 'Account Filter: '+accounts[args.acctid]['name'])
        else:
            qnotify('Plaid', 'Account Filter Failed')
        return 0  # 0 means script exited cleanly

    # save User ID if that is passed in
    if args.userid:  # Script was passed an API key
        log.debug("saving user id "+args.userid)
        # save the key
        wf.save_password('plaid_user_id', args.userid)
        qnotify('Plaid', 'User ID Saved')
        return 0  # 0 means script exited cleanly

    # save Secret if that is passed in
    if args.secret:  # Script was passed an Hub ID
        log.debug("saving secret "+args.secret)
        # save the key
        wf.save_password('plaid_secret', args.secret)
        qnotify('Plaid', 'Secret Saved')
        return 0  # 0 means script exited cleanly

    # save Secret if that is passed in
    if args.environment:  # Script was passed an Hub ID
        log.debug("saving environment "+args.environment)
        # save the key
        wf.store_data('plaid_environment', args.environment)
        qnotify('Plaid', 'Environment Saved')
        return 0  # 0 means script exited cleanly

    ####################################################################
    # Check that we have an Client ID/Secret saved
    ####################################################################

    environ = get_stored_data(wf, 'plaid_environment')
    environ = DEFAULT_ENV if not environ else environ

    try:
        client_id = wf.get_password('plaid_client_id')
    except PasswordNotFound:  # Client ID has not yet been set
        error('Client ID not found')
        return 0

    try:
        user_id = wf.get_password('plaid_user_id')
    except PasswordNotFound:  # User ID has not yet been set
        error('User ID not found')
        return 0

    try:
        secret = wf.get_password('plaid_secret')
    except PasswordNotFound:  # Secret has not yet been set
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
            open_url(wf, LINK_URL(link_token))
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
    