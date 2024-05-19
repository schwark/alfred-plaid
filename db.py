import sqlite3
import os
from time import time
import struct
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from common import extract_filter, get_category, category_name
import re

class TxnDB:
    def __init__(self, file, logger=None):
        self.file = file
        self.logger = logger
        if not os.path.exists(self.file):
            self.create_db()
                 
    def debug(self, text):
        if(self.logger): self.logger.debug(text)
        
    def create_db(self):
        """Create a "virtual" table, which sqlite3 uses for its full-text search

        Given the size of the original data source (~45K entries, 5 MB), we'll put
        *all* the data in the database.

        Depending on the data you have, it might make more sense to only add
        the fields you want to search to the search DB plus an ID (included here
        but unused) with which you can retrieve the full data from your full
        dataset.
        """
        self.debug('Creating transactions database')
        sqlfile = open('create.sql','r')
        sql = sqlfile.read()
        sqlfile.close()
        con = sqlite3.connect(self.file)
        with con:
            cur = con.cursor()
            cur.executescript(sql)
            
    def update_txn_category(self, category_id, merchant_id, merchant, txntext, cat_name):
        column_value = merchant_id if merchant_id else (merchant if merchant else txntext)
        params = {'category_id': int(category_id), 'categories': cat_name, 'column_value': column_value}
        column = 'merchant_id' if merchant_id else ('merchant' if merchant else 'txntext')
        con = sqlite3.connect(self.file)
        with con:
            cur = con.cursor()
            sql = f"""UPDATE transactions SET category_id=:category_id, categories=:categories
                            WHERE {column}=:column_value"""
            self.logger.debug(f"{sql}: {column} {column_value}")
            cur.execute(sql, params,)

            
    def save_txn(self, txn, wf):
        account_id = txn['account_id']
        auth = datetime.strptime(txn['authorized_date'], '%Y-%m-%d') if 'authorized_date' in txn and txn['authorized_date'] else None
        post = datetime.strptime(txn['date'], '%Y-%m-%d')
        amount = txn['amount']
        category_id = get_category(wf, txn)
        categories = category_name(wf, category_id, True)
        currency = txn['iso_currency_code']
        merchant = txn['merchant_name']
        merchant_id = txn['merchant_entity_id']
        channel = txn['payment_channel']
        txntext = txn['name']
        subtype = txn['subtype'] if 'subtype' in txn else ''
        txn_id = txn['transaction_id']
        con = sqlite3.connect(self.file)
        with con:
            cur = con.cursor()
            cur.execute("""INSERT OR IGNORE INTO
                        transactions (transaction_id, account_id, currency, post, auth, channel, amount, subtype, merchant, merchant_id, categories, category_id, txntext)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (txn_id, account_id, currency, post, auth, channel, amount, subtype, merchant, merchant_id, categories, category_id, txntext))


    # Search ranking function
    # Adapted from http://goo.gl/4QXj25 and http://goo.gl/fWg25i
    def make_rank_func(self, weights):
        """`weights` is a list or tuple of the relative ranking per column.

        Use floats (1.0 not 1) for more accurate results. Use 0 to ignore a
        column.
        """
        def rank(matchinfo):
            # matchinfo is defined as returning 32-bit unsigned integers
            # in machine byte order
            # http://www.sqlite.org/fts3.html#matchinfo
            # and struct defaults to machine byte order
            bufsize = len(matchinfo)  # Length in bytes.
            matchinfo = [struct.unpack(b'I', matchinfo[i:i + 4])[0]
                        for i in range(0, bufsize, 4)]
            it = iter(matchinfo[2:])
            return sum(x[0] * w / x[1]
                    for x, w in zip(zip(it, it, it), weights)
                    if x[1])
        return rank
        
    def parse_dt(self, dt):
        date_from = None
        date_to = None
        if not dt: return date_from, date_to
        dt = dt.lower().split('-')
        if len(dt) > 1:
            now = datetime.now()
            if 'this' in dt[0]:
                date_to = now
                if 'week' in dt[1]:
                    date_from = now - timedelta(days=datetime.today().isoweekday() % 7)
                elif 'month' in dt[1]:
                    date_from = now.replace(day=1,hour=0,minute=0,second=0)
                elif 'quarter' in dt[1]:
                    currQuarter = (now.month - 1) / 3 + 1
                    date_from = datetime(now.year, int(3 * currQuarter - 2), 1)
                elif 'half' in dt[1]:
                    currQuarter = (now.month - 1) / 3 + 1
                    date_from = datetime(now.year, int(3 * currQuarter - 2), 1) - relativedelta(months=3)
                elif 'year' in dt[1]:    
                    date_from = now.replace(day=1,month=1,hour=0,minute=0,second=0)
            elif 'last' in dt[0]:
                if 'week' in dt[1]:
                    date_from = now - timedelta(days=datetime.today().isoweekday() % 7 + 7)
                    date_to = date_from + timedelta(days=7)
                elif 'month' in dt[1]:
                    date_from = now.replace(day=1,hour=0,minute=0,second=0) - relativedelta(months=1)
                    date_to = date_from + relativedelta(months=1,days=-1)
                elif 'quarter' in dt[1]:
                    currQuarter = (now.month - 1) / 3 + 1
                    date_from = datetime(now.year, int(3 * currQuarter - 2), 1) - relativedelta(months=3)
                    date_to = date_from + relativedelta(months=3, days=-1)
                elif 'half' in dt[1]:
                    currQuarter = (now.month - 1) / 3 + 1
                    date_from = datetime(now.year, int(3 * currQuarter - 2), 1) - relativedelta(months=6)
                    date_to = date_from + relativedelta(months=6, days=-1)
                elif 'year' in dt[1]:    
                    date_from = now.replace(day=1,month=1,hour=0,minute=0,second=0) - relativedelta(years=1)
                    date_to = date_from + relativedelta(years=1, days=-1)
        return date_from, date_to
    
    def get_results(self, query):
        self.debug(f"{query}")
        query, date_from = extract_filter(query, 'dtf', 'date')
        query, date_to = extract_filter(query, 'dtt', 'date')
        query, amt_from = extract_filter(query, 'amtf', 'number')
        query, amt_to = extract_filter(query, 'amtt', 'number')
        query, sort = extract_filter(query, 'srt', 'text')
        query, order = extract_filter(query, 'ord', 'text')
        query, acct = extract_filter(query, 'act', 'text')
        query, dt = extract_filter(query, 'dt', 'text')
        query, cat = extract_filter(query, 'cat', 'text')
        query, txn = extract_filter(query, 'txn', 'text')
        self.debug(f"{dt}")
        if dt:
            dfro, dto = self.parse_dt(dt)
            date_from = dfro if dfro and not date_from else date_from
            date_to = dto if dto and not date_to else date_to
        if cat:
            if re.match(r'^\d+$', cat):
                pat = re.compile(r'([0-9]*)([1-9])(0+)$')
                groups = pat.match(str(cat))
                cat = int(cat)
                max_cat = int(groups[1]+str(int(groups[2])+1)+groups[3]) if groups else cat+1
            else:
                cat = None
        else:
            max_cat = 0
        sort = sort if sort else 'post'
        order = order if order else 'DESC'
        dtf = f" AND post >= :dtf" if date_from else ''
        dtt = f" AND post <= :dtt" if date_to else ''
        amtf = f" AND amount >= :amtf" if amt_from else ''
        amtt = f" AND amount <= :amtt" if amt_to else ''
        acctq = f" AND account_id IN (:acct)" if acct else ''
        catq = f" AND category_id >= :cat AND category_id < :max_cat" if cat else ''
        txnq = f" AND transaction_id = :txn" if txn else ''
        catq = catq if not txn else '' # if txn_id is specified cat is ignored
        termsearch = f"id IN (SELECT rowid from txn_fts WHERE txn_fts MATCH :query ORDER BY rank DESC)"
        query = ' '.join([x+'*' if ':' not in x else '' for x in query.strip().split()]).strip()
        params = {'query': query, 'amtt': amt_to, 'amtf': amt_from, 'dtt': date_to, 'dtf': date_from, 'srt': sort, 'ord': order, 'acct': acct, 'cat': cat, 'max_cat': max_cat, 'txn': txn}
        termsearch = termsearch if query else 'id IS NOT NULL'
        self.debug(params)
        if not (query or dtf or dtt or amtf or amtt or catq or txnq): return None
            
        # Search!
        start = time()
        db = sqlite3.connect(self.file)
        db.row_factory = sqlite3.Row
        # Set ranking function with weightings for each column.
        # `make_rank_function` must be called with a tuple/list of the same
        # length as the number of columns "selected" from the database.
        # In this case, `url` is set to 0 because we don't want to search on
        # that column
        db.create_function('rank', 1, self.make_rank_func((1.0, 1.0, 0, 0)))
        cursor = db.cursor()
        try:
            sql = f"""
                    SELECT transaction_id, account_id, txntext, subtype, merchant, merchant_id, post, currency, amount, category_id, categories 
                    FROM transactions 
                    WHERE {termsearch}{dtt}{dtf}{amtt}{amtf}{catq}{acctq}{txnq} ORDER BY {sort} {order}"""
            self.debug(sql)
            cursor.execute(sql, params, )
            results = cursor.fetchall()
        except sqlite3.OperationalError as err:
            # If the query is invalid, show an appropriate warning and exit
            if b'malformed MATCH' in err:
                self.debug(f'Invalid Query {query}')           # Otherwise raise error for Workflow to catch and log
            else:
                raise err
            
        self.debug('{} results for `{}` in {:0.3f} seconds'.format(
                len(results), query, time() - start))
        return results