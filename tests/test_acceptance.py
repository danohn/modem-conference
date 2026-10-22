from modem_conference.acceptance import accepted_bearer, CaptureMetrics


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
