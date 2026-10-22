from modem_conference.__main__ import station_label


def test_pair_and_new_station_labels_never_share_preferences_or_logs():
    first = station_label([], '2')
    second = station_label([first])
    assert first == '2'
    assert second == '1'
    third = station_label([first,second])
    assert third == '3'
    assert station_label([first], '2') == '1'
    assert station_label([first,second,third], 'Desk') == 'Desk'
