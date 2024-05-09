import sqlite3
import os
from time import time
import struct
from datetime import datetime
from dateutil.parser import parse
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
            
    def save_txn(self, txn):
        account_id = txn['account_id']
        auth = datetime.strptime(txn['authorized_date'], '%Y-%m-%d') if 'authorized_date' in txn and txn['authorized_date'] else None
        post = datetime.strptime(txn['date'], '%Y-%m-%d')
        amount = txn['amount']
        categories = ','.join(txn['category'])
        category_id = txn['category_id']
        currency = txn['iso_currency_code']
        merchant = txn['merchant_name']
        channel = txn['payment_channel']
        txntext = txn['name']
        subtype = txn['subtype'] if 'subtype' in txn else ''
        txn_id = txn['transaction_id']
        con = sqlite3.connect(self.file)
        with con:
            cur = con.cursor()
            cur.execute("""INSERT OR IGNORE INTO
                        transactions (transaction_id, account_id, currency, post, auth, channel, amount, subtype, merchant, categories, category_id, txntext)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (txn_id, account_id, currency, post, auth, channel, amount, subtype, merchant, categories, category_id, txntext))


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
    
    def extract_filter(self, query, token, type):
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
    
    def get_results(self, query):
        query, date_from = self.extract_filter(query, 'dtf', 'date')
        query, date_to = self.extract_filter(query, 'dtt', 'date')
        query, amt_from = self.extract_filter(query, 'amtf', 'number')
        query, amt_to = self.extract_filter(query, 'amtt', 'number')
        query, sort = self.extract_filter(query, 'srt', 'text')
        query, order = self.extract_filter(query, 'ord', 'text')
        query, acct = self.extract_filter(query, 'act', 'text')
        sort = sort if sort else 'post'
        order = order if order else 'DESC'
        dtf = f" AND post >= :dtf" if date_from else ''
        dtt = f" AND post <= :dtt" if date_to else ''
        amtf = f" AND amount >= :amtf" if amt_from else ''
        amtt = f" AND amount <= :amtt" if amt_to else ''
        acctq = f" AND account_id = :acct" if acct else ''
        query = ' '.join([x+'*' if ':' not in x else '' for x in query.strip().split()])
        params = {'query': query, 'amtt': amt_to, 'amtf': amt_from, 'dtt': date_to, 'dtf': date_from, 'srt': sort, 'ord': order, 'acct': acct}
        self.debug(params)
        if not query: return None
            
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
                    SELECT transaction_id, account_id, txntext, subtype, merchant, post, currency, amount, category_id, categories 
                    FROM transactions 
                    WHERE id IN (SELECT rowid from txn_fts WHERE txn_fts MATCH :query ORDER BY rank DESC){dtt}{dtf}{amtt}{amtf}{acctq} ORDER BY {sort} {order}"""
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