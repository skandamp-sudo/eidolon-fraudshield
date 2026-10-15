"""SQLite event store. Separate connections make threaded HTTP access safe."""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import json, sqlite3
from pathlib import Path

class Store:
    def __init__(self,path):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self._init()

    @contextmanager
    def connection(self):
        con=sqlite3.connect(self.path,timeout=10)
        con.row_factory=sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def _init(self):
        with self.connection() as con:
            con.execute('PRAGMA journal_mode=WAL')
            con.executescript('''
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              txid TEXT NOT NULL, created_at TEXT NOT NULL,
              step INTEGER NOT NULL, type TEXT NOT NULL,
              amount REAL NOT NULL, old_balance REAL NOT NULL,
              dest_balance REAL NOT NULL, score REAL NOT NULL,
              tier TEXT NOT NULL, decision TEXT NOT NULL,
              reasons TEXT NOT NULL, source TEXT NOT NULL,
              truth INTEGER, reviewed_as TEXT NOT NULL DEFAULT 'UNREVIEWED'
            );
            CREATE TABLE IF NOT EXISTS reviews (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              event_id INTEGER NOT NULL, reviewed_at TEXT NOT NULL,
              disposition TEXT NOT NULL,
              FOREIGN KEY(event_id) REFERENCES events(id)
            );
            CREATE INDEX IF NOT EXISTS idx_events_created ON events(id DESC);
            CREATE INDEX IF NOT EXISTS idx_events_tier ON events(tier);
            ''')

    def insert(self,event,result,source='manual',truth=None):
        at=datetime.now(timezone.utc).isoformat(timespec='seconds')
        with self.connection() as con:
            cur=con.execute('''INSERT INTO events
            (txid,created_at,step,type,amount,old_balance,dest_balance,score,tier,decision,reasons,source,truth)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (event.get('transactionId') or 'MANUAL',at,event['step'],event['type'],event['amount'],
             event['oldbalanceOrg'],event['oldbalanceDest'],result['score'],result['tier'],
             result['decision'],json.dumps(result['reasons']),source,truth))
            return cur.lastrowid

    @staticmethod
    def public(row):
        out=dict(row)
        out['reasons']=json.loads(out['reasons'])
        return out

    def events(self,limit=60):
        with self.connection() as con:
            return [self.public(r) for r in con.execute('SELECT * FROM events ORDER BY id DESC LIMIT ?', (max(1,min(int(limit),200)),))]

    def summary(self):
        with self.connection() as con:
            row=con.execute('''SELECT COUNT(*) AS total,
              COALESCE(SUM(tier='HIGH'),0) AS high,
              COALESCE(SUM(tier='MEDIUM'),0) AS medium,
              COALESCE(SUM(tier IN ('HIGH','MEDIUM') AND reviewed_as='UNREVIEWED'),0) AS pending,
              COALESCE(SUM(tier='LOW'),0) AS low,
              COALESCE(SUM(amount),0) AS volume,
              COALESCE(AVG(score),0) AS average_score,
              COALESCE(SUM(reviewed_as != 'UNREVIEWED'),0) AS reviewed,
              COALESCE(SUM(truth=1),0) AS synthetic_fraud
              FROM events''').fetchone()
            points=[dict(r) for r in con.execute('''SELECT tier,COUNT(*) AS count FROM events
              WHERE id > (SELECT MAX(id)-100 FROM events) GROUP BY tier''')]
            return {**dict(row),'recent_distribution':points}

    def review(self,event_id:int,disposition:str):
        if disposition not in {'CONFIRMED_FRAUD','FALSE_POSITIVE','INVESTIGATING'}:
            raise ValueError('Invalid review disposition')
        with self.connection() as con:
            cur=con.execute('UPDATE events SET reviewed_as=? WHERE id=?',(disposition,event_id))
            if cur.rowcount==0: raise KeyError('Event not found')
            con.execute('INSERT INTO reviews(event_id,reviewed_at,disposition) VALUES (?,?,?)',
                        (event_id,datetime.now(timezone.utc).isoformat(timespec='seconds'),disposition))

    def reset(self):
        with self.connection() as con:
            con.execute('DELETE FROM reviews')
            con.execute('DELETE FROM events')
