'''Environment Management Tools.'''
# %%  Imports
from typing import Union, List, Tuple, Dict
import re
import json
import subprocess
from pathlib import Path
from collections.abc import Iterable

import pandas as pd

# %% Initialize logging
import logging  # pylint: disable=wrong-import-position wrong-import-order
logging.basicConfig(level=logging.INFO,
                    format='%(levelname)-8s %(message)s')
logger = logging.getLogger(__name__)
#logger.setLevel(logging.DEBUG)
logger.setLevel(logging.INFO)


# %% Type Definitions
# CmdType is an operating system command either as a single string or as a
# list of command parts.
CmdType = Union[str, List[str]]

# EnvRef is a reference to a Conda environment either by it's name or by the
# path to the environment.
EnvRef = Union[str, Path]

# FullEnvRef is # FullEnvRef is a complete reference to a Conda environment
# as a Tuple containing the name and the path to the environment.
FullEnvRef = Tuple[str, Path]

# FileNameOption is either a string file name or a boolean
FileNameOption = Union[str, bool]


# %% Exception Definitions
class ProjectException(Exception):
    '''Base Exception for projects module.'''

class AnacondaException(ProjectException):
    '''Errors related to `conda` calls.'''

class AbortedCmdException(ProjectException):
    '''Errors resulting from a time-out for a system call.'''


# %% Utility Functions
def true_iterable(variable)-> bool:
    '''Indicate if the variable is a non-string type iterable.
    Arguments:
        variable {Iterable[Any]} -- The variable to test.
    Returns:
        True if variable is a non-string iterable.
    '''
    return not isinstance(variable, str) and isinstance(variable, Iterable)


# %% Console command processing
def error_check(output: subprocess.CompletedProcess, error_type: Exception,
                error_msg: str):
    '''Check for errors in subprocess output.

    if a `CalledProcessError` error occurred raise the error, with the
    error_msg text.
    Args:
        output (subprocess.CompletedProcess): subprocess output to be tested.
        error_type (Exception): The type of exception to raise if an error
            occurs.
        error_msg (str): The Error message to include if required.
    Raises:
        error_type: If subprocess generated an error.
    '''
    try:
        output.check_returncode()
    except subprocess.CalledProcessError as err:
        msg = '\n'.join([error_msg, output.stderr.decode()])
        raise error_type(msg) from err
    except subprocess.TimeoutExpired as err:
        msg = '\n'.join(['Command timed out!', output.stderr.decode()])
        raise AbortedCmdException(msg) from err


def console_command(cmd_str: CmdType,
                    error_type: Exception = subprocess.CalledProcessError,
                    error_msg: str = 'A console_command error occurred!',
                    abort_after: int = None)->str:
    '''Run a system console command.

    Run the command. Check for errors and raise the appropriate error if
    necessary.
    If no error, return the output from the result of running the console
    command.

    Args:
        cmd_str (CmdType): The operating system command to execute. Either a
            single string containing the entire command, or a list of strings,
            with each part of the command as a separate list item.
        error_type (Exception, Optional): The type of exception to raise if an
            error occurs.  Default is subprocess.CalledProcessError.
        error_msg (str, Optional): The Error message to include if required.
            Default is 'A console_command error occurred!'.
        abort_after (int, Optional): Abort the command call after the given
            number of seconds.  If None, do not time-out the command call.
            Default is None.

    Returns:
        str: The log output from running the console command.
    '''
    output = subprocess.run(cmd_str, shell=True, capture_output=True,
                            check=False, timeout=abort_after)
    # check for errors
    error_check(output, error_type, error_msg)
    cmd_log = output.stdout.decode()
    return cmd_log

# %% Conda Environment Functions
def save_env_specs(env_ref: EnvRef, save_folder: Path,
                   spec_file: FileNameOption = True,
                   yml_file: FileNameOption = True,
                   history_json: FileNameOption = True):
    '''Store *spec*, *.yml* and *.json* history files for the environment.

    Default spec file names will have the form: {env_name}_spec.txt'
    Default .yml file names will have the form: {env_name}.yml'
    Default .yml file names will have the form: {env_name}.yml'

    Args:
        env_ref (EnvRef): A reference to the Conda environment either by it's
            name or by the path to the environment.
        save_folder (str): Path to the folder where the information is to be
            saved.
        spec_file (FileNameOption): If a file name or True, save a conda
            environment spec file.  If True, use the default file name pattern.
            Default is True.
        yml_file (FileNameOption): If a file name or True, export a conda
            environment *.yml* file. If True, use the default file name pattern.
            Default is True.
        history_json (FileNameOption): If a file name or True, create a *.json*
            file containing the packages explicitly installed to create the
            environment.  If True, use the default file name pattern.
            Default is True.
    '''
    # Allow for string path references
    env_path = Path(env_ref)
    if env_path.is_dir():
        # env_ref is a path reference.
        # Note: this can fail if env_name matches a folder name in Path.cwd().
        env_name = env_path.name
        env_cmd_ref = ['-p', env_path]
    else:
        # env_ref is an environment name
        env_name = env_ref
        env_cmd_ref = ['--name', env_name]

    if spec_file:
        # Generate a conda environment spec file
        if not isinstance(spec_file, str):
            # Use the default file pattern
            spec_file = save_folder / f'{env_name}_spec.txt'
        save_spec_cmd = ['conda', 'list', '--explicit']
        save_spec_cmd += env_cmd_ref
        save_spec_cmd += ['>', str(spec_file)]
        console_command(save_spec_cmd, AnacondaException,
                        f'Error saving {env_name} environment spec file.')

    if yml_file:
        # Generate a conda environment .yml file
        if not isinstance(yml_file, str):
            # Use the default file pattern
            yml_file = save_folder / f'{env_name}.yml'
        save_yml_cmd = ['conda', 'env', 'export']
        save_yml_cmd += env_cmd_ref
        save_yml_cmd += ['--file', str(yml_file)]
        console_command(save_yml_cmd, AnacondaException,
                        f'Error saving {env_name}.yml file.')

    if history_json:
        # Generate a conda environment history .json file
        if not isinstance(history_json, str):
            # Use the default file pattern
            history_json = save_folder / f'{env_name}.json'
        save_history_cmd = ['conda', 'env', 'export',
                            '--from-history', '--json']
        save_history_cmd += env_cmd_ref
        save_history_cmd += ['>', str(history_json)]
        console_command(save_history_cmd, AnacondaException,
                        f'Error saving {env_name}.json file.')


def get_conda_info(info_storage_path: Path = None)->dict:
    '''Get information about the current Conda environment.

    If a file path is provided, save the json info to that file.

    Args:
        conda_info_file (Path, optional): The file path to save the json data
            in. If None, do not save the data.  Defaults to None.

    Returns:
        dict: Conda environment parameters as nested dictionaries.
    '''
    conda_info_cmd = r'conda info --envs --json'
    conda_info = console_command(conda_info_cmd, AnacondaException,
                                 'Unable to get Anaconda info')

    # If supplied, save the data to a .json file
    if info_storage_path:
        if info_storage_path.is_dir():
            conda_info_file = info_storage_path / 'conda_info.json'
        else:
            conda_info_file = Path(info_storage_path)
        conda_info_file.write_text(conda_info, encoding="utf-8")

    # Convert the json data to a dictionary
    conda_info_dict = json.loads(conda_info)
    return conda_info_dict


def list_environments()->List[FullEnvRef]:
    '''Get list of current Anaconda environments.

    Returns:
        List[FullEnvRef]: A list containing the references to all current
            Anaconda environments
    '''
    env_pattern = re.compile(
        r'(?P<name>'  # Start of *name* group.
        r'[a-z0-9_]'  # Name begins with letter, number or _.
        r'.+?'        # All text until 2 or more spaces are encountered
        r')'          # End of *name* group.
        r'[ *]{2,}'   # 2 or more spaces or * in a row.
        r'(?P<path>'  # Start of *path* group.
        r'[A-Z]:'     # Drive letter, followed by a :.
        r'[^\r\n]*'   # Remaining text before the end of the line.
        r')',         # End of *path* group.
        flags=re.IGNORECASE)

    conda_envs = r'conda env list'
    env_list = console_command(conda_envs, AnacondaException,
                               'Unable to get Anaconda environments')
    env_info = [(name, Path(path))
                for name, path in env_pattern.findall(env_list)]
    return env_info


def log_all_envs(env_storage_path: Path):
    '''Store environment info for each environment.

    Args:
        env_storage_path (Path): Path to the folder where the information is to
            be saved.
    '''
    env_list = list_environments()
    if not env_storage_path.exists():
        env_storage_path.mkdir()
    for env_def in env_list:
        env_name, env_path = env_def
        logger.info('Storing environment for %s', env_name)
        try:
            save_env_specs(env_path, env_storage_path)
        except AnacondaException:
            logger.warning('Unable to store environment for %s', env_name)


def build_env_table(env_storage_path: Path = None)->pd.DataFrame:
    '''Save a spreadsheet table with environments and their paths.

    Args:
        env_storage_path (Path, optional): The path where the table spreadsheet
            will be stored. If a directory, the default file name:
                'Conda Environments.xlsx'
            is used. If None, do not save the table in a file. Defaults to None.

    Returns:
        pd.DataFrame: A table with environments and their paths.
    '''
    env_list = list_environments()
    env_data = pd.DataFrame(env_list)
    env_data.columns = ['Environment', 'Environment Path']
    if env_storage_path:
        if env_storage_path.is_dir():
            env_table_file = env_storage_path / 'Conda Environments.xlsx'
        env_data.to_excel(env_table_file)
    return env_data


def activate_environment(env_name: str)->str:
    '''Generate command string to activate a Conda environment.

    This string is intended to be a prefix to activate a conda environment.
    for use with calls to `console_command`.
    e.g.:
        cmd_str = activate_environment('Standard')
        cmd_str += 'conda env export --from-history'
        output = console_command(cmd_str)

    Args:
        env_name (str): The name of the Conda environment.

    Returns:
        str: The Conda activation string prefix.
    '''
    cmd_str = ''.join([
        r'cmd /c C:\ProgramData\Anaconda3\Scripts\activate.bat ',
        r'C:\ProgramData\Anaconda3',
        r'&&',
        f'conda activate {env_name}',
        r'&&'
        ])
    return cmd_str


def create_environment(new_env: str, python_version: str = 3.10)->Dict[str,str]:
    '''Create a ne Conda environment.

    Args:
        new_env (str): The name for the new Conda environment.
        python_version (str, optional): The version of python to used for the
            environment. Defaults to 3.10.

    Returns:
        Dict[str,str]: Output as a dictionary of dictionaries from the
            environment creation logs.
    '''
    logger.info('Creating environment for %s', new_env)

    env_create_cmds = f'conda create -y --json --quiet --name {new_env} '
    env_create_cmds += f'python={python_version}'
    err_msg = ' '.join([f'Unable to create new environment "{new_env}"',
                        f'with python={python_version}!'])
    install_output = console_command(env_create_cmds, AnacondaException,
                                     err_msg)
    install_output_dict = json.loads(install_output)
    return install_output_dict


def remove_environment(env_ref: EnvRef)->Dict[str,str]:
    '''Remove an Anaconda environment

    Args:
        env_ref (EnvRef): A reference to the Conda environment either by it's
            name or by the path to the environment.

    Returns:
        Dict[str,str]: Log output, as a dictionary of dictionaries, generated
            when removing the environment.
    '''
    # Allow for string path references
    env_path = Path(env_ref)
    if env_path.is_dir():
        # env_ref is a path reference.
        # Note: this can fail if env_name matches a folder name in Path.cwd().
        del_env = env_path.name
        env_cmd_ref = f'-p {str(env_path)}'
    else:
        # env_ref is an environment name
        del_env = env_ref
        env_cmd_ref = f'--name {del_env}'

    delete_cmd = activate_environment(del_env)
    delete_cmd += 'conda deactivate&&'
    delete_cmd += 'conda remove -y --json --quiet --all '
    delete_cmd += env_cmd_ref
    err_msg = f'Unable to delete environment {del_env}'

    uninstall_output = console_command(delete_cmd, AnacondaException, err_msg)

    install_output_dict = json.loads(uninstall_output)
    return install_output_dict
