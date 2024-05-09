# encoding: utf-8

import sys
import argparse
from workflow.workflow import MATCH_ATOM, MATCH_STARTSWITH, MATCH_SUBSTRING, MATCH_ALL, MATCH_INITIALS, MATCH_CAPITALS, MATCH_INITIALS_STARTSWITH, MATCH_INITIALS_CONTAIN
from workflow import Workflow, ICON_WEB, ICON_NOTE, ICON_BURN, ICON_SWITCH, ICON_HOME, ICON_COLOR, ICON_INFO, ICON_SYNC, web, PasswordNotFound
from common import get_stored_data, DEFAULT_ENV, DB_FILE, get_password, ensure_icon
from db import TxnDB
import os.path
from dateutil.parser import parse 

log = None

def get_acct_subtitle(acct):
    result = ''
    if 'subtype' in acct:
        result = f"{result}{acct['subtype']}   "
    if 'balances' in acct:
        if 'available' in acct['balances'] and acct['balances']['available']:
            result = f"{result}|   available: ${acct['balances']['available']:,.2f}   "
        if 'current' in acct['balances'] and acct['balances']['current']:
            result = f"{result}|   current: ${acct['balances']['current']:,.2f}   "
        if 'limit' in acct['balances'] and acct['balances']['limit']:
            result = f"{result}|   limit: ${acct['balances']['limit']:,.2f} "
    return result

def get_bank_icon(account, banks):
    if not 'institution_id' in account or account['institution_id'] not in banks: return None
    bank = banks[account['institution_id']]
    name = bank['name']
    logo = bank['logo']
    return ensure_icon(name, 'bank', logo)

def get_category_icon(category):
    l = category.lower().split(',')
    for i in range(1,len(l)+1):
        cats = [l[-i], l[-i][:-1]]
        for cat in cats:
            icon = f'icons/category/{cat}.png'
            if os.path.exists(icon):
                return icon    

def get_txn_icon(txn, accounts, banks, merchants, categories):
    account = accounts[txn['account_id']]
    if 'institution_id' in account:
        bank = banks[account['institution_id']]
        bank = bank['name'].lower().replace(' ','')
    else:
        bank = None
    category = txn['categories'].split(',')[-1]
    merchant = txn['merchant']
    merchant_url = merchants[txn['merchant_entity_id']]['icon'] if 'merchant_entity_id' in txn and txn['merchant_entity_id'] and txn['merchant_entity_id'] in merchants else None
    micon = ensure_icon(merchant, 'merchant', merchant_url)
    bicon = ensure_icon(bank, 'bank')
    category_url = categories[txn['category_id']]['icon'] if 'category_id' in txn and txn['category_id'] and txn['category_id'] in categories else None
    caticon = ensure_icon(txn['category_id'], 'category', category_url)
    cicon = get_category_icon(category)
    icon = micon if micon else (caticon if caticon else cicon if cicon else bicon)
    return icon

def add_config_commands(args, config_commands):
    word = args.query.lower().split(' ')[0] if args.query else ''
    config_command_list = wf.filter(word, config_commands.keys(), min_score=80, match_on=MATCH_SUBSTRING | MATCH_STARTSWITH | MATCH_ATOM)
    if config_command_list:
        for cmd in config_command_list:
            wf.add_item(config_commands[cmd]['title'],
                        config_commands[cmd]['subtitle'],
                        arg=config_commands[cmd]['args'],
                        autocomplete=config_commands[cmd]['autocomplete'],
                        icon=config_commands[cmd]['icon'],
                        valid=config_commands[cmd]['valid'])
    return config_command_list

def extract_commands(wf, args, commands):
    return args

def main(wf):
    # build argument parser to parse script args and collect their
    # values
    parser = argparse.ArgumentParser()
    # add an optional query and save it to 'query'
    parser.add_argument('query', nargs='?', default=None)
    # parse the script's arguments
    args = parser.parse_args(wf.args)

    log.debug("args are "+str(args))

    words = args.query.split(' ') if args.query else []

    # list of commands
    commands = {
        'status': {
            'capability': 'global'
        },
        'on': {
                'component': 'main',
                'capability': 'Switch',
                'command': 'on'
        }, 
        'off': {
                'component': 'main',
                'capability': 'Switch',
                'command': 'off'
        },
        'toggle': {
                'component': 'main',
                'capability': 'Switch',
                'command': 'off'
        },
        'dim': {
                'component': 'main',
                'capability': 'SwitchLevel',
                'command': 'setLevel',
                'arguments': [
                    lambda: int(args.device_params[0]),
                ]
        },
        'slevel': {
                'component': 'main',
                'capability': 'WindowShadeLevel',
                'command': 'setShadeLevel',
                'arguments': [
                    lambda: int(args.device_params[0]),
                ]
        },
        'open': {
                'component': 'main',
                'capability': 'WindowShade',
                'command': 'open'
        },
        'close': {
                'component': 'main',
                'capability': 'WindowShade',
                'command': 'close'
        },
        'lock': {
                'component': 'main',
                'capability': 'Lock',
                'command': 'lock'
        }, 
        'unlock': {
                'component': 'main',
                'capability': 'Lock',
                'command': 'unlock'
        },
        'view': {
                'component': 'main',
                'capability': 'ContactSensor',
                'command': 'view'
        },
        'color': {
                'component': 'main',
                'capability': 'ColorControl',
                'command': 'setColor',
                'arguments': [
                    {
                        'hex': lambda: get_color(args.device_params[0], colors)
                    }
                ]
        },
        'mode': {
            'component': 'main',
            'capability': 'Thermostat',
            'command': 'setThermostatMode',
            'arguments': [
                lambda: str(args.device_params[0])
            ]
        },
        'heat': {
                'component': 'main',
                'capability': 'Thermostat',
                'command': 'setHeatingSetpoint',
                'arguments': [
                    lambda: int(args.device_params[0]),
                ]
        },
        'cool': {
                'component': 'main',
                'capability': 'Thermostat',
                'command': 'setCoolingSetpoint',
                'arguments': [
                    lambda: int(args.device_params[0]),
                ]
        }
    }

    config_commands = {
        'link': {
            'title': 'Link or update item',
            'subtitle': 'Add/update bank or card linking with a nickname',
            'autocomplete': 'link',
            'args': ' --link',
            'icon': ICON_SYNC,
            'valid': True
        },
        'kill': {
            'title': 'Kill the link server',
            'subtitle': 'Clean up link server errors',
            'autocomplete': 'kill',
            'args': ' --kill',
            'icon': ICON_BURN,
            'valid': True
        },
        'update': {
            'title': 'Update Accounts and Transactions',
            'subtitle': 'Update the accounts and transactions from Plaid',
            'autocomplete': 'update',
            'args': ' --update',
            'icon': ICON_SYNC,
            'valid': True
        },
        'clientid': {
            'title': 'Set Client ID',
            'subtitle': 'Set client ID for Plaid',
            'autocomplete': 'clientid',
            'args': ' --clientid '+(words[1] if len(words)>1 else ''),
            'icon': ICON_WEB,
            'valid': len(words) > 1
        },
        'secret': {
            'title': 'Set secret',
            'subtitle': 'Set secret for Plaid development environment',
            'autocomplete': 'secret',
            'args': ' --secret '+(words[1] if len(words)>1 else ''),
            'icon': ICON_WEB,
            'valid': len(words) > 1
        },
        'userid': {
            'title': 'Set User ID',
            'subtitle': 'Set user ID for Plaid',
            'autocomplete': 'userid',
            'args': ' --userid '+(words[1] if len(words)>1 else ''),
            'icon': ICON_WEB,
            'valid': len(words) > 1
        },
        'pubtoken': {
            'title': 'Set Public Token',
            'subtitle': 'Set public token for Plaid',
            'autocomplete': 'pubtoken',
            'args': ' --pubtoken '+(words[1] if len(words)>1 else ''),
            'icon': ICON_WEB,
            'valid': len(words) > 1
        },
        'env': {
            'title': 'Set Environment',
            'subtitle': 'Set environment for Plaid',
            'autocomplete': 'env',
            'args': ' --environment '+(words[1] if len(words)>1 else ''),
            'icon': ICON_WEB,
            'valid': len(words) > 1 and words[1] in ['sandbox', 'development', 'production']
        },
        'reinit': {
            'title': 'Reinitialize the workflow',
            'subtitle': 'CAUTION: this deletes all accounts, transactions and apikeys...',
            'autocomplete': 'reinit',
            'args': ' --reinit',
            'icon': ICON_BURN,
            'valid': True
        },
        'clear': {
            'title': 'Clear account data, keep passwords',
            'subtitle': 'CAUTION: this deletes all accounts, transactions...',
            'autocomplete': 'clear',
            'args': ' --clear',
            'icon': ICON_BURN,
            'valid': True
        },
        'workflow:update': {
            'title': 'Update the workflow',
            'subtitle': 'Updates workflow to latest github version',
            'autocomplete': 'workflow:update',
            'args': '',
            'icon': ICON_SYNC,
            'valid': True
        }
    }

    # add config commands to filter
    add_config_commands(args, config_commands)

    ####################################################################
    # Check that we have an API key saved
    ####################################################################

    environ = get_stored_data(wf, 'plaid_environment')
    environ = DEFAULT_ENV if not environ else environ
    items = get_password(wf, 'plaid_items')

    try:
        client_id = wf.get_password('plaid_client_id')
    except PasswordNotFound:  # API key has not yet been set
        wf.add_item('No Client ID key set...',
                    'Please use pd clientid to set your Plaid Client ID.',
                    valid=False,
                    icon=ICON_NOTE)
        wf.send_feedback()
        return 0

    try:
        secret = wf.get_password('plaid_secret')
    except PasswordNotFound:  # mode has not yet been set
        wf.add_item('No Client Secret key set...',
                    'Please use pd secret to set your Plaid Client Secret.',
                    valid=False,
                    icon=ICON_NOTE)
        wf.send_feedback()
        return 0
        
    try:
        user_id = wf.get_password('plaid_user_id')
    except PasswordNotFound:
        wf.add_item('No User ID key set...',
                    'Please use pd userid to set your User ID - can be anything you choose',
                    valid=False,
                    icon=ICON_NOTE)
        wf.send_feedback()
        return 0

    # since this i now sure to be a device/scene query, fix args if there is a device/scene command in there
    args = extract_commands(wf, args, commands)
 
    # update query post extraction
    query = args.query


    ####################################################################
    # View/filter devices or scenes
    ####################################################################

    # Check for an update and if available add an item to results
    if wf.update_available:
        # Add a notification to top of Script Filter results
        wf.add_item('New version available',
            'Action this item to install the update',
            autocomplete='workflow:update',
            icon=ICON_INFO)

    accounts = get_stored_data(wf, 'accounts')
    banks = get_stored_data(wf, 'banks')
    merchants = get_stored_data(wf, 'merchants')
    categories = get_stored_data(wf, 'categories')
    
    if not accounts or len(accounts) < 1:
        wf.add_item('No Accounts...',
                    'Please use pd update - to update your Accounts and Transactions.',
                    valid=False,
                    icon=ICON_NOTE)
        wf.send_feedback()
        return 0

    # If script was passed a query, use it to filter posts
    if query:
        if ':act' in query:
            query = query.replace(':act','').strip().lower()
            list = wf.filter(query, accounts.values(), lambda x: f"{x['name']} {x['subtype']}")
            if not list:
                    wf.add_item(
                            title="No matching accounts found...",
                            subtitle="Please try another search term",
                            arg="",
                            valid=True,
                            icon=ICON_INFO
                    )
            else:
                wf.add_item(
                            title="All Accounts",
                            subtitle="Remove account filter - set to all accounts",
                            arg=' --acctid all',
                            valid=True,
                            icon=ICON_COLOR
                )   
                log.debug(list)             
                for acct in list:
                    name = acct['name'] if 'name' in acct and acct['name'] else acct['official_name']
                    wf.add_item(
                                title=name,
                                subtitle=get_acct_subtitle(acct),
                                arg=' --acctid '+acct['account_id'],
                                valid=True,
                                icon=get_bank_icon(acct, banks)
                        )                
        else:
            db = TxnDB(DB_FILE, wf.logger)
            try:
                acct_id = wf.get_password('plaid_acct_id')
            except:
                acct_id = None
            if acct_id: query = f"{query} act:{acct_id}"
            txns = db.get_results(query)
            if not txns:
                wf.add_item(
                        title="No matching transactions found...",
                        subtitle="Please try another search term",
                        arg="",
                        valid=True,
                        icon=ICON_INFO
                )
            else:
                for txn in txns:
                    post = parse(txn['post']).strftime('%Y-%m-%d')
                    merchant = txn['merchant'] if txn['merchant'] else txn['txntext']
                    merchant = merchant.ljust(50)
                    wf.add_item(
                            title=f"{post}   {merchant}   ${txn['amount']:.2f}",
                            subtitle=f"{txn['categories']}   {txn['txntext']}",
                            arg=' --txnid '+txn['transaction_id'],
                            valid=True,
                            icon=get_txn_icon(txn, accounts, banks, merchants, categories)
                    )

        # Send the results to Alfred as XML
        wf.send_feedback()
    return 0


if __name__ == u"__main__":
    wf = Workflow(libraries=['./lib'], update_settings={
        'github_slug': 'schwark/alfred-plaid'
    })
    log = wf.logger
    sys.exit(wf.run(main))
    