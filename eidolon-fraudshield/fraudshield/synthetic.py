"""Seeded, clearly synthetic PaySim-like demo events. NOT bank data."""
import random
from .features import clean_event

TYPES = ('PAYMENT', 'CASH_OUT', 'TRANSFER', 'CASH_IN', 'DEBIT')

def generate(count=1000, seed=77, start_step=1):
    rng = random.Random(seed)
    for i in range(count):
        step = start_step + i // 25
        is_fraud = rng.random() < .065
        tx_type = rng.choices(('TRANSFER', 'CASH_OUT'), (.54, .46))[0] if is_fraud else rng.choices(TYPES, (.43, .27, .17, .09, .04))[0]
        origin = round(rng.lognormvariate(9.4, 1.2), 2)
        dest = round(rng.lognormvariate(9.1, 1.2), 2)
        if is_fraud:
            if rng.random() < .73:
                amount = origin * rng.uniform(.78, 1.14)
            else:
                amount = rng.lognormvariate(10.4, .85)
        else:
            amount = rng.lognormvariate(7.0, 1.45)
            if rng.random() < .065:
                amount = rng.lognormvariate(10.6, .9)
        # Overlap is deliberate. The demonstration should not be trivial or perfect.
        if rng.random() < .035:
            origin = 0
        event = clean_event(dict(step=step, type=tx_type, amount=round(amount, 2),
                                 oldbalanceOrg=origin, oldbalanceDest=dest,
                                 transactionId=f'SIM-{seed}-{i+1:06d}'))
        yield event, int(is_fraud)
