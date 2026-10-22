"""Isolate Qt finalization failures without opening capture devices or modems.

Each case gets its own interpreter; exit status includes finalization. This is
an explicit diagnostic, not a retry or a replacement for the ordinary CI gate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys


MINIMAL = '''
import gc, sys
from PySide6.QtCore import QCoreApplication, QObject, Signal
from PySide6.QtTest import QSignalSpy
app = QCoreApplication([])
class Sender(QObject):
    value = Signal(bool)
sender = Sender()
gc.collect()
before = (sys.getrefcount(True), sys.getrefcount(False))
for _ in range(100):
    spy = QSignalSpy(sender.value)
    sender.value.emit(True)
    sender.value.emit(False)
    assert spy.at(0) == [True]
    assert spy.at(1) == [False]
    del spy
gc.collect()
after = (sys.getrefcount(True), sys.getrefcount(False))
print(dict(before=before, after=after, delta=tuple(b-a for a,b in zip(before,after))), flush=True)
'''

PYTEST = '''
import gc, json, sys
import pytest
class References:
    def pytest_runtest_logreport(self, report):
        if report.when == 'teardown':
            print(json.dumps(dict(test=report.nodeid, true_refs=sys.getrefcount(True), false_refs=sys.getrefcount(False))), flush=True)
before = (sys.getrefcount(True), sys.getrefcount(False))
result = pytest.main(sys.argv[1:], plugins=[References()])
gc.collect()
print(dict(pytest_result=int(result), before=before, after=(sys.getrefcount(True),sys.getrefcount(False))), flush=True)
raise SystemExit(result)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    options = ['--import-mode=importlib', '-q', '-s', '-W', 'ignore::DeprecationWarning']
    no_reads = MINIMAL.replace('    assert spy.at(0) == [True]', '    pass').replace(
        '    assert spy.at(1) == [False]', '    pass')
    no_spy = no_reads.replace('    spy = QSignalSpy(sender.value)', '    pass').replace(
        '    del spy', '    pass')
    empty_spy = no_reads.replace('    sender.value.emit(True)', '    pass').replace(
        '    sender.value.emit(False)', '    pass')
    ordinary_slot = MINIMAL.replace('    spy = QSignalSpy(sender.value)',
        '    values = []; sender.value.connect(values.append)').replace(
        'spy.at(0)', 'values[:1]').replace('spy.at(1)', 'values[1:]').replace(
        '    del spy', '    sender.value.disconnect(values.append); del values')
    integer_spy = MINIMAL.replace('Signal(bool)', 'Signal(int)')
    string_spy = MINIMAL.replace('Signal(bool)', 'Signal(str)').replace(
        '.emit(True)', ".emit('a')").replace('.emit(False)', ".emit('b')").replace(
        '== [True]', "== ['a']").replace('== [False]', "== ['b']")
    cases = [(name, code, []) for name, code in (
        ('minimal_signal_spy', MINIMAL), ('emit_without_spy', no_spy),
        ('spy_without_read', no_reads), ('spy_without_emit', empty_spy),
        ('ordinary_slot', ordinary_slot), ('integer_spy', integer_spy),
        ('string_spy', string_spy))]
    cases.extend((path.name, PYTEST, [str(path), *options])
                 for path in sorted(args.tests.glob('test_*.py')))
    cases.extend((f'full_suite_{i}', PYTEST, [str(args.tests), *options]) for i in range(2))
    reports = []
    for name, code, arguments in cases:
        try:
            result = subprocess.run([sys.executable, '-c', code, *arguments],
                                    capture_output=True, text=True, timeout=120)
            report = dict(case=name, returncode=result.returncode,
                          stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired as exc:
            report = dict(case=name, returncode=None, timeout=True,
                          stdout=str(exc.stdout), stderr=str(exc.stderr))
        reports.append(report)
        args.output.write_text(json.dumps(reports, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report), flush=True)
    return int(any(report['returncode'] != 0 for report in reports))


if __name__ == '__main__':
    raise SystemExit(main())
