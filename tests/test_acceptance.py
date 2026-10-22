from modem_conference.acceptance import (accepted_bearer, CaptureMetrics,
                                        transmission_clock, capture_duration_accepted,
                                        station_plan, duration_outcome)
from types import SimpleNamespace
import pytest


def carrier_report():
    return {'source':'AT+MRR', 'validated':True, 'phase':'connect', 'modulation':'V32B',
            'tx_bps':14400, 'rx_bps':14400, 'connect_bps':14400,
            'raw_mcr':'+MCR: V32B', 'raw_mrr':'+MRR: 14400,14400', 'raw_connect':'CONNECT 14400'}


def test_actual_inband_or_corroborated_carrier_reports_have_explicit_sources():
    assert accepted_bearer(14400, None) == {'source':'V.80 in-band', 'tx_bps':14400, 'rx_bps':14400}
    assert accepted_bearer(None, carrier_report()) == carrier_report()


def test_configured_rates_or_inconsistent_carrier_reports_cannot_pass():
    assert accepted_bearer(None, {'configured_rate':14400}) is None
    assert accepted_bearer(None, None) is None
    assert accepted_bearer(28800, carrier_report()) is None
    for changes in ({'validated':False}, {'source':'configured'}, {'rx_bps':0},
                    {'raw_connect':'CONNECT 9600'}, {'raw_mrr':'+MRR: 14400,0'},
                    {'raw_mcr':'+MCR: V34'}, {'raw_connect':''}):
        assert accepted_bearer(None, {**carrier_report(), **changes}) is None


def test_capture_metrics_count_without_retaining_frames_or_unbounded_statuses():
    metrics = CaptureMetrics()
    metrics.preview(object())
    metrics.outgoing({'lcn':1, 'payload':b'x'*24}, 10.)
    metrics.outgoing({'lcn':2, 'payload':b'picture'}, 10.)
    for index in range(1000):
        metrics.status(f'video overload detail {index}')
    metrics.ended_at = 10.03
    report = metrics.summary()
    assert report['preview_frames'] == 1
    assert report['outgoing_frames'] == {1:1,2:1}
    assert report['outgoing_bytes'] == {1:24,2:7}
    assert report['overload_status_count'] == 1000
    assert len(report['status_history']) == 100
    assert len(report['status_counts']) <= 33
    assert report['audio_output_ratio'] >= 1.


def test_hardware_clock_waits_for_all_live_sources_after_permission_delay():
    metrics = {'1':CaptureMetrics(), '2':CaptureMetrics()}
    assert transmission_clock(['file','file'], metrics, 10.) == 10.
    assert transmission_clock(['file','camera'], metrics, 10.) is None
    metrics['2'].started_at = 70.
    assert transmission_clock(['file','camera'], metrics, 10.) == 70.
    assert transmission_clock(['camera','camera'], metrics, 10.) is None
    metrics['1'].started_at = 90.
    assert transmission_clock(['camera','camera'], metrics, 10.) == 90.


def test_permission_delay_cannot_turn_short_capture_into_a_full_duration_pass():
    short = {'capture_duration_seconds':540., 'audio_output_ratio':.99,
             'outgoing_frames':{1:17820,2:900}}
    assert not capture_duration_accepted(short, 600.)
    full = {'capture_duration_seconds':600., 'audio_output_ratio':.99,
            'outgoing_frames':{1:19800,2:1000}}
    assert capture_duration_accepted(full, 600.)
    assert not capture_duration_accepted({**full, 'outgoing_frames':{1:100,2:1000}}, 600.)


def test_single_station_has_only_explicit_local_ownership_and_role():
    args = SimpleNamespace(mode='station', port='COM7', role='answer', number=None,
                           source='camera', bundle=None, exercise_video_overload=False)
    assert station_plan(args) == (['camera'], ['COM7'], [None])
    args.role = 'dial'
    with pytest.raises(ValueError, match='--number'):
        station_plan(args)
    args.number = '5550123'
    assert station_plan(args)[1] == ['COM7']
    args.port = None
    with pytest.raises(ValueError, match='--port'):
        station_plan(args)


def test_simulated_single_station_waits_for_media_and_rejects_early_remote_hangup():
    metrics = {'1':CaptureMetrics()}
    assert transmission_clock(['camera'], metrics, 10.) is None
    assert duration_outcome(None, 600., True, 5.) == 'early_disconnect'
    metrics['1'].started_at = 45.  # Selected/authorized after call connection.
    start = transmission_clock(['camera'], metrics, 10.)
    assert start == 45.
    assert duration_outcome(644.-start, 600., True, 5.) == 'early_disconnect'
    assert duration_outcome(645.-start, 600., False, 5.) == 'continue'
    assert duration_outcome(645.-start, 600., True, 5.) == 'complete'
    assert duration_outcome(650.-start, 600., False, 5.) == 'complete'
