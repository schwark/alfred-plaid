# encoding: utf-8

import sys
import argparse
from workflow.workflow import MATCH_ATOM, MATCH_STARTSWITH, MATCH_SUBSTRING, MATCH_ALL, MATCH_INITIALS, MATCH_CAPITALS, MATCH_INITIALS_STARTSWITH, MATCH_INITIALS_CONTAIN
from workflow import Workflow, ICON_WEB, ICON_NOTE, ICON_BURN, ICON_SWITCH, ICON_HOME, ICON_COLOR, ICON_INFO, ICON_SYNC, web, PasswordNotFound
from common import get_stored_data, DEFAULT_ENV, DB_FILE, get_password, ensure_icon
from db import TxnDB
import os.path
from dateutil.parser import parse 
from datetime import datetime, timedelta
import re
import json

log = None
environments = ['development', 'sandbox', 'production']
chart_types = {'p': 'pie', 'l': 'line', 'b': 'bar'}
time_aggregates = {'a': 'all', 'd': 'day', 'w': 'week', 'm': 'month'}
merchant_aggregates = {'m': 'merchant', 'c': 'category'}

def get_time_cut(dt, type):
    if 'a' == type: return 'all'
    if 'd' == type: return dt.strftime('%Y-%m-%d')
    if 'w' == type: return (dt - timedelta(days=dt.isoweekday() % 7)).strftime('%Y-%m-%d')
    if 'm' == type: return dt.replace(day=1,hour=0,minute=0,second=0).strftime('%Y-%m')

def create_chart(txns, ct, ta, ma):
    data = {}
    lines = ['Total'] if 'p' != ct else []
    for txn in txns:
        time_cut = get_time_cut(parse(txn['post']), ta)
        data[time_cut] = data[time_cut] if time_cut in data else {}
        merchant_cut = txn['merchant'] if 'm' == ma else txn['categories'].split(',')[0]
        merchant_cut = merchant_cut if merchant_cut else 'Other'
        data[time_cut][merchant_cut] = data[time_cut][merchant_cut]+txn['amount'] if merchant_cut in data[time_cut] else txn['amount']
        if merchant_cut not in lines: lines.append(merchant_cut)
        if 'p' != ct:
            data[time_cut]['Total'] = data[time_cut]['Total']+txn['amount'] if 'Total' in data[time_cut] else txn['amount']
    chart = {}
    chart['type'] = chart_types[ct]
    chart['data'] = {}
    chart['data']['labels'] = list(data.keys()) if 'p' != ct else lines
    chart['data']['datasets'] = []
    if 'p' != ct:
        values = {}
        for cut in data:
            for mcut in lines:
                values[mcut] = values[mcut] if mcut in values else []
                values[mcut].append(data[cut][mcut] if mcut in data[cut] else 0)
        for mcut in values:
            chart['data']['datasets'].append({'label': mcut, 'data': values[mcut]})
    else:
        chart['data']['datasets'].append({'data': list(data['all'].values())})
    log.debug(chart)
    return chart
         
def get_chart_url(txns, ct, ta, ma):
    chart = create_chart(txns, ct, ta, ma)
    url = f"https://quickchart.io/chart?width=500&height=300&chart={json.dumps(chart, separators=(',', ':'))}"
    log.debug(url)
    return url

def get_acct_subtitle(acct):
    result = ''
    if 'subtype' in acct:
        result = f"{result}{acct['subtype']}   "
    if 'balances' in acct:
        if 'available' in acct['balances'] and acct['balances']['available']:
            result = f"{result}|   available: ${acct['balances']['available']:,.2f}   "
        if 'current' in acct['balances'] and acct['balances']['current']:
            result = f"{result}|   balance: ${acct['balances']['current']:,.2f}   "
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
            cat = cat.replace(' ','')
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
    merchant = txn['merchant']
    merchant_url = merchants[txn['merchant_entity_id']]['icon'] if 'merchant_entity_id' in txn and txn['merchant_entity_id'] and txn['merchant_entity_id'] in merchants else None
    micon = ensure_icon(merchant, 'merchant', merchant_url)
    category_url = categories[txn['category_id']]['icon'] if 'category_id' in txn and txn['category_id'] and txn['category_id'] in categories else None
    cicon = get_category_icon(txn['categories'])
    caticon = ensure_icon(txn['category_id'], 'category', category_url) if not cicon else None
    bicon = ensure_icon(bank, 'bank') if not cicon and not caticon else None
    icon = micon if micon else (cicon if cicon else caticon if caticon else bicon)
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

    words = args.query.split() if args.query else []

    config_commands = {
        'link': {
            'title': 'Link or update item',
            'subtitle': 'Add/update bank or card linking with a nickname',
            'autocomplete': 'link',
            'args': ' --link',
            'icon': "icons/ui/link.png",
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
            'icon': "icons/ui/sync.png",
            'valid': True
        },
        'clientid': {
            'title': 'Set Client ID',
            'subtitle': 'Set client ID for Plaid',
            'autocomplete': 'clientid',
            'args': ' --clientid '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/key.png",
            'valid': len(words) > 1
        },
        'secret': {
            'title': 'Set secret',
            'subtitle': 'Set secret for Plaid development environment',
            'autocomplete': 'secret',
            'args': ' --secret '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/password.png",
            'valid': len(words) > 1
        },
        'userid': {
            'title': 'Set User ID',
            'subtitle': 'Set user ID for Plaid',
            'autocomplete': 'userid',
            'args': ' --userid '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/username.png",
            'valid': len(words) > 1
        },
        'pubtoken': {
            'title': 'Set Public Token',
            'subtitle': 'Set public token for Plaid',
            'autocomplete': 'pubtoken',
            'args': ' --pubtoken '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/key.png",
            'valid': len(words) > 1
        },
        'env': {
            'title': 'Set Environment',
            'subtitle': 'Set environment for Plaid',
            'autocomplete': 'env ',
            'args': ' --environment '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/choose.png",
            'valid': len(words) > 1 and words[1] in environments
        },
        'act': {
            'title': 'Add an Account Filter',
            'subtitle': 'Filter results to certain accounts',
            'autocomplete': 'act:',
            'args': ' --acctid '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/account.png",
            'valid': False
        },
        'dt': {
            'title': 'Add a Date Filter',
            'subtitle': 'Filter results to certain dates',
            'autocomplete': 'dt:',
            'args': ' --dt '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/calendar.png",
            'valid': False
        },
        'amtt': {
            'title': 'Add a Amount To Filter',
            'subtitle': 'Filter results to transactions up to amount',
            'autocomplete': 'amtt:',
            'args': ' --amtt '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/amount.png",
            'valid': False
        },
        'amtf': {
            'title': 'Add a Amount From Filter',
            'subtitle': 'Filter results to transactions from amount',
            'autocomplete': 'amtf:',
            'args': ' --amtf '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/amount.png",
            'valid': False
        },
        'reinit': {
            'title': 'Reinitialize the workflow',
            'subtitle': 'CAUTION: this deletes all accounts, transactions and apikeys...',
            'autocomplete': 'reinit',
            'args': ' --reinit',
            'icon': "icons/ui/burn.png",
            'valid': True
        },
        'clear': {
            'title': 'Clear account data, keep client secret etc.',
            'subtitle': 'CAUTION: this deletes all accounts, transactions...',
            'autocomplete': 'clear',
            'args': ' --clear',
            'icon': "icons/ui/burn.png",
            'valid': True
        },
        'workflow:update': {
            'title': 'Update the workflow',
            'subtitle': 'Updates workflow to latest github version',
            'autocomplete': 'workflow:update',
            'args': '',
            'icon': "icons/ui/update.png",
            'valid': True
        }
    }

    # add config commands to filter
    add_config_commands(args, config_commands)

    ####################################################################
    # Check that we have an API key saved
    ####################################################################

    environ = get_stored_data(wf, 'plaid_environment')
    environ = DEFAULT_ENV if not environ else environ.decode('utf-8')

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
            icon="icons/ui/update.png")

    accounts = get_stored_data(wf, 'accounts')
    banks = get_stored_data(wf, 'banks')
    merchants = get_stored_data(wf, 'merchants')
    categories = get_stored_data(wf, 'categories')
    
    if not accounts or len(accounts) < 1:
        wf.add_item('No Accounts...',
                    'Please use pd update - to update your Accounts and Transactions.',
                    valid=False,
                    icon="icons/ui/empty.png")
        wf.send_feedback()
        return 0

    # If script was passed a query, use it to filter posts
    if query:
        ta = 'm' # time aggregation
        ma = 'm' # merchant/category aggregation
        ct = 'b' # chart type
        if 'ct:' in query:
            found = re.compile('ct\:([^\s]+)').search(query)
            ct = found.group(1) if found and found.group(1) in chart_types else ct
            if found and 'p' == found.group(1): ta = 'a'
            query = re.sub(r'ct:[^\s]*','', query)
        if 'ta:' in query:
            found = re.compile('ta\:([^\s]+)').search(query)
            if found and 'a' == found.group(1): ct = 'p'
            ta = found.group(1) if found and found.group(1) in time_aggregates else ta
            query = re.sub(r'ta:[^\s]*','', query)
        if 'ma:' in query:
            found = re.compile('ma\:([^\s]+)').search(query)
            ma = found.group(1) if found and found.group(1) in merchant_aggregates else ma
            query = re.sub(r'ma:[^\s]*','', query)
        if 'env ' in query:
            query = query.replace('env','').strip().lower()
            list = wf.filter(query, environments)
            for env in list:
                wf.add_item(
                            title=env,
                            subtitle=f"Set environment to {env}",
                            autocomplete=f"env {env}",
                            arg=' --environment '+env,
                            valid=True,
                            icon=f"icons/ui/{env}.png"
                    )                
        elif 'act:' in query:
            query = query.replace('act:','').strip().lower()
            list = wf.filter(query, accounts.values(), lambda x: f"{x['name']} {x['subtype']}")
            if not list:
                    wf.add_item(
                            title="No matching accounts found...",
                            subtitle="Please try another search term",
                            arg="",
                            valid=True,
                            icon="icons/ui/empty.png"
                    )
            else:
                wf.add_item(
                            title="All Accounts",
                            subtitle="Remove account filter - set to all accounts",
                            arg=' --acctid all',
                            valid=True,
                            icon="icons/ui/all.png"
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
        elif re.match(r'dt\:[^\s]*$', query):
            timeframes = ['This week', 'This month', 'This quarter', 'This half', 'This year', 'Last week', 'Last month', 'Last quarter', 'Last half', 'Last year']
            found = re.compile('dt\:([^\s]+)').search(query)
            term = found.group(1) if found else ''
            list = wf.filter(term, timeframes)
            query = re.sub(r'dt\:[^\s]*$','',query)
            for period in list:
                length = period.split()[1]
                wf.add_item(
                        title=period,
                        subtitle=f"Filter over {period.lower()}",
                        autocomplete=f"{query}dt:{period.lower().replace(' ','-')} ",
                        valid=False,
                        icon=f"icons/ui/{length}.png"
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
                        icon="icons/ui/empty.png"
                )
            else:
                wf.add_item(
                    title="Chart the transactions",
                    subtitle=f"Highlight and press SHIFT key to {chart_types[ct]} chart aggregated by {time_aggregates[ta]} and {merchant_aggregates[ma]}",
                    arg="--chart",
                    valid=True,
                    quicklookurl=get_chart_url(txns, ct, ta, ma),
                    icon='icons/ui/chart.png'
                )                
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
    