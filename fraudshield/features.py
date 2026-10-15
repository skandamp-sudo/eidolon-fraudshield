"""Leakage-aware features shared by training and inference.

PaySim schema: step, type, amount (+ balances accepted for display).
The PaySim dataset authors warn that both pre- and post-transaction balance
fields can leak the target because fraud is cancelled. We intentionally exclude
ALL balance fields, isFraud, and isFlaggedFraud from model features.
"""
from __future__ import annotations
import math

FEATURE_NAMES = [
    'log_amount', 'high_value_5k', 'high_value_20k', 'high_value_100k',
    'is_transfer', 'is_cash_out', 'is_cash_in', 'is_payment', 'is_debit',
    'overnight_simulated_hour',
]

TYPES = {'TRANSFER', 'CASH_OUT', 'CASH_IN', 'PAYMENT', 'DEBIT'}

def clean_event(payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError('Transaction must be a JSON object')
    try:
        step = int(payload.get('step', 1))
        tx_type = str(payload['type']).upper().strip()
        amount = float(payload['amount'])
        origin = float(payload.get('oldbalanceOrg', 0))
        dest = float(payload.get('oldbalanceDest', 0))
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Invalid transaction fields: step, type, amount, oldbalanceOrg, oldbalanceDest') from exc
    if tx_type not in TYPES:
        raise ValueError('type must be TRANSFER, CASH_OUT, CASH_IN, PAYMENT or DEBIT')
    if step < 0 or step > 10_000_000 or any(not math.isfinite(x) or x < 0 or x > 1e12 for x in (amount, origin, dest)):
        raise ValueError('Invalid step or amount/balance values')
    txid = str(payload.get('transactionId', '')).strip()[:80]
    return dict(step=step, type=tx_type, amount=amount, oldbalanceOrg=origin,
                oldbalanceDest=dest, transactionId=txid)

def vector(event: dict) -> list[float]:
    amount = event['amount']
    tx_type = event['type']
    return [
        min(math.log1p(amount) / 13.0, 2.5),
        float(amount > 5_000),
        float(amount > 20_000),
        float(amount > 100_000),
        float(tx_type == 'TRANSFER'),
        float(tx_type == 'CASH_OUT'),
        float(tx_type == 'CASH_IN'),
        float(tx_type == 'PAYMENT'),
        float(tx_type == 'DEBIT'),
        float(event['step'] % 24 in (0, 1, 2, 3, 4, 5)),
    ]

FEATURE_DESCRIPTIONS = {
    'log_amount': 'Transaction value signal',
    'high_value_5k': 'Transaction exceeds 5,000-unit demo threshold',
    'high_value_20k': 'Transaction exceeds 20,000-unit demo threshold',
    'high_value_100k': 'Transaction exceeds 100,000-unit demo threshold',
    'is_transfer': 'Transfer transaction pattern',
    'is_cash_out': 'Cash-out transaction pattern',
    'is_cash_in': 'Cash-in transaction pattern',
    'is_payment': 'Payment transaction pattern',
    'is_debit': 'Debit transaction pattern',
    'overnight_simulated_hour': 'Overnight activity (simulation time step)',
}
