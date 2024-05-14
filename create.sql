BEGIN;
CREATE TABLE IF NOT EXISTS transactions(
    id integer primary key autoincrement, 
    transaction_id text unique,
    account_id text, 
    currency text,
    channel text,
    auth datetime,
    post datetime,
    amount real,
    subtype text,
    merchant text,
    merchant_id text,
    institution text,
    txntext text,
    category_id text,
    categories text
);
CREATE VIRTUAL TABLE IF NOT EXISTS txn_fts USING fts5(
    subtype,
    merchant,
    institution,
    categories,
    content=transactions,
    content_rowid=id
);
CREATE INDEX IF NOT EXISTS txn_post_idx on transactions(post);
CREATE INDEX IF NOT EXISTS txn_amount_idx on transactions(amount);

/* triggers to keep the FTS tables up to date */
CREATE TRIGGER txn_ai AFTER INSERT ON transactions BEGIN
  INSERT INTO txn_fts(rowid, subtype, merchant, institution, categories) VALUES (new.id, new.subtype, new.merchant, new.institution, new.categories);
END;
CREATE TRIGGER txn_ad AFTER DELETE ON transactions BEGIN
  INSERT INTO txn_fts(txn_fts, rowid, subtype, merchant, institution, categories) VALUES ('delete', old.id, old.subtype, old.merchant, old.institution, old.categories);
END;
CREATE TRIGGER txn_au AFTER UPDATE ON transactions BEGIN
  INSERT INTO txn_fts(txn_fts, rowid, subtype, merchant, institution, categories) VALUES ('delete', old.id, old.subtype, old.merchant, old.institution, old.categories);
  INSERT INTO txn_fts(rowid, subtype, merchant, institution, categories) VALUES (new.id, new.subtype, new.merchant, new.institution, new.categories);
END;
COMMIT;