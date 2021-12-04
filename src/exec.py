# Helper functions for executing commands local and remote

import pandas as pd
import subprocess

from fabric import Connection
from formatting import format_output_string, printf_err
from io import StringIO
from rich.progress import (Progress, SpinnerColumn, TextColumn, 
    TimeElapsedColumn)
from typing import Optional, Union

class ExecResult:
    exit_code: int 
    stdout: str
    stderr: str

    def __init__(self, exit_code: int, stdout: str, stderr: str):
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr

def exec_file(
    path: str,
    uri: str=None,
    private_key_path: str=None,
    description: str=None,
    cwd: str=None,
) -> list[ExecResult]:
    with open(path, "rt") as f:
        lines = f.readlines()

    if description is None:
        raise ValueError("Must pass description to exec_file")

    results = []
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
    ) as progress:
        overall_task = progress.add_task(format_output_string(description))

        current_task = None
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line == "":
                i += 1
                continue
            elif line.startswith("##"):
                if current_task is not None:
                    progress.update(task_id, description=format_output_string(
                        f"Completed: {current_task}", indent=2), 
                        completed=100)
                current_task = line[2:].strip()
                task_id = progress.add_task(format_output_string(
                    f"Running: {current_task}", indent=2))
                i += 1
                continue
            elif line.startswith("#"):
                i += 1
                continue
            elif line.endswith("\\"):
                while i < len(lines):
                    i += 1
                    block_line = lines[i].strip()
                    line += f"\n  {block_line}"
                    if not block_line.endswith("\\"):
                        break
            result = exec_cmd(line, uri, private_key_path, cwd=cwd)
            results.append(result)
            i += 1

        # Mark current sub-task complete (if any)
        if current_task is not None:
            progress.update(task_id, description=format_output_string(
                f"Completed: {current_task}", indent=2), completed=100)

        # Mark overall task complete
        progress.update(overall_task, description=format_output_string(
            f"Completed: {description}"), completed=100)
        progress.console.bell()
        return results

def exec_cmd(
    cmd: Union[str, list[str]],
    uri: str=None,
    private_key_path: str=None,
    description: str=None,
    cwd: str=None,
) -> Union[ExecResult, list[ExecResult]]:

    # Description sets up a master context for showing things
    if description is not None:
        description = format_output_string(description)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            TimeElapsedColumn(),
        ) as progress:
            task = progress.add_task(description)

            if uri is None:
                result = exec_cmd_local(cmd, cwd)
            else:
                result = exec_cmd_remote(cmd, uri, private_key_path, cwd)

            if description is not None:
                progress.console.bell()
                description = format_output_string(
                    f"Completed: {description}")
                progress.update(task, description=description, completed=100)

            return result
    else:
        if uri is None:
            return exec_cmd_local(cmd, cwd)
        else:
            return exec_cmd_remote(cmd, uri, private_key_path, cwd)

def exec_cmd_local(
    cmd: Union[str, list[str]],
    cwd: str=None,
) -> Union[ExecResult, list[ExecResult]]: 
    """Execute cmd or list[cmd] locally in cwd"""
    if type(cmd) is str:
        result = exec_single_cmd_local(cmd, cwd)
    elif type(cmd) is list:
        result = []
        for c in cmd:
            r = exec_single_cmd_local(c, cwd)
            result.append(r)
    else:
        raise TypeError("cmd must be str or list[str]")
    return result

def exec_single_cmd_local(
    cmd: str,
    cwd: str=None,
) -> ExecResult:
    """Execute cmd locally in cwd"""
    result = subprocess.run(cmd, cwd=cwd, check=False, shell=True, 
        capture_output=True)
    return ExecResult(result.returncode, 
        result.stdout.decode("utf8").strip(), 
        result.stderr.decode("utf8").strip())

def exec_cmd_remote(
    cmd: Union[str, list[str]],
    uri: str,
    private_key_path: str,
    cwd: str=None,
) -> Union[ExecResult, list[ExecResult]]:
    """Execute cmd on uri using private_key_path in cwd"""
    connect_args={
        "key_filename": [private_key_path]
    }
    with Connection(uri, connect_kwargs=connect_args) as connection:
        if cwd is not None:
            connection.cd(cwd)
        if type(cmd) is str:
            result = exec_single_cmd_remote(connection, cmd)
        elif type(cmd) is list:
            result = []
            for c in cmd:
                r = exec_single_cmd_remote(connection, c)
                result.append(r)
        else:
            raise TypeError("cmd must be str or list[str]")

        return result

def exec_single_cmd_remote(
    connection: Connection,
    cmd: str,
) -> ExecResult:
    """Execute cmd on connection, ensuring that result no exceptions are
thrown"""
    result = connection.run(cmd, warn=True, hide="both")
    return ExecResult(result.exited, 
        result.stdout.strip(), 
        result.stderr.strip())

def exit_on_error(result: ExecResult):
    if result.exit_code != 0:
        printf_err(result.stderr)
        exit(result.exit_code)

def exec_cmd_return_dataframe(cmd) -> Optional[pd.DataFrame]:
    """Execute the command and return a dataframe or None"""
    result = exec_cmd(cmd)
    exit_on_error(result)
    if result.stdout == "":
        return None
    stream = StringIO(result.stdout)
    return pd.read_csv(stream, sep="\t", header=None)
