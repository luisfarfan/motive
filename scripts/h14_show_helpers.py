"""Pure checks for observed H14 Show Control evidence; no production access."""
import re


def _check(condition, message, **context):
    if not condition:
        raise AssertionError({'check': message, **context})


def native_animation_id(token, session):
    """Parse the exact owner namespace, native animation ID and token serial."""
    _check(isinstance(session, str) and bool(session), 'nonempty owner session', session=session)
    prefix = session + ':animation:'
    _check(isinstance(token, str) and token.startswith(prefix),
           'animation token belongs to owner session', token=token, session=session)
    parts = token[len(prefix):].split(':')
    _check(len(parts) == 2 and all(re.fullmatch(r'[1-9][0-9]*', part) for part in parts),
           'animation token has positive native ID and serial', token=token)
    return int(parts[0])


def composite_receipt(job, session, pid):
    """Validate the complete composite-to-counter result, irrespective of record order."""
    _check(isinstance(job, dict), 'job is an object', job=job)
    context = {'job_id': job.get('id')}
    _check(type(pid) is int and pid > 0, 'positive owner PID', pid=pid, **context)
    _check(job.get('state') == 'completed' and job.get('cursor') == 2,
           'two-action composite sequence completed', state=job.get('state'),
           cursor=job.get('cursor'), **context)
    records = job.get('records')
    _check(isinstance(records, list) and len(records) == 2,
           'composite and counter records are present', records=records, **context)
    _check(all(isinstance(record, dict) and type(record.get('index')) is int
               for record in records), 'records have integer action indices', **context)
    indexed = {record['index']: record for record in records}
    _check(set(indexed) == {0, 1}, 'unique composite and counter indices',
           indices=[record['index'] for record in records], **context)
    composite, counter = indexed[0], indexed[1]
    _check(composite.get('stage') == 'completed', 'composite action completed', **context)
    _check(counter.get('stage') == 'completed' and counter.get('operation_id') is None,
           'local counter completed without native operation', **context)
    token = composite.get('operation_id')
    operation_id = native_animation_id(token, session)
    receipts = composite.get('revision_receipts')
    _check(isinstance(receipts, list) and len(receipts) == 2,
           'composite has dispatch and terminal receipts', receipts=receipts, **context)
    _check(all(isinstance(receipt, dict) for receipt in receipts),
           'mutation receipts are objects', **context)
    action_key = receipts[0].get('action_key')
    _check(isinstance(action_key, str) and bool(action_key),
           'mutation receipts identify an action', action_key=action_key, **context)
    for index, receipt in enumerate(receipts):
        _check(receipt.get('action_key') == action_key and receipt.get('operation_id') == token,
               'receipt matches composite action and token', receipt_index=index, **context)
        before, after = receipt.get('before'), receipt.get('after')
        for label, version in [('before', before), ('after', after)]:
            _check(isinstance(version, dict) and type(version.get('pid')) is int
                   and version['pid'] == pid and type(version.get('revision')) is int
                   and version['revision'] >= 0,
                   'receipt revision belongs to the owner PID', receipt_index=index,
                   boundary=label, version=version, **context)
        _check(after['revision'] >= before['revision'],
               'receipt revision never regresses', receipt_index=index, **context)
    _check(receipts[0]['after'] == receipts[1]['before'],
           'dispatch and terminal receipts form one exact chain', **context)
    return {'operation_id': operation_id, 'operation_token': token,
            'action_key': action_key, 'receipts': receipts}


def native_cancel_outcome(job, requested_after_started):
    """Classify only an observed native cancellation; a successful request is insufficient."""
    if not isinstance(job, dict) or type(requested_after_started) is not bool:
        return 'NOT_OBSERVED'
    if job.get('phase') == 'failed':
        return 'FAIL'
    if (job.get('phase') == 'cancelled' and job.get('pending_ack') is False
            and type(job.get('started')) is bool
            and job['started'] is requested_after_started
            and type(job.get('widget_triggered')) is bool
            and job['widget_triggered'] is requested_after_started):
        return 'PASS'
    return 'NOT_OBSERVED'


def counter_value(state):
    """Read the tagged goals integer from a complete Production status snapshot."""
    _check(isinstance(state, dict) and isinstance(state.get('show_control'), dict),
           'Production snapshot contains Show Control')
    counters = state['show_control'].get('counters')
    _check(isinstance(counters, dict), 'Show Control counters are an object', counters=counters)
    if 'goals' not in counters:
        return 0
    value = counters['goals']
    _check(isinstance(value, dict) and value.get('type') == 'int'
           and type(value.get('value')) is int,
           'goals counter is a tagged integer', counter=value)
    return value['value']
