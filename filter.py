# encoding: utf-8

import sys
import argparse
from workflow.workflow import MATCH_ATOM, MATCH_STARTSWITH, MATCH_SUBSTRING, MATCH_ALL, MATCH_INITIALS, MATCH_CAPITALS, MATCH_INITIALS_STARTSWITH, MATCH_INITIALS_CONTAIN
from workflow import Workflow, ICON_NOTE, ICON_BURN, PasswordNotFound
from common import get_stored_data, DB_FILE, ensure_icon, get_environment, get_password
from db import TxnDB
import os.path
from dateutil.parser import parse 
from datetime import timedelta
import re
import json
import urllib.parse

log = None
environments = ['development', 'sandbox', 'production']
chart_types = {'p': 'pie', 'd': 'doughnut', 'l': 'line', 'b': 'bar'}
time_aggregates = {'d': 'day', 'w': 'week', 'm': 'month'}
merchant_aggregates = {'m': 'merchant', 'c': 'category'}
timeframes = ['This week', 'This month', 'This quarter', 'This half', 'This year', 'Last week', 'Last month', 'Last quarter', 'Last half', 'Last year']

chart_options = {
    'ta': 'm', # time aggregation
    'ma': 'm', # merchant/category aggregation
    'ct': 'b' # chart type
}


def get_time_cut(dt, ta, ct):
    if ct in ['p', 'd']: return 'all'
    if 'd' == ta: return dt.strftime('%b-%d-%y')
    if 'w' == ta: return (dt - timedelta(days=dt.isoweekday() % 7)).strftime('%b-%d-%y')
    if 'm' == ta: return dt.replace(day=1,hour=0,minute=0,second=0).strftime('%b-%y')

def create_chart(txns):
    ta = chart_options['ta']
    ma = chart_options['ma']
    ct = chart_options['ct']
    
    data = {}
    lines = ['Total'] if ct not in ['p','d'] else []
    min_date = None
    max_date = None
    for txn in txns:
        post_date = parse(txn['post'])
        time_cut = get_time_cut(post_date, ta, ct)
        if not min_date or post_date < min_date: min_date = post_date
        if not max_date or post_date > max_date: max_date = post_date
        data[time_cut] = data[time_cut] if time_cut in data else {}
        merchant_cut = txn['merchant'] if 'm' == ma else txn['categories'].split(',')[0]
        merchant_cut = merchant_cut if merchant_cut else 'Other'
        data[time_cut][merchant_cut] = data[time_cut][merchant_cut]+txn['amount'] if merchant_cut in data[time_cut] else txn['amount']
        if merchant_cut not in lines: lines.append(merchant_cut)
        if ct not in ['p', 'd']:
            data[time_cut]['Total'] = data[time_cut]['Total']+txn['amount'] if 'Total' in data[time_cut] else txn['amount']
    drop_year = (min_date.year == max_date.year)
    chart = {}
    chart['type'] = chart_types[ct]
    chart['options'] = {}
    chart['options']['layout'] = {'padding': 10}
    chart['data'] = {}
    chart['data']['labels'] = (['-'.join(x.split('-')[:-1]) for x in list(data.keys())] if drop_year else list(data.keys())) if ct not in ['p','d'] else lines
    chart['data']['datasets'] = []
    if 'p' != ct:
        values = {}
        for cut in data:
            for mcut in lines:
                values[mcut] = values[mcut] if mcut in values else []
                values[mcut].append(data[cut][mcut] if mcut in data[cut] else 0)
        for mcut in values:
            cdata = {'label': mcut, 'data': values[mcut]}
            if 'Total' == mcut:
                cdata['type'] = 'line'
                cdata['fill'] = False
            chart['data']['datasets'].append(cdata)
    else:
        chart['data']['datasets'].append({'data': list(data['all'].values())})
    log.debug(chart)
    return chart
         
def get_chart_url(txns):
    chart = create_chart(txns)
    url = f"https://quickchart.io/chart?width=500&height=300&chart={urllib.parse.quote_plus(json.dumps(chart, separators=(',', ':')))}"
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

def get_category_icon(categories):
    cats = categories.lower().split(',')
    for i in range(len(cats), 0, -1):
        log.debug(cats)
        cat = cats[i-1]
        words = re.split(r'\s+|\'|,', cat)
        for i in range(len(words),0,-1):
            substr = ''.join(words[0:i])
            icon = f'icons/category/{substr}.png'
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
    words = args.query.lower().split() if args.query else []
    for word in words:
        config_command_list = wf.filter(word, config_commands.keys(), min_score=80, match_on=MATCH_SUBSTRING | MATCH_STARTSWITH | MATCH_ATOM)
        if config_command_list:
            base = re.sub(fr'{word}$','',args.query)
            for cmd in config_command_list:
                wf.add_item(config_commands[cmd]['title'],
                            config_commands[cmd]['subtitle'],
                            arg=config_commands[cmd]['args'],
                            autocomplete=f"{base}{config_commands[cmd]['autocomplete']}",
                            icon=config_commands[cmd]['icon'],
                            valid=config_commands[cmd]['valid'])

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
            'autocomplete': 'act: ',
            'args': ' --acctid '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/account.png",
            'valid': False
        },
        'ct': {
            'title': 'Customize chart type',
            'subtitle': 'Set the chart type generated for transaction set',
            'autocomplete': 'ct:',
            'args': ' --ct '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/chart-type.png",
            'valid': False
        },
        'ta': {
            'title': 'Customize time periods for charting',
            'subtitle': 'Chart over different time windows (weeks,months,etc.)',
            'autocomplete': 'ta:',
            'args': ' --ta '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/time-period.png",
            'valid': False
        },
        'ma': {
            'title': 'Choose merchant or category based charting',
            'subtitle': 'Chart totals by merchant or category',
            'autocomplete': 'ma:',
            'args': ' --ma '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/categorize.png",
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
    
    config_options = {
        'env': {
                'name': 'environment',
                'title': lambda x: f"{x}",
                'subtitle': lambda x: f"Set environment to {x.lower()}",
                'arg': lambda x: f"--environment {x}",
                'suffix': ' ',
                'options': environments,
                'valid': True
        },
        'dt': {
                'name': 'date range',
                'title': lambda x: f"{x}",
                'subtitle': lambda x: f"Filter transactions within {x.lower()}",
                'icon': lambda x: f"{x.split()[1]}",
                'suffix': '\:',
                'options': timeframes,
                'id': lambda x: x.lower().replace(' ','-'),
                'valid': False            
        },
        'ct': {
                'name': 'chart type',
                'title': lambda x: f"{x}",
                'subtitle': lambda x: f"Chart type {x.lower()}",
                'options': chart_types,
                'suffix': '\:',
                'set': {'holder': chart_options, 'field': 'ct'},
                'valid': False                        
        },
        'ta': {
                'name': 'time aggregates',
                'title': lambda x: f"Aggregate transactions over {x}s",
                'subtitle': lambda x: f"Totals transactions with a {x.lower()} for charting",
                'options': time_aggregates,
                'suffix': '\:',
                'set': {'holder': chart_options, 'field': 'ta'},
                'valid': False                                    
        },
        'ma': {
                'name': 'time aggregates',
                'title': lambda x: f"Aggregate transactions by {x}",
                'subtitle': lambda x: f"Totals transactions by {x.lower()} for charting",
                'options': merchant_aggregates,
                'suffix': '\:',
                'set': {'holder': chart_options, 'field': 'ma'},
                'valid': False                                                
        }
    }

    # add config commands to filter
    add_config_commands(args, config_commands)

    ####################################################################
    # Check that we have an API key saved
    ####################################################################

    environ = get_environment(wf)

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
    
    try:
        items = get_password(wf, 'plaid_items')
    except PasswordNotFound:
        items = None
        wf.add_item('No Linked Financial Institutions Found...',
                    'Please use pd link to link your bank accounts',
                    valid=False,
                    icon="icons/ui/no-bank.png")
    
    if items and (not accounts or len(accounts) < 1):
        wf.add_item('No Accounts...',
                    'Please use pd update - to update your Accounts and Transactions.',
                    valid=False,
                    icon="icons/ui/empty.png")
#        wf.send_feedback()
#        return 0

    # If script was passed a query, use it to filter posts
    if query:
        for opt in config_options:
            suffix = config_options[opt]['suffix']
            opts = config_options[opt]['options']
            is_array = isinstance(opts, list)
            if not is_array: opts = opts.keys()
            found = re.findall(fr'{opt}{suffix}([^\s]+)', query)
            term = found[0] if found else ''
            if re.findall(fr'{opt}{suffix}[^\s]*$', query):
                matches = wf.filter(term, opts, lambda x: x if is_array else opts[x])
                query = re.sub(fr'{opt}{suffix}[^\s]*$','',query)
                for item in matches:
                    name = item if is_array else config_options[opt]['options'][item]
                    id = config_options[opt]['id'](item) if 'id' in config_options[opt] else item
                    log.debug(name)
                    icon = config_options[opt]['icon'](name) if 'icon' in config_options[opt] else name.lower().replace(' ','-')
                    suffix = suffix.replace("\\",'')
                    wf.add_item(
                            title=config_options[opt]['title'](name),
                            subtitle=config_options[opt]['subtitle'](name),
                            autocomplete=f"{query}{opt}{suffix}{id} ",
                            arg=config_options[opt]['arg'](item) if 'arg' in config_options[opt] else '',
                            valid=config_options[opt]['valid'],
                            icon=f"icons/ui/{icon}.png"
                    )
            if found:
                log.debug(f'found {term} with {opts}')
                if term and (term in opts):
                    if 'set' in config_options[opt]:
                        config_options[opt]['set']['holder'][config_options[opt]['set']['field']] = term
    
        if 'act:' in query:
            query = query.replace('act:','').strip().lower()
            matches = wf.filter(query, accounts.values(), lambda x: f"{x['name']} {x['subtype']}")
            if not matches:
                    wf.add_item(
                            title="No matching accounts found...",
                            subtitle="Please try another search term",
                            valid=False,
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
                log.debug(matches)             
                for acct in matches:
                    name = acct['name'] if 'name' in acct and acct['name'] else acct['official_name']
                    wf.add_item(
                                title=name,
                                subtitle=get_acct_subtitle(acct),
                                arg=' --acctid '+acct['account_id'],
                                valid=True,
                                icon=get_bank_icon(acct, banks)
                        )                
        elif re.match(r'dt\:[^\s]*$', query):
            found = re.compile('dt\:([^\s]+)').search(query)
            term = found.group(1) if found else ''
            matches = wf.filter(term, timeframes)
            query = re.sub(r'dt\:[^\s]*$','',query)
            for period in matches:
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
                        valid=False,
                        icon="icons/ui/empty.png"
                )
            else:
                wf.add_item(
                    title="Chart the transactions",
                    subtitle=f"Highlight and tap SHIFT key for {chart_types[chart_options['ct']]} chart aggregated by {time_aggregates[chart_options['ta']]} and {merchant_aggregates[chart_options['ma']]}",
                    valid=False,
                    quicklookurl=get_chart_url(txns),
                    icon='icons/ui/chart.png'
                )                
                for txn in txns:
                    post = parse(txn['post']).strftime('%Y %b %d')
                    merchant = txn['merchant'] if txn['merchant'] else txn['txntext']
                    merchant = merchant.ljust(50)
                    wf.add_item(
                            title=f"{post}\t{merchant}\t\t${txn['amount']:.2f}",
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
    