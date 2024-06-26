# encoding: utf-8

import sys
import argparse
from workflow.workflow import MATCH_ATOM, MATCH_STARTSWITH, MATCH_SUBSTRING, MATCH_ALL, MATCH_INITIALS, MATCH_CAPITALS, MATCH_INITIALS_STARTSWITH, MATCH_INITIALS_CONTAIN
from workflow import Workflow, ICON_NOTE, ICON_BURN, PasswordNotFound
from common import get_stored_data, get_environment, get_protocol, get_secure_value, set_secure_value, get_current_user, ALL_ENV, ALL_USER, get_db_file, get_category_icon, get_category, extract_filter, get_merchant_icon, get_bank_icon, get_category_icon, ICONS_DEFAULT
from db import TxnDB
from dateutil.parser import parse 
from datetime import timedelta, datetime
import re
import os
import json
import urllib.parse
from dateutil.parser import parse 
from shlex import quote

log = None
protos = ['https', 'http']
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

def create_chart(wf, txns): 
    ta = chart_options['ta']
    ma = chart_options['ma']
    ct = chart_options['ct']
       
    data = {}
    lines = ['Total'] if ct not in ['p','d'] else []
    min_date = None
    max_date = None
    merchants = get_stored_data(wf, 'merchants')
    categories = get_stored_data(wf, 'categories')
    for txn in txns:
        category_id = get_category(wf, txn)
        post_date = parse(txn['post'])
        time_cut = get_time_cut(post_date, ta, ct)
        if not min_date or post_date < min_date: min_date = post_date
        if not max_date or post_date > max_date: max_date = post_date
        data[time_cut] = data[time_cut] if time_cut in data else {}
        merchant_cut = txn['merchant'] if 'm' == ma else categories[category_id]['list'][0]
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
         
def get_chart_url(wf, txns):
    chart = create_chart(wf, txns)
    url = f"https://quickchart.io/chart?width=500&height=300&chart={urllib.parse.quote_plus(json.dumps(chart, separators=(',', ':')))}"
    log.debug(url)
    return url

def format_post_date(dt):
    format = '%b-%d'
    this_year = datetime.now().year
    given_date = parse(dt)
    date_year = given_date.year
    format = f"{format}-%y" if(date_year != this_year) else f"{format}   "
    return given_date.strftime(format)
    
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
       
def get_txn_icon(wf, txn, accounts, banks, merchants, categories, icons):
    icon = get_merchant_icon(wf, txn['merchant_id'], merchants, icons)
    if icon: return icon
    icon = get_category_icon(wf, txn['category_id'], categories, icons)
    if icon: return icon
    icon = get_bank_icon(wf, accounts[txn['account_id']]['institution_id'], banks, icons)
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

def add_new_link(wf, query, opts):
    wf.add_item(
        title="Link a new item",
        subtitle="Link a new financial institution's accounts",
        autocomplete="link new",
        arg='--link new',
        valid=True,
        icon="icons/ui/newbank.png"
    )
    
def add_refresh_all(wf, query, opts):
    wf.add_item(
        title="Force refresh on all Accounts",
        subtitle="Force a refresh of transaction data across all accounts",
        autocomplete="refresh all",
        arg='--refresh all',
        valid=True,
        icon="icons/ui/all.png"
    )
    
def add_all_accounts(wf, query, opts):
    if opts and ('filter ' in query):
        wf.add_item(
                title="All Accounts",
                subtitle="Remove account filter - set to all accounts",
                arg=f" {'--filter' if 'filter ' in query else ''} --acctid all",
                valid=True,
                icon="icons/ui/all.png"
        )
    elif not opts:
        wf.add_item(
            title="No matching accounts found...",
            subtitle="Please try another search term",
            valid=False,
            icon="icons/ui/empty.png"
        )

def add_item_errors(wf, query):
    if 'link ' in query: return
    items = get_secure_value(wf, 'items', {})
    for item in items:
        if 'error' in items[item] and items[item]['error']:
            wf.add_item(
                title="Some items have errors..",
                subtitle="Please check and re-link the appropriate accounts using pd link",
                autocomplete="link ",
                valid=False,
                icon="icons/ui/broken.png"
            )
            return

def extract_nick(query):
    found = re.findall(r'nick (.*)', query)
    nick = re.sub(r'\w+\:[^\s]*','', found[0]).strip() if found else ''
    return nick
            
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
    accounts = get_secure_value(wf, 'accounts', {})
    banks = get_stored_data(wf, 'banks')
    merchants = get_stored_data(wf, 'merchants')
    categories = get_stored_data(wf, 'categories')
    environ = get_environment(wf)
    items = get_secure_value(wf, 'items', {})
    icons = get_stored_data(wf, 'icons', ICONS_DEFAULT)
    acct_filter = get_secure_value(wf, 'acct_filter', [])
    
    config_commands = {
        'link': {
            'title': 'Link or update item',
            'subtitle': 'Add/update bank or card linking with a nickname',
            'autocomplete': 'link ',
            'args': ' --link',
            'icon': "icons/ui/link.png",
            'valid': False
        },
        'del': {
            'title': 'Delete item and accounts',
            'subtitle': 'Delete the item and all related accounts and transactions',
            'autocomplete': 'del ',
            'args': ' --delete',
            'icon': "icons/ui/delete.png",
            'valid': False
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
        'refresh': {
            'title': 'Force a refresh of data from the bank',
            'subtitle': 'Force and update of transactions. update will need to be called a few mins later',
            'autocomplete': 'refresh ',
            'args': ' --refresh',
            'icon': "icons/ui/cloud.png",
            'valid': False
        },
        'upcat': {
            'title': 'Update Categories',
            'subtitle': 'Update transaction categories',
            'autocomplete': 'upcat',
            'args': ' --upcat',
            'icon': "icons/ui/refresh.png",
            'valid': True
        },
        'filter': {
            'title': 'Filter by Account',
            'subtitle': 'Add account to permanent filter by account',
            'autocomplete': 'filter ',
            'args': ' --filter',
            'icon': "icons/ui/filter.png",
            'valid': False
        },
        'nick': {
            'title': 'Nickname Account',
            'subtitle': 'Set a nickname for an account',
            'autocomplete': 'nick ',
            'args': ' --nick',
            'icon': "icons/ui/nickname.png",
            'valid': False
        },
        'clientid': {
            'title': 'Set Client ID',
            'subtitle': 'Set client ID for Plaid',
            'autocomplete': 'clientid ',
            'args': ' --clientid '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/key.png",
            'valid': len(words) > 1
        },
        'secret': {
            'title': 'Set secret',
            'subtitle': f'Set secret for Plaid {environ} environment',
            'autocomplete': 'secret ',
            'args': ' --secret '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/password.png",
            'valid': len(words) > 1
        },
        'userid': {
            'title': 'Set User ID',
            'subtitle': f'Set user ID for Plaid {environ}',
            'autocomplete': 'userid ',
            'args': ' --userid '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/username.png",
            'valid': len(words) > 1
        },
        'pubtoken': {
            'title': 'Set Public Token',
            'subtitle': 'Set public token for Plaid',
            'autocomplete': 'pubtoken ',
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
        'proto': {
            'title': 'Set Link Server Protocol',
            'subtitle': 'Choose HTTP(S) for link server',
            'autocomplete': 'proto ',
            'args': ' --proto '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/https.png",
            'valid': len(words) > 1 and words[1] in protos
        },
        'act': {
            'title': 'Choose an Account',
            'subtitle': 'Choose an account to filter by or nickname',
            'autocomplete': 'act:',
            'args': ' --acctid '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/account.png",
            'valid': False
        },
        'cat': {
            'title': 'Choose a category',
            'subtitle': 'Choose a transaction category',
            'autocomplete': 'cat:',
            'args': ' --catid '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/categories.png",
            'valid': False
        },
        'cht': {
            'title': 'Add a chart to query results',
            'subtitle': 'Add a chart option to query results',
            'autocomplete': 'cht: ',
            'args': ' --chtid '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/chart.png",
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
            'title': 'Add a Time Period Filter',
            'subtitle': 'Filter results to certain time periods',
            'autocomplete': 'dt:',
            'args': ' --dt '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/timeperiod.png",
            'valid': False
        },
        'dtf': {
            'title': 'Add a Date From Filter',
            'subtitle': 'Filter results to only after this date',
            'autocomplete': 'dtf:',
            'args': ' --dtf '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/dateafter.png",
            'valid': False
        },
        'dtt': {
            'title': 'Add a Date To Filter',
            'subtitle': 'Filter results to only before this date',
            'autocomplete': 'dtt:',
            'args': ' --dtt '+(words[1] if len(words)>1 else ''),
            'icon': "icons/ui/datebefore.png",
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
                'subtitle': lambda x,y: f"Set environment to {x}" if get_environment(wf) != x else f"Current environment is {x}",
                'arg': lambda x, y: f"--environment {x}",
                'suffix': ' ',
                'options': environments,
                'valid': True
        },
        'proto': {
                'name': 'protocol',
                'title': lambda x: f"Use {x} for link server",
                'subtitle': lambda x,y: f"Set protocol to {x}{'. NOTE: Browser will warn of not trusted site with https' if 'https' == x else ''}" if get_protocol(wf) != x else f"Current protocol is {x}",
                'arg': lambda x, y: f"--proto {x}",
                'suffix': ' ',
                'options': protos,
                'valid': True
        },
        'dt': {
                'name': 'date range',
                'title': lambda x: f"{x}",
                'subtitle': lambda x,y: f"Filter transactions within {x.lower()}",
                'icon': lambda x: f"icons/ui/{x.split()[1]}.png",
                'suffix': '\:',
                'options': timeframes,
                'id': lambda x: x.lower().replace(' ','-'),
                'valid': False            
        },
        'cat': {
                'name': 'categories',
                'title': lambda x: f"{x['list'][-1]}",
                'subtitle': lambda x,y: f"{' > '.join(x['list'])}",
                'icon': lambda x: f"{x['icon']}",
                'suffix': '\:',
                'options': categories,
                'filter_func': lambda x: f"{', '.join(categories[x]['list'])}",
                'id': lambda x: x if 0 != x else None,
                'valid': False            
        },
        'act': {
                'name': 'accounts',
                'special_items_func': add_all_accounts,
                'title': lambda x: f"{x['nick'] if 'nick' in x else x['name']}",
                'subtitle': lambda x,y: ('Remove' if x['account_id'] in acct_filter else 'Add')+' this account to filter' if 'filter' in y else ('Set account nickname to '+extract_nick(y) if 'nick' in y else (f"{banks[x['institution_id']]['name']} {get_acct_subtitle(x)}")),
                'icon': lambda x: f"{banks[x['institution_id']]['icon']}",
                'suffix': '\:',
                'arg': lambda x, y: f"{'--filter ' if 'filter ' in y else ''}{'--nick '+quote(extract_nick(y)) if 'nick ' in y else ''} --acctid {x}",
                'options': accounts,
                'filter_func': lambda x: f"{banks[accounts[x]['institution_id']]['name']} {accounts[x]['name']} {accounts[x]['subtype']} {accounts[x]['nick'] if 'nick' in accounts[x] else ''} {x}",
                'valid': lambda x, y: True if ('nick ' in x and len(words) > 2) or ('filter ' in x) else False        
        },
        'link': {
                'name': 'items',
                'special_items_func': add_new_link,
                'title': lambda x: banks[x['institution_id']]['name'],
                'subtitle': lambda x,y: f"{'*ERROR* ' if x['error'] else ''} Update link to {banks[x['institution_id']]['name']}",
                'icon': lambda x: banks[x['institution_id']]['icon'] if not x['error'] else 'icons/ui/broken.png',
                'suffix': ' ',
                'arg': lambda x, y: f"--link {x}",
                'options': items,
                'filter_func': lambda x: banks[items[x]['institution_id']]['name'],
                'valid': True            
        },
        'del': {
                'name': 'delete',
                'title': lambda x: banks[x['institution_id']]['name'],
                'subtitle': lambda x,y: f"{'*ERROR* ' if x['error'] else ''} Remove all accounts and link to {banks[x['institution_id']]['name']}",
                'icon': lambda x: banks[x['institution_id']]['icon'] if 'error' not in x or not x['error'] else 'icons/ui/broken.png',
                'suffix': ' ',
                'arg': lambda x, y: f"--delete {x}",
                'options': items,
                'filter_func': lambda x: banks[items[x]['institution_id']]['name'],
                'valid': True            
        },
        'refresh': {
                'name': 'items',
                'special_items_func': add_refresh_all,
                'title': lambda x: banks[x['institution_id']]['name'],
                'subtitle': lambda x,y: f"{'*ERROR* ' if x['error'] else ''} Force refresh of transactions from {banks[x['institution_id']]['name']}",
                'icon': lambda x: banks[x['institution_id']]['icon'] if not x['error'] else 'icons/ui/broken.png',
                'suffix': ' ',
                'arg': lambda x, y: f"--refresh {x}",
                'options': items,
                'filter_func': lambda x: banks[items[x]['institution_id']]['name'],
                'valid': True            
        },
        'ct': {
                'name': 'chart type',
                'title': lambda x: f"{x}",
                'subtitle': lambda x,y: f"Chart type {x.lower()}",
                'options': chart_types,
                'suffix': '\:',
                'set': {'holder': chart_options, 'field': 'ct'},
                'valid': False                        
        },
        'ta': {
                'name': 'time aggregates',
                'title': lambda x: f"Aggregate transactions over {x}s",
                'subtitle': lambda x,y: f"Totals transactions with a {x.lower()} for charting",
                'options': time_aggregates,
                'suffix': '\:',
                'set': {'holder': chart_options, 'field': 'ta'},
                'valid': False                                    
        },
        'ma': {
                'name': 'time aggregates',
                'title': lambda x: f"Aggregate transactions by {x}",
                'subtitle': lambda x,y: f"Totals transactions by {x.lower()} for charting",
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


    client_id = get_secure_value(wf, 'client_id', None, ALL_USER, ALL_ENV)
    if not client_id:
        wf.add_item('No Client ID key set...',
                    'Please use pd clientid to set your Plaid Client ID.',
                    autocomplete='clientid ',
                    valid=False,
                    icon="icons/ui/warning.png")
        wf.send_feedback()
        return 0

    secret = get_secure_value(wf, 'secret', None, ALL_USER)
    if not secret:
        wf.add_item(f'No Client Secret key set for {environ}...',
                    'Please use pd secret to set your Plaid Client Secret.',
                    autocomplete='secret ',
                    valid=False,
                    icon="icons/ui/warning.png")
#        wf.send_feedback()
#        return 0
        
    user_id = get_current_user(wf)
    if not user_id:
        wf.add_item(f'No {get_environment(wf)} User set...',
                    'Please use pd userid to set your User ID - can be anything you choose',
                    autocomplete='userid ',
                    valid=False,
                    icon="icons/ui/warning.png")
#        wf.send_feedback()
#        return 0

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
        
    add_item_errors(wf, query)
    
    items = get_secure_value(wf, 'items', None)
    if not items:
        wf.add_item('No Linked Financial Institutions Found...',
                    'Please use pd link to link your bank accounts',
                    autocomplete='link ',
                    valid=False,
                    icon="icons/ui/no-bank.png")
    
    if items and (not accounts or len(accounts) < 1):
        wf.add_item('No Accounts...',
                    'Please use pd update - to update your Accounts and Transactions.',
                    autocomplete='update ',
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
            if not is_array: opts = list(opts.keys())
            found = re.findall(fr'{opt}{suffix}([^\s]+)', query)
            term = found[0] if found else ''
            if re.findall(fr'{opt}{suffix}[^\s]*\s*$', query):
                matches = wf.filter(term, opts, config_options[opt]['filter_func'] if 'filter_func' in config_options[opt] else (lambda x: x if is_array else config_options[opt]['options'][x]))
                prequery = re.sub(fr'{opt}{suffix}[^\s]*\s*$','',query)
                if 'special_items_func' in config_options[opt]:
                    config_options[opt]['special_items_func'](wf, prequery, opts)
                for item in matches:
                    name = item if is_array else config_options[opt]['options'][item]
                    id = config_options[opt]['id'](item) if 'id' in config_options[opt] else item
                    if not id: continue
                    icon = config_options[opt]['icon'](name) if 'icon' in config_options[opt] else f"icons/ui/{name.lower().replace(' ','-')}.png"
                    valid = config_options[opt]['valid']
                    if type(valid) is not bool:
                        valid = valid(prequery, item)
                    suffix = suffix.replace("\\",'')
                    wf.add_item(
                            title=config_options[opt]['title'](name),
                            subtitle=config_options[opt]['subtitle'](name, prequery),
                            autocomplete=f"{prequery}{opt}{suffix}{id} ",
                            arg=config_options[opt]['arg'](item, prequery) if 'arg' in config_options[opt] else '',
                            valid=valid,
                            icon=icon
                    )
            if found:
                #log.debug(f'found {term} with {opts}')
                if term and (term in opts):
                    if 'set' in config_options[opt]:
                        config_options[opt]['set']['holder'][config_options[opt]['set']['field']] = term
    
    
        db = TxnDB(get_db_file(wf), wf.logger)
        acct_filter = get_secure_value(wf, 'acct_filter', [])
        if acct_filter: query = f"{query} act:{','.join(acct_filter)}"
        txns = db.get_results(query)
        if not txns:
            if items and accounts:
                wf.add_item(
                        title="No matching transactions found...",
                        subtitle="Please try another search term",
                        valid=False,
                        icon="icons/ui/empty.png"
                )
        else:
            if 'cht:' in query:
                wf.add_item(
                    title="Chart the transactions",
                    subtitle=f"Highlight and tap SHIFT key for {chart_types[chart_options['ct']]} chart aggregated by {time_aggregates[chart_options['ta']]} and {merchant_aggregates[chart_options['ma']]}",
                    valid=False,
                    quicklookurl=get_chart_url(wf,txns),
                    icon='icons/ui/chart.png'
                )
            txn_list = txns #[:30] if len(txns) > 30 else txns                
            query, cat_id = extract_filter(query, 'cat', 'text')
            query, txn_id = extract_filter(query, 'txn', 'text')
            custom_categories = get_stored_data(wf, 'custom_categorization', {})
            for txn in txn_list:
                merchant_id = txn['merchant_id']
                acct = accounts[txn['account_id']]
                post = format_post_date(txn['post'])
                acct_name = acct['nick'] if 'nick' in acct else acct['name']

                if not cat_id or not txn_id:
                    category_id = get_category(wf, txn, custom_categories)
                    category = ' > '.join(categories[category_id]['list'])
                    subtitle = f"{acct_name} | {category}     {txn['txntext']}"
                else:
                    category = ' > '.join(categories[int(cat_id)]['list'])
                    subtitle = f"Change category to {category}"
                merchant = txn['merchant'] if txn['merchant'] else ''
                txntext = txn['txntext']
                title = merchant if merchant else txntext
                #log.debug(f"{merchant_id} | {txn['txntext']} | {merchant}")
                title = title.ljust(50)
                arg = f' --merchant_id {merchant_id}' if cat_id and merchant_id else ''
                if not arg:
                    arg = f" --merchant {quote(merchant)}" if cat_id and (not merchant_id  and merchant) else ''
                if not arg:
                    arg = f" --txntext {quote(txntext)}" if cat_id and (not merchant_id  and txntext) else ''
                arg = arg + f' --category_id {cat_id}' if cat_id else ''
                wf.add_item(
                        title=f"{post}    {title}    ${txn['amount']:.2f}",
                        subtitle=subtitle,
                        autocomplete=f"txn:{txn['transaction_id']} ",
                        arg=arg,
                        valid=('--merchant' in arg or '--txntext' in arg) and '--category_id' in arg,
                        icon=get_txn_icon(wf, txn, accounts, banks, merchants, categories, icons)
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
    