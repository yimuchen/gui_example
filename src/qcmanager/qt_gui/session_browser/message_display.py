import logging
from typing import Iterable

from PyQt5.QtWidgets import QGridLayout, QGroupBox, QLabel

from ..gui_session import GUISession
from ..qt_helper import _QContainer, _QLabelHandler, _QPBarContainer, _QThreadableTQDM


class SessionMessageDisplay(_QContainer):
    def __init__(self, session: GUISession):
        super().__init__(session)

        # Creating elements set by outer objects
        self.monitor_box = QGroupBox("Program monitor")
        self.gui_message = QLabel("")
        self.program_message = QLabel("")

        # Should not need more than 6 progress bars in total???
        self.progress_bars = [_QPBarContainer() for _ in range(6)]

        self.__init_layout__()
        self.__init_logger__()

    def __init_layout__(self):
        self._layout = QGridLayout()
        self._layout.addWidget(QLabel("Program messages"), 0, 0)
        self._layout.addWidget(self.program_message, 0, 1)

        self._layout.addWidget(QLabel("GUI messages"), 1, 0)
        self._layout.addWidget(self.program_message, 1, 1)

        for index, p in enumerate(self.progress_bars):
            self._layout.addWidget(p.desc_label, 2 + index, 0)
            self._layout.addWidget(p.pbar_widget, 2 + index, 1)
            p.clear()

        self._layout.setColumnStretch(0, 1)
        self._layout.setColumnStretch(1, 20)
        self.setLayout(self._layout)

    def __init_logger__(self):
        # GUI Loggers
        gui_logger = logging.getLogger("GUI")
        gui_logger.addHandler(_QLabelHandler(self.gui_message))

        # Procedure logging methods
        prog_logger = logging.getLogger("QACProcedure")
        prog_logger.addHandler(_QLabelHandler(self.program_message))

    def iterate(self, x: Iterable, *args, **kwargs):
        """
        The progress bar containers cannot be initialized here due to import
        restrictions. The main constructer must make sure that a new session
        """

        def _get_first_unused():
            for index, p in enumerate(self.progress_bars):
                if not p.in_use:
                    return p

        p_item = _get_first_unused()
        # p_item.moveToThread(thread_tqdm.thread())
        p_item.prepare(_QThreadableTQDM(self.session, x, *args, **kwargs))
        return p_item.tqdm_instance
