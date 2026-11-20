"""Summaries from retained H21 observations; no assumed GPU attribution/leak proof."""
import statistics
import json


def summarize_gameplay(path, expected_pid):
    """Describe fixture observations; draw counters are not decoded pixel proof."""
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    ready = [r for r in rows if r.get('event') == 'ready']
    if len(ready) != 1 or ready[0].get('pid') != expected_pid:
        raise ValueError('Game telemetry producer identity mismatch')
    samples = [r for r in rows if r.get('event') == 'game']
    if len(samples) < 2:
        raise ValueError('Insufficient gameplay observations')
    draw_rates = []
    for left, right in zip(samples, samples[1:]):
        elapsed = right['seconds']-left['seconds']
        frames = right['draw_frames']-left['draw_frames']
        if elapsed <= 0 or frames < 0:
            raise ValueError('Non-monotonic game telemetry')
        draw_rates.append(frames/elapsed)
    return {'scope':'Game-owned sampled counters and reported FPS; separate from SCK delivery and encoded output cadence. Not decoded gameplay pixel proof.',
            'observed_seconds':samples[-1]['seconds']-samples[0]['seconds'],
            'samples':len(samples), 'draw_frames_delta':samples[-1]['draw_frames']-samples[0]['draw_frames'],
            'observed_draw_rate_fps':distribution(draw_rates),
            'reported_game_fps':distribution([r['fps'] for r in samples]),
            'sampled_distinct_ball_positions':len({tuple(r['ball']) for r in samples}),
            'final_round_counter':samples[-1]['rounds'],
            'final_collision_counter':samples[-1]['collisions']}


def distribution(values):
    return {'samples':len(values), 'min':min(values), 'median':statistics.median(values), 'max':max(values)} if values else None


def summarize(run):
    observations = [r['response']['memory'] for r in run.get('memory',[]) if r['response'].get('ok')]
    cpu = []
    for a,b in zip(observations,observations[1:]):
        seconds = (b['monotonic_ns']-a['monotonic_ns'])/1e9
        if seconds>0 and a['cpu']['available'] and b['cpu']['available']:
            first = a['cpu']['user_seconds']+a['cpu']['system_seconds']
            last = b['cpu']['user_seconds']+b['cpu']['system_seconds']
            cpu.append(100*(last-first)/seconds)
    result = {'cpu_percent_one_core_100':distribution(cpu),
              'rss_mib':distribution([v['vm']['resident_bytes']/1048576 for v in observations if v['vm']['available']]),
              'footprint_mib':distribution([v['vm']['physical_footprint_bytes']/1048576 for v in observations if v['vm']['available']]),
              'limits':['Process metrics cover Motive only, not the game/fixture/receiver.',
                        'Short/long memory observations do not prove absence of leaks.',
                        'GPU utilization includes all applications and has driver-defined interval semantics.']}
    if len(observations)>=2:
        result['footprint_first_to_last_mib']=(observations[-1]['vm']['physical_footprint_bytes']-observations[0]['vm']['physical_footprint_bytes'])/1048576
    values = []
    for row in run.get('gpu',[]):
        for device in row['response'].get('devices',[]):
            v=device['statistics'].get('Device Utilization %')
            if isinstance(v,(int,float)): values.append(v)
    result['device_wide_gpu_percent'] = distribution(values)
    initial=run.get('initial_state',{});last=run.get('last_state',{})
    if initial and last:
        result['compositor_counter_delta']={k:last['stats'][k]-initial['stats'][k] for k in
            ('rendered_frames','lagged_frames','video_skipped_frames','preview_busy_drops')}
        result['output_last_active']={k:v['stats'] for k,v in last['outputs'].items()}
        camera=run.get('camera_source_id')
        if camera:
            first=next(s for s in initial['sources'] if s['id']==camera)
            final=next(s for s in last['sources'] if s['id']==camera)
            result['camera']={'width':final['width'],'height':final['height'],
                              'observed_frames_delta':final['frames']-first['frames'],
                              'interval_s':run.get('last_elapsed_s'),
                              'scope':'Native frame arrival count; not physical A/V alignment or decoded camera freshness.'}
    return result
