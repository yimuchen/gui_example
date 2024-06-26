"""
procedure_base.py

Decorator methods to ensure that all process function can exit with the
appropate results container flags regardless of execution status. This will
also contain common methods in routines that are commonly used by QA/QC
procedures, such as pulling data with a fixed number of events, and methods for
creating the command line processes.
"""

import io
import logging
import os
import shutil
import time
import traceback
from dataclasses import dataclass
from typing import Callable, Iterable

from ..hw.tileboard_zmq import TBController
from ..utils import _str_, timestamps, to_yaml
from ..yaml_format import DataEntry, ProcedureResult, StatusCode


@dataclass(kw_only=True)
class ProcedureBase(object):
    """
    Base object to unify the procedure runtine. Notice that to ensure that the
    functions are stateless up-to the instances that are managed by the Session
    object, all procedures will be recreated on the call instance.

    The typical call method for higher level function should be something like:

    return =  MyProcedure(
                kwarg1=abc,
                kwarg2=abc,
                kwarg3=123,
            ).run_with(
                session.hw_interface1,
                session.hw_interface2
            )

    Developers should not over load the main `run_with` method, just the
    various `run` methods to ensure a common routine is processed everytime.
    The keyword arguments are stored according to the kwargs names as fields.
    To be used. Additional parsing of the keyword arugments to the process can
    be specified in the `parse_arg` method. Default is no parsing and simply
    returning as is.

    On the successful general of a procedure object. An interal "result" is
    automatically generated, from the various arguments. The `self.result`
    field should be modified by the defined run method, and will be return to
    be store in the main session object.
    """

    store_base: str = ""

    def __post_init__(self):
        """
        Additional items to create after all kwargs have been complete
        """
        self.result: ProcedureResult = ProcedureResult(
            name=self.name,
            _start_time=timestamps(),
            _end_time=timestamps(),
            input={k: v for k, v in self.__dict__.items() if k != "store_base"},
            status_code=(0, ""),
        )

    def run_with(self, *args, **kwargs) -> ProcedureResult:
        """
        Wrapper for the main run method to be wrapped to handle and store
        exception results. Ideally, we should keep the error messages concise
        and only do full dumps for unknown errors.
        """
        # TODO: Complete the various exception methods
        try:
            self.run(*args, **kwargs)
        except KeyboardInterrupt:
            self.logwarn("User interupt signal received")
            self.result.status_code = (StatusCode.SIG_INTERUPT, "")
        except Exception as err:
            # Generic error. Supposedly it should not reach this stage. Passing
            # the full error message to logger information.
            print(traceback.format_exc())
            self.result.status_code = (StatusCode.UNKNOWN_ERROR, str(err))
            self.logerror(
                f"Unknown error! [{str(err)}]",
                extra={"error_trace": traceback.format_exc()},
            )
        finally:
            self.result._end_time = timestamps()
            self.loginfo(f"{self.name} completed")
            return self.result

    @property
    def procedure_name(self):
        return self.__class__.__name__

    @property
    def name(self):
        return self.procedure_name

    def make_store_path(self, path: str) -> str:
        return os.path.join(self.store_base, path)

    def full_path(self, data: DataEntry):
        return self.make_store_path(data.path)

    def open_text_file(self, path, desc, **kwargs) -> io.TextIOWrapper:
        """Opening a file to be written, Automatically adding this to be entry"""
        full_path = self.make_store_path(path)
        self.result.data_files.append(DataEntry(path=full_path, desc=desc, **kwargs))
        return open(full_path, "w")

    """
    Additional methods used for logging message (avoid using raw prints!!)
    """

    def log(self, msg: str, level: int, *args, **kwargs) -> None:
        logging.getLogger(f"QACProcedure.{self.name}").log(
            level=level, msg=_str_(msg), *args, **kwargs
        )

    def loginfo(self, msg: str, *args, **kwargs) -> None:
        self.log(msg, logging.INFO, *args, **kwargs)

    def logwarn(self, msg: str, *args, **kwargs) -> None:
        self.log(msg, logging.WARNING, *args, **kwargs)

    def logerror(self, msg: str, *args, **kwargs) -> None:
        self.log(msg, logging.ERROR, *args, **kwargs)

    """
    Common methods for interacting with hardware interfaces.
    """

    def acquire_hgcroc(
        self, tbc: TBController, n_events: int, save_path: str, desc="", **kwargs
    ) -> DataEntry:
        """
        Acquiring n_events data, and store the entry to the the a DataEntry to
        the current results. Additional kwargs will be passed to the
        construction of the DataEntry
        """

        # Cast to string required?
        tbc.daq_socket.yaml_config["daq"]["NEvents"] = str(n_events)

        # Always attempt to store to the /tmp directory first
        tbc.pull_socket.yaml_config["global"]["outputDirectory"] = "/tmp"
        tbc.pull_socket.yaml_config["global"]["run_type"] = "data_acquire"

        tbc.pull_socket.configure()
        tbc.daq_socket.configure()

        tbc.pull_socket.start()
        tbc.daq_socket.start()
        while not tbc.daq_socket.is_complete():
            tbc.sleep(0.01)
        tbc.daq_socket.stop()
        tbc.pull_socket.stop()

        shutil.move(
            os.path.join("/tmp", "data_aquire0.raw"), self.make_store_path(save_path)
        )
        time.sleep(0.1)  # Sleep 100ms for output to be complete
        self.result.data_files.append(DataEntry(path=save_path, **kwargs))
        return self.result.last_data

    def save_full_config(self, tbc: TBController, save_path: str, desc="", **kwargs):
        """
        Flushing the current configuration to a file
        """
        ret = tbc.i2c_socket._config.copy()
        for key in ret.keys():
            if key.find("roc_s") == 0:
                tbc.i2c_socket._config[key] = {"sc": ret[key]}
        initial_full_config = {}
        for key, val in tbc.i2c_socket._config.keys():
            if key.find("roc_s") == 0:
                initial_full_config[key] = val
        initial_full_config["daq"] = tbc.daq_socket._config["daq"]
        initial_full_config["client"] = tbc.pull_socket._config["client"]

        with self.open_text_file(path=save_path, desc=desc, **kwargs) as fout:
            to_yaml(initial_full_config, fout)


# Helper method to shorten method names
HWIterable = Callable[[Iterable], Iterable]
