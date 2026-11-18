"""Pure checks for the bounded GPUI concurrency trial; no owner or media access."""
import copy
import pathlib
import re

from h14_collection_helpers import require
from h14_show_helpers import counter_value, native_animation_id


def validate_manifest(value):
    require(set(value) == {'version', 'trial_id', 'owner', 'data_dir', 'project_sha256',
                          'show_control_sha256', 'receiver_ffmpeg'}, 'Unknown trial manifest fields')
    require(type(value['version']) is int and value['version'] == 1, 'Trial manifest v1 required')
    require(re.fullmatch(r'[A-Za-z0-9_-]{1,24}', value['trial_id']) is not None, 'Invalid trial ID')
    require(set(value['owner']) == {'bundle', 'pid', 'sha256'}, 'Exact owner identity required')
    require(type(value['owner']['pid']) is int and value['owner']['pid'] > 0, 'Exact positive owner PID required')
    for digest in (value['owner']['sha256'], value['project_sha256'], value['show_control_sha256']):
        require(isinstance(digest, str) and re.fullmatch(r'[0-9a-f]{64}', digest), 'Explicit SHA-256 required')
    for path in (value['owner']['bundle'], value['data_dir'], value['receiver_ffmpeg']):
        require(isinstance(path, str) and '\0' not in path and pathlib.Path(path).is_absolute(),
                'Explicit absolute local paths required')
    return value


def validate_saved_project(project, pack, initial_graph):
    require(type(project.get('version')) is int and project['version'] == 5, 'Saved project v5 required')
    require(project['variant'] == 'horizontal' and project['audio'] == 'none'
            and project['capture_window'] is False and project['window'] is None and project['camera'] is None,
            'Saved project must contain no physical capture or legacy audio')
    require(project['video'] == {'version': 1, 'resolution': 'full_hd1080', 'fps': 30,
                                'coordinate_space': 'design960'}, 'Reviewed B3 1080p30 project required')
    require(pack['id'] == 'matchday' and pack['resources'] == [] and len(pack['overlays']) == 12
            and len(pack['scenes']) == 4, 'Expected local controlled MATCHDAY manifest')
    graph = project['graph']; sources = graph['sources']; scenes = graph['scenes']
    require(len(sources) == 14 and len(scenes) == 5, 'Only default resources plus MATCHDAY permitted')
    require(len({s['id'] for s in sources}) == 14 and len({s['id'] for s in scenes}) == 5,
            'Resource IDs must be unique')
    require(all(source in sources for source in initial_graph['sources'])
            and initial_graph['scenes'][0] in scenes, 'Default project resources must be preserved exactly')
    require(graph['active_scene'] == initial_graph['active_scene'], 'Saved reviewed default scene required')
    bindings = {'sources': {}, 'scenes': {}, 'layers': {}}
    for overlay in pack['overlays']:
        found = [s for s in sources if s['name'] == 'MATCHDAY · '+overlay['name']]
        require(len(found) == 1, 'Unambiguous owned overlay required')
        source = found[0]
        require(set(source) == {'id', 'name', 'spec', 'overlay'}
                and source['spec'] == {'kind': 'overlay', 'color': 0x33e8b5}
                and source['overlay'] == overlay['definition'], 'Saved overlay differs from controlled definition')
        bindings['sources'][overlay['id']] = source['id']
    for scene in pack['scenes']:
        found = [s for s in scenes if s['name'] == 'MATCHDAY · '+scene['name']]
        require(len(found) == 1, 'Unambiguous owned scene required')
        target = found[0]; bindings['scenes'][scene['id']] = target['id']
        require(set(target) == {'id', 'name', 'layers'} and len(target['layers']) == len(scene['layers']),
                'Unexpected MATCHDAY layer count')
        for layer in scene['layers']:
            expected = {'source_id': bindings['sources'][layer['overlay_id']],
                        'layouts': {key: layer[key] for key in ('horizontal', 'vertical')}}
            found = [l for l in target['layers'] if {k: v for k, v in l.items() if k != 'id'} == expected]
            require(len(found) == 1, 'Saved layer differs from exact controlled layout')
            bindings['layers'][layer['id']] = found[0]['id']
    all_layers = [layer['id'] for scene in scenes for layer in scene['layers']]
    require(len(all_layers) == len(set(all_layers)), 'Layer IDs must be unique')
    return bindings


def expected_configuration(pack, deck_template, bindings):
    """Read-only comparison with the explicit manual subset in creator_packs.rs."""
    def animation(identifier):
        value = next(a for a in pack['animations'] if a['id'] == identifier)
        return {'type': 'animate', 'scene_id': bindings['scenes'][value['scene_id']],
                'layer_id': bindings['layers'][value['layer_id']],
                'animation': {k: value[k] for k in ('kind', 'easing', 'duration_ms', 'distance', 'scale_from')}}
    goal = animation('goal-enter')
    goal.update(type='trigger_animated_widget', source_id=bindings['sources']['goal-celebration'])
    goal_actions = [goal, {'type': 'increment_counter', 'name': 'goals', 'amount': 1}]
    actions = [('deck-goal', goal_actions, 10000), ('deck-celebrate', goal_actions, 10000),
               ('deck-community', [{'type': 'widget', 'source_id': bindings['sources']['community-alert'], 'event': 'trigger'}], 3000),
               ('lower-enter', [{'type': 'show_overlay', 'source_id': bindings['sources']['match-lower-third']}, animation('lower-enter')], 0)]
    config = {'schema_version': 1, 'rules': [dict(id=identifier, enabled=True, event_kind='manual.button_pressed',
        priority=5, conditions=[], actions=copy.deepcopy(rule_actions), cooldown_ms=cooldown, debounce_ms=0,
        timeout_ms=10000, busy_policy='reject', failure_policy='stop') for identifier, rule_actions, cooldown in actions],
        'variables': {'goals': {'type': 'int', 'value': 0}}, 'queue_capacity': 16, 'rate_limit': 20,
        'rate_window_ms': 1000, 'max_actions_per_event': 32}
    deck = copy.deepcopy(deck_template); deck['name'] = 'MATCHDAY Live Deck'
    for button in deck['buttons']:
        if button['id'] == 'goal': button['label'] = 'Celebración de gol'
        target = button['target']
        if target['kind'] in ('overlay', 'countdown'): target['source_ref'] = bindings['sources'][target['source_ref']]
        if target['kind'] == 'scene': target['scene_ref'] = bindings['scenes'][target['scene_ref']]
    return config, deck


def temporary_configuration(saved, pack, deck_template, bindings, duration_ms):
    require(set(saved) == {'version', 'project_fingerprint', 'config', 'deck'}
            and type(saved['version']) is int and saved['version'] == 1, 'Reviewed Show Control store v1 required')
    require(re.fullmatch(r'[0-9a-f]{64}', saved['project_fingerprint']) is not None, 'Stored binding fingerprint required')
    config, deck = expected_configuration(pack, deck_template, bindings)
    require(saved['config'] == config and saved['deck'] == deck, 'Stored B3 manual configuration differs from reviewed definitions')
    require(type(duration_ms) is int and duration_ms in (450, 3000), 'Only stock450ms or custom3000ms is supported')
    original = copy.deepcopy(saved)
    temporary = copy.deepcopy(saved['config'])
    goal = next(rule for rule in temporary['rules'] if rule['id'] == 'deck-goal')
    require(goal['actions'][0]['animation']['duration_ms'] == 450, 'Original B3 duration must remain 450 ms')
    goal['actions'][0]['animation']['duration_ms'] = duration_ms
    require(saved == original, 'Saved configuration may not be mutated')
    return temporary, copy.deepcopy(saved['deck'])


def native_job(state, operation):
    return next((job for job in state['overlays']['runtime']['animations']['jobs']
                 if job['operation_id'] == operation), None)


def tone_gain(state, tone):
    inputs = [item for item in state['audio_mixer']['store']['inputs'] if item['id'] == tone]
    require(len(inputs) == 1 and inputs[0]['source'] == {'kind': 'tone'} and inputs[0]['muted'] is False,
            'Owned unmuted tone must remain present')
    require(state['audio_mixer']['monitoring'] == 'off', 'Monitoring must remain disabled')
    return inputs[0]['gain_db']


def pending_evidence(state, job, session, tone, duration_ms):
    records = [record for record in job['records'] if record.get('operation_id')]
    if len(records) != 1: return None
    operation = native_animation_id(records[0]['operation_id'], session)
    native = native_job(state, operation)
    if not native or native['phase'] != 'running' or native['started'] is not True or native['widget_triggered'] is not True:
        return None
    require(native['duration_ms'] == duration_ms, 'Observed native operation must use the explicitly selected duration')
    return {'operation_id': operation, 'native': native, 'job_state': job['state'],
            'gain_db': tone_gain(state, tone), 'revision': state['revision'], 'last_action': state['last_action']}


def ui_gain_edit(evidence):
    return bool(evidence and evidence['gain_db'] == 0 and evidence['job_state'] in ('awaiting_completion', 'needs_reconciliation')
                and re.fullmatch(r'UI · set_audio_gain · revisión [0-9]+', evidence['last_action']))


def classify_result(before, edit, job, state, baseline_counter):
    if not before or not edit:
        return {'status': 'NOT_OBSERVED', 'reason': 'Need pending native operation before edit and real UI gain change while still running'}
    require(before['job_state'] == 'awaiting_completion' and before['gain_db'] == -12, 'Pending baseline at −12 dB required')
    require(before['operation_id'] == edit['operation_id'] and edit['revision'] > before['revision'] and ui_gain_edit(edit),
            'Same native operation and later genuine UI action required')
    codes = [record.get('code') for record in job['records']]
    passed = job['state'] == 'needs_reconciliation' and job['cursor'] == 0 and 'MISSING_MUTATION_RECEIPT' in codes \
        and counter_value(state) == baseline_counter and not any(record['index'] == 1 for record in job['records'])
    return {'status': 'PASS' if passed else 'FAIL', 'counter_before': baseline_counter,
            'counter_after': counter_value(state), 'job': job,
            'automatic_replay_requested_by_harness': False,
            'dispatch_uniqueness': 'NOT_PROVEN_WITHOUT_JOURNAL_AUDIT',
            'click_provenance': 'Root CUA evidence is required separately; no UI origin is sent by this harness.'}
