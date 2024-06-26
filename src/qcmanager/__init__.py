import os
import traceback
from typing import Any, Dict, Type

from . import plotting, procedures, session, utils, yaml_format

__version__ = "0.0.3"


def run_single_procedure(
    session: session.Session,
    procedure_class: Type,
    procedure_arguments: Dict[str, Any],
) -> None:
    """
    Running the procedure defined by the class with the given user inputs.
    Hardware interfaces are detected automatically.
    - The procedure_arguments should match the arguments used to define
      procedure constructor.
    - One additional item that we will add here is to set the store_path of the
      procedure base on the procedure name and the current timestamp.
    """
    StatusCode = yaml_format.StatusCode

    # Setting the the storage directory and creating the initial results object
    store_base = session.modify_save_path(
        procedure_class.__name__ + "_" + utils.timestampf()
    )
    os.mkdir(store_base)
    procedure_instance = procedure_class(**procedure_arguments, store_base=store_base)
    session.results.append(procedure_instance.result)

    # Running additional parsing before processing
    try:
        for name, param in procedures._parsing.get_procedure_args(
            procedure_class
        ).items():
            procedures._parsing.run_argument_parser(
                param,
                getattr(procedure_instance, name),
                session=session,
                exception=True,
            )
        result = procedure_instance.run_with(
            *session.detect_procedure_interface(procedure_class)
        )
        # For all the the results. The file path should be reset to be relative
        # to the session.yaml file
        for f in result.data_files:
            f.path = os.path.relpath(f.path, os.path.dirname(session.log_file))
    # Most exceptions should be handled in the _procedure_base method.
    except Exception:
        # Unlabeled exceptions. In usual operation, it should never reach this
        # stage, should be fixed in code. Here we will save the full track
        # stace for debugging later on.
        session.results[-1].status_code = (
            StatusCode.UNKNOWN_ERROR,
            traceback.format_exc(),
        )
    finally:
        session.save_session()
