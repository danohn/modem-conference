from types import SimpleNamespace

from modem_conference import dependencies


def responses(monkeypatch, muxers):
    monkeypatch.setattr(dependencies, 'binary', lambda name: name)
    def run(arguments, **kwargs):
        if '-encoders' in arguments:
            output = ' V h263 encoder\n A g723_1 encoder\n V mpeg4 encoder\n A aac encoder\n V png encoder\n'
        elif '-decoders' in arguments:
            output = ' V h263 decoder\n A g723_1 decoder\n'
        elif '-muxers' in arguments:
            output = muxers
        else:
            output = 'ffprobe version test'
        return SimpleNamespace(returncode=0, stdout=output, stderr='')
    monkeypatch.setattr(dependencies.subprocess, 'run', run)


def test_missing_avi_muxer_is_reported_before_camera_transmission(monkeypatch):
    responses(monkeypatch, ' E matroska Matroska\n')
    status = dependencies.check()
    assert not status.ready
    assert 'AVI muxer' in status.detail


def test_supported_codecs_and_avi_muxer_make_dependency_check_ready(monkeypatch):
    responses(monkeypatch, ' E avi AVI (Audio Video Interleaved)\n')
    assert dependencies.check().ready
