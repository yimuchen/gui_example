import functools
import logging
import traceback
from typing import Callable, Iterable, List

import tqdm
from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ..utils import _str_
from .gui_session import GUISession


def clear_layout(layout):
    """
    Clearing the container contents of a layout. As this operation is
    potentially expensive, use this method sparingly!
    """
    for i in reversed(range(layout.count())):
        item = layout.itemAt(i)
        if isinstance(item.widget(), QWidget):
            item.widget().deleteLater()
        elif item.layout():
            clear_layout(item.layout())
            item.layout().deleteLater()


class _QContainer(QWidget):
    """
    Large containers which bundles chunks of information at a time. Exposing
    the parent instance with the name "session" for exposing hardware controls.
    """

    def __init__(self, session: GUISession):
        # NOTE: Because GUISession has multiple inheritance it must be setup
        # set this way
        super().__init__()
        self.setParent(session)
        self.session = session  # Reference to main session instance

    @staticmethod
    def gui_action(f: Callable):
        """
        Common decorator for letting GUI action create an error message instead
        of hard crashing. Helps with debugging the information.
        """

        @functools.wraps(f)
        def _wrap(*args, **kwargs):
            try:
                f(*args, **kwargs)
            except Exception as err:
                print(traceback.format_exc())
                logging.getLogger("GUI").error(str(err))

        return _wrap

    def _display_update(self):
        """
        Method to overload to define what should be done when a refresh
        signal is requested by the user. By default do nothing.
        """
        pass

    def log(self, s: str, level: int) -> None:
        logging.getLogger(f"GUI.{self.__class__.__name__}").log(
            level=level, msg=_str_(s)
        )

    def loginfo(self, s: str) -> None:
        self.log(s, logging.INFO)

    def logwarn(self, s: str) -> None:
        self.log(s, logging.WARNING)

    def logerror(self, s: str) -> None:
        self.log(s, logging.ERROR)


class _QLineEditDefault(QLineEdit):
    """Input method elements"""

    def __init__(self, default: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._default = default
        self.setText(self._default)

    def revert_default(self):
        self.setText(self._default)


class _QSpinBoxDefault(QSpinBox):
    """Input method elements"""

    def __init__(self, default: int, min_value=0, max_value=99, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._default = default
        self.setMinimum(min_value)
        self.setMaximum(max_value)
        self.setValue(self._default)

    def revert_default(self):
        self.setValue(self._default)


class _QComboPlaceholder(QComboBox):
    """Adding some pythonic methods to handling combo box methods"""

    def __init__(self, placeholder: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._placeholder = placeholder
        self.setEditable(True)
        self.setEditText("")
        self.lineEdit().setPlaceholderText(self._placeholder)

    def set_texts(self, texts: List[str]) -> None:
        self.clear()
        for t in texts:
            self.addItem(t)

    @property
    def item_texts(self):
        return [self.itemText(i) for i in range(self.count())]

    def on_textchange(self, f: Callable):
        """Short hand"""
        self.lineEdit().textChanged.connect(f)


class _QConfirmationDialog(QDialog):
    """
    Simple OK/Cancel confirmation box. The Ok/Cancel will return a simple
    True/False flag should something go wrong.
    """

    def __init__(self, parent, brief: str, full_message: str):
        super().__init__(parent)

        self.setWindowTitle(brief)
        self._buttonBox = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        self._buttonBox.accepted.connect(self.accept)
        self._buttonBox.rejected.connect(self.reject)
        self._layout = QVBoxLayout()
        self._layout.addWidget(QLabel(_str_(full_message)))
        self._layout.addWidget(self._buttonBox)
        self.setLayout(self._layout)


class _QRunButton(QPushButton):
    """
    Button that handles the locking of other buttons when clicked. See the
    set_lock method in the main session handle
    """

    def __init__(self, session: GUISession, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session

        # Other than the running flag, is the session correctly configured to
        # carry out this action? Default is to always set to be True
        self.session_config_valid = True

    def run_connect(self, f: Callable, threaded=False):
        """
        Additional wrapper the callable action which ensures that the interface
        is properly locked the the run call is created. The threaded flag is
        used to indicate that the callable method will spawn a thread in a
        separate method and thus should not unlock the buttons when the method
        terminates.
        """

        def _wrap(event):
            if self.session.run_lock:
                # Early return if this somehow slipped past run_lock
                self.setDisabled(True)
                return
            # Locking buttons and releasing if not a threaded method
            self.session.lock_buttons(True)
            f()
            if not threaded:
                self.session.lock_buttons(False)
                self.session.refresh()

        self.clicked.connect(_wrap)

    def _display_update(self):
        if self.session.run_lock:
            self.setDisabled(True)
        else:
            self.setEnabled(self.session_config_valid)

    def _set_lock(self):
        self._display_update()


class _QInteruptButton(QPushButton):
    """
    Buttons to only be enabled after global run_lock is set to true. The logic
    for how this should be handled by the implementing class and not here.
    """

    def __init__(self, session: GUISession, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.session = session

    def _display_update(self):
        self.setEnabled(self.session.run_lock)

    def _set_lock(self):
        self._display_update()


class _QLabelHandler(logging.Handler):
    """
    Have a label show the latest logging output.
    """

    def __init__(self, label: QLabel, level: int = logging.NOTSET):
        super().__init__(level=level)
        self.label = label

    def emit(self, record: logging.LogRecord):
        self.label.setText(record.msg)


class _QThreadableTQDM(QObject):
    # A threadable loop object. As we cannot have multiple inheritance with
    # QObjects, we will create a tqdm object to use as styling of the object.
    # We will still use the underlying TQDM object to help with styling and
    # avoiding excessive signal generation
    progress = pyqtSignal(int)
    clear = pyqtSignal()

    class _WrapTQDM(tqdm.tqdm):
        # Thin wrapper to automatically handle the emit progress signal
        def __init__(self, obj, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._parent = obj

        def update(self, n=1):
            super().update(n)
            self._parent.progress.emit(self.n)

    def __init__(self, session: GUISession, x: Iterable, *args, **kwargs):
        super().__init__()
        self.tqdm_bar = _QThreadableTQDM._WrapTQDM(self, x, *args, **kwargs)
        # Add reference to main session object to capture the various signals
        self.session = session

    def __iter__(self):
        # main iteration class that is used to generate the signals. Mimicking
        # the structure and signal of the tqdm.std.__iter__ method:
        # See here:
        # https://github.com/tqdm/tqdm/blob/master/tqdm/std.py#L1160
        try:
            for x in self.tqdm_bar:
                if self.session.interupt_flag:
                    raise InterruptedError("Interupted by user!!")
                yield x
        finally:
            self.clear.emit()


class _QPBarContainer(QWidget):
    def __init__(self):
        super().__init__()

        # Display elements
        self.desc_label = QLabel("")
        self.pbar_widget = QProgressBar()
        self.tqdm_instance: _QThreadableTQDM._WrapTQDM = None

    def __init_layout__(self):
        # No explicit layout would be added here. As the display elements would
        # most likely set want to be the set by the solution
        self.pbar_label.setStyleSheet("font-family: monospace")

    def prepare(self, instance: _QThreadableTQDM._WrapTQDM):
        # Wrapping the instances
        self.in_use = True
        self.tqdm_instance = instance

        # Setting the display elements to be visible
        self.desc_label.show()
        self.pbar_widget.show()
        self.desc_label.setText(self.tqdm_instance.tqdm_bar.desc)
        self.pbar_widget.setMaximum(self.tqdm_instance.tqdm_bar.total)

        # Connecting the signals to display element update
        self.tqdm_instance.progress.connect(self.progress)
        self.tqdm_instance.clear.connect(self.clear)

    @_QContainer.gui_action
    def progress(self, x):
        tqdm_bar = self.tqdm_instance.tqdm_bar
        desc = tqdm_bar.desc

        self.pbar_widget.setValue(tqdm_bar.n)

        # Getting the display text using the tqdm format bar
        format_dict = {k: v for k, v in tqdm_bar.format_dict.items()}
        format_dict["ncols"] = 0  # Length 0 / stat only progress bar
        pbar_str = tqdm_bar.format_meter(**format_dict)
        pbar_str = pbar_str[len(desc) + 1 :]

        self.pbar_widget.setFormat(pbar_str)
        self.pbar_widget.setStyleSheet("font-family: monospace")

    def clear(self):
        self.in_use = False
        self.desc_label.hide()
        self.pbar_widget.hide()
