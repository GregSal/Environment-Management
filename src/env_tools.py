'''Environment Management Tools.

 Tools for building and managing Conda project environments
 '''

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

# FileOption is a reference to a file as a string or path If True, this means
# that a default name is to be used.
FileOption = Union[str, Path, bool]

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

class MissingEnvironment(ProjectException):
    '''The supplied environment name or path is not an Anaconda environment.'''


# %% Utility Functions
def true_iterable(variable)-> bool:
    '''Indicate if the variable is a non-string type iterable.
    Arguments:
        variable {Iterable[Any]} -- The variable to test.
    Returns:
        True if variable is a non-string iterable.
    '''
    return not isinstance(variable, str) and isinstance(variable, Iterable)


def build_file_string(file_name: FileOption, folder: Path = None,
                      default_name: str = 'file.txt')->str:
    '''Generates a quoted full file path for use with subprocess commands.

    If file_name is a Path, convert it to a quoted string.
    If file_name is a string and folder is supplied, build a full path as:
        `folder / file_name` and convert it to a quoted string.
    If file_name is a string and folder is NOT supplied, just add quotes to
        file_name.
    If file_name is True, use default_name as the file_name and either build a
        full path or just add quotes depending of whether folder was supplied.
    If file_name is False or an empty string, return an empty string.

    Double quotes (") are used to quote the string.

    Args:
        file_name (FileOption): Either the full path to a file, the name of a
            file, or a boolean.
        folder (Path): The folder that is used with file_name to create a full
            path.
        default_name (str): A default file name to use if file_name == True.

    Returns:
        str: A quoted full path to a file, or an empty string if file_name is
            False.
    '''
    # Return empty string is file_name is False
    if not file_name:
        return ''

    if isinstance(file_name, Path):
        final_name = str(file_name)
    elif isinstance(file_name, str):
        if folder:
            file_path = folder / file_name
            final_name = str(file_path)
        else:
            final_name = file_name
    elif folder:
        file_path = folder / default_name
        final_name = str(file_path)
    return f'"{final_name}"'



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


def set_env_ref(env_ref: EnvRef)->str:
    '''Create a string environment reference for use in Conda commands.

    The environment command segment has one of two forms:
        - If env_ref is the name of an environment:
            - *'--name <Environment Name>'*.
        - If env_ref is the path to an environment:
            - *'-p <Path To Environment>'*.

    Args:
        env_ref (EnvRef): A reference to the Conda environment either by it's
            name or by the path to the environment.

    Raises:
        MissingEnvironment: env_ref does not correspond with a current Anaconda
            environment.

    Returns:
        Tuple[str, str]: A length-two tuple. The first value is the environment
            name. The second is a Conda command segment referencing the
            desired environment.
    '''
    # Build list of current environment names and paths
    env_list = list_environments()
    env_names = {env[0] for env in env_list}
    env_paths = {str(env[1]) for env in env_list}

    # Check for environment name
    if env_ref in env_names:
        # env_ref is an environment name
        env_name = env_ref
        env_cmd_ref = f'--name {env_ref}'
    # Check for environment path
    elif str(env_ref) in env_paths:
        # env_ref is a path reference.
        # The environment name is the name of the env folder.
        env_name = Path(env_ref).name
        env_cmd_ref = f'-p {str(env_ref)}'
    else:
        raise MissingEnvironment(f'Environment {env_ref} does not exist')
    return (env_name, env_cmd_ref)


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

    env_name, env_cmd_ref = set_env_ref(env_ref)
    default_name = f'{env_name}_spec.txt'
    full_spec_file = build_file_string(spec_file, save_folder, default_name)
    if full_spec_file:
        # Generate a conda environment spec file
        save_spec_cmd  = f'conda list --explicit {env_cmd_ref} '
        save_spec_cmd += f'> {full_spec_file}'
        console_command(save_spec_cmd, AnacondaException,
                        f'Error saving {env_name} environment spec file.')

    default_name = f'{env_name}.yml'
    full_yml_file = build_file_string(yml_file, save_folder, default_name)
    if full_yml_file:
        # Generate a conda environment .yml file
        save_yml_cmd  = f'conda env export {env_cmd_ref} '
        save_yml_cmd += f'--file {full_yml_file}'
        console_command(save_yml_cmd, AnacondaException,
                        f'Error saving {env_name}.yml file.')

    default_name = f'{env_name}.json'
    full_history_json_file = build_file_string(history_json, save_folder,
                                               default_name)
    if history_json:
        # Generate a conda environment history .json file
        save_history_cmd  = r'conda env export --from-history --json '
        save_history_cmd += f'{env_cmd_ref} > {full_history_json_file}'
        console_command(save_history_cmd, AnacondaException,
                        f'Error saving {env_name}.json file.')


def get_conda_info(env_ref: EnvRef = None, info_storage_path: Path = None)->dict:
    '''Get information about the current Conda environment.

    If a file path is provided, save the json info to that file.

    Args:
        env_ref (EnvRef): A reference to the Conda environment either by it's
            name or by the path to the environment. If None, get info for the
            base environment.  Defaults to None.
        info_storage_path (str): Path to the folder or file where the
            information is to be saved. If info_storage_path is a folder, the
            json info will be saved in a file named:
            'conda_info_<env_name>.json'.  If None, do not save the data.
            Defaults to None.

    Returns:
        dict: Conda environment parameters as nested dictionaries.
    '''
    if env_ref:
        env_name  = set_env_ref(env_ref)[0]
        conda_info_cmd = activate_environment(env_name)
    else:
        conda_info_cmd = ''
        env_name = 'base'

    conda_info_cmd += r'conda info --envs --json'
    msg = f'Unable to get Anaconda info for ({env_name})'
    conda_info = console_command(conda_info_cmd, AnacondaException, msg)

    # If supplied, save the data to a .json file
    if info_storage_path:
        if info_storage_path.is_dir():
            conda_info_file = info_storage_path / f'conda_info_{env_name}.json'
        else:
            conda_info_file = Path(info_storage_path)
        conda_info_file.write_text(conda_info, encoding='utf-8')

    # Convert the json data to a dictionary
    conda_info_dict = json.loads(conda_info)
    return conda_info_dict


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
    env_name, env_cmd_ref = set_env_ref(env_ref)

    delete_cmd = activate_environment(env_name)
    delete_cmd += 'conda deactivate&&'
    delete_cmd += 'conda remove -y --json --quiet --all '
    delete_cmd += env_cmd_ref
    err_msg = f'Unable to delete environment {env_name}'

    uninstall_output = console_command(delete_cmd, AnacondaException, err_msg)

    install_output_dict = json.loads(uninstall_output)
    return install_output_dict


def install_packages(env_ref: EnvRef, package_list: List[str])->Dict[str,str]:
    '''Install Conda packages in an Anaconda environment.

    Args:
        env_ref (EnvRef): A reference to the Conda environment either by it's
            name or by the path to the environment.
        package_list (List[str]): A list of package names (and optionally
            version restrictions) to install in the Conda environment.  The
            packages must be available from one of the standard Anaconda
            channels.
    Returns:
        Dict[str,str]: Log output, as a dictionary of dictionaries, generated
            when installing the packages.
    '''
    env_name, env_cmd_ref = set_env_ref(env_ref)

    packages = ' '.join(package_list)

    install_cmd = 'conda install -y --json  --quiet '
    install_cmd += env_cmd_ref
    install_cmd += ' '
    install_cmd += packages

    err_msg = f'Unable to install requested packages in "{env_name}"!'

    install_output = console_command(install_cmd, AnacondaException, err_msg)

    install_output_dict = json.loads(install_output)
    return install_output_dict


def pip_install_packages(env_ref: EnvRef, pip_package_list: List[str])->Dict[str,str]:
    '''Use pip to install packages in an Anaconda environment

    This is intended to be used for installing packages that that cannot be
    found in one of the Anaconda channels.

    Args:
        env_ref (EnvRef): A reference to the Conda environment either by it's
            name or by the path to the environment.
        package_list (List[str]): A list of pip "requirement specifiers"
            (typically package names) to install in the Conda environment.  See
            [Requirement Specifiers](https://pip.pypa.io/en/stable/reference/requirement-specifiers/)
            for more details.
    Returns:
        Dict[str,str]: Log output, as a dictionary of dictionaries, generated
            when installing the packages.
    '''
    env_name = set_env_ref(env_ref)[0]
    activate_cmd = activate_environment(env_name)

    install_logs = []
    for pkg_req in pip_package_list:
        install_cmd = activate_cmd + f'pip install {pkg_req} --quiet --report -'
        err_msg = f'Unable to install {pkg_req} in "{env_name}"!'
        pip_output = console_command(install_cmd, AnacondaException, err_msg)
        install_log_dict = json.loads(pip_output)
        install_logs.append(install_log_dict)

    return install_logs
