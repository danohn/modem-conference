"""Windows 95 inspired palette for the native modem conferencing client."""
from importlib.resources import files

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

FACE = '#c0c0c0'
NAVY = '#000080'
SHADOW = '#808080'
HIGHLIGHT = '#ffffff'

STYLE = '''
QMainWindow, QDialog, QWidget#stationBody { background: #c0c0c0; color: black; }
QWidget { font-family: Tahoma, Arial, sans-serif; font-size: 12px; }
QLabel#stationCaption { background: #000080; color: white; font-weight: bold; padding: 5px 7px; }
QMenuBar { background: #c0c0c0; padding: 2px; border-bottom: 1px solid #808080; }
QMenuBar::item { padding: 4px 9px; background: transparent; }
QMenuBar::item:selected, QMenu::item:selected { background: #000080; color: white; }
QMenu { background: #c0c0c0; border: 2px outset #eeeeee; padding: 3px; }
QMenu::item { padding: 5px 24px 5px 14px; }
QPushButton, QToolButton { background: #c0c0c0; color: black; border-top: 2px solid white; border-left: 2px solid white; border-bottom: 2px solid #404040; border-right: 2px solid #404040; padding: 4px 9px; min-height: 18px; border-radius: 0px; }
QPushButton:pressed, QToolButton:pressed, QPushButton:checked { border-top: 2px solid #404040; border-left: 2px solid #404040; border-bottom: 2px solid white; border-right: 2px solid white; padding-top: 5px; padding-left: 10px; padding-bottom: 3px; padding-right: 8px; }
QPushButton:disabled, QToolButton:disabled { color: #808080; }
QPushButton:focus, QToolButton:focus { outline: 1px dotted black; }
QLineEdit, QComboBox, QPlainTextEdit { background: white; color: black; border-top: 2px solid #808080; border-left: 2px solid #808080; border-bottom: 2px solid white; border-right: 2px solid white; padding: 4px; selection-background-color: #000080; selection-color: white; border-radius: 0px; }
QLineEdit:disabled, QComboBox:disabled { background: #d4d0c8; color: #606060; }
QComboBox::drop-down { width: 20px; background: #c0c0c0; border-left: 1px solid #808080; }
QComboBox::down-arrow { image: url(__COMBO_ARROW__); width: 7px; height: 4px; }
QGroupBox { border: 1px solid #808080; margin-top: 9px; padding: 10px 8px 8px; }
QGroupBox::title { subcontrol-origin: margin; left: 9px; padding: 0px 4px; background: #c0c0c0; }
QFrame#videoPanel { border-top: 1px solid white; border-left: 1px solid white; border-bottom: 1px solid #808080; border-right: 1px solid #808080; }
QLabel#tabCaption { border-top: 2px solid white; border-left: 2px solid white; border-right: 1px solid #808080; font-weight: bold; padding: 5px 12px; }
QLabel#filename { background: white; border-top: 2px solid #808080; border-left: 2px solid #808080; border-bottom: 2px solid white; border-right: 2px solid white; padding: 5px; }
QLabel#smallText { font-size: 11px; color: #333333; }
QProgressBar { border-top: 2px solid #808080; border-left: 2px solid #808080; border-bottom: 2px solid white; border-right: 2px solid white; background: white; min-height: 12px; max-height: 14px; text-align: center; }
QProgressBar::chunk { background: #000080; width: 9px; margin: 1px; }
QLabel#statusCell { border-top: 1px solid #808080; border-left: 1px solid #808080; border-bottom: 1px solid white; border-right: 1px solid white; padding: 4px 6px; font-size: 11px; }
QCheckBox { spacing: 5px; }
QToolTip { background: #ffffe1; color: black; border: 1px solid black; padding: 3px; }
'''


def apply_theme(app: QApplication) -> None:
    """Use rectangular desktop controls and retain Qt's OS scaling support."""
    app.setStyle(QStyleFactory.create('Fusion'))
    palette = QPalette()
    for role, color in ((QPalette.ColorRole.Window, FACE),
                        (QPalette.ColorRole.Button, FACE),
                        (QPalette.ColorRole.Base, '#ffffff'),
                        (QPalette.ColorRole.Text, '#000000'),
                        (QPalette.ColorRole.WindowText, '#000000'),
                        (QPalette.ColorRole.ButtonText, '#000000'),
                        (QPalette.ColorRole.Highlight, NAVY),
                        (QPalette.ColorRole.HighlightedText, '#ffffff'),
                        (QPalette.ColorRole.Light, '#ffffff'),
                        (QPalette.ColorRole.Dark, SHADOW)):
        palette.setColor(role, QColor(color))
    app.setPalette(palette)
    app.setFont(QFont('Tahoma', 10))
    app.setStyleSheet(STYLE.replace('__COMBO_ARROW__',
                                   str(files('modem_conference').joinpath('assets/combo-arrow.svg')).replace('\\', '/')))
