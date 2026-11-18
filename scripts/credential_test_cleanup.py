"""Pure validation of the owned dummy-credential helper's deletion receipt."""


def credential_delete_failure(response, expected_reference):
    """Return bounded diagnostics, never a secret, arbitrary payload or message."""
    if not isinstance(response, dict):
        return {'code': 'CREDENTIAL_CLEANUP_DELETE_INVALID_RESPONSE'}
    result = response.get('result')
    valid_result = type(result) is int and 0 <= result <= 6
    if (response.get('ok') is True and valid_result and result == 0
            and response.get('credential_ref') == expected_reference):
        return None
    failure = {'code': 'CREDENTIAL_CLEANUP_DELETE_NOT_ACKNOWLEDGED'}
    if valid_result:
        failure['native_result'] = result
    return failure
