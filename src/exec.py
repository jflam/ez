# Helper functions for executing commands local and remote

import pandas as pd
import shlex, subprocess

from ez_state import Ez
from fabric import Connection
from formatting import format_output_string, printf, printf_err
from io import StringIO
from invoke.exceptions import UnexpectedExit
from rich.console import Console
from rich.progress import (Progress, SpinnerColumn, TextColumn, 
    TimeElapsedColumn)
from typing import Tuple

# TODO: a single method that handles local and remote as well to unify code.

def exec_cmd_local(
    cmd: str,
    cwd: str=None,
) -> Tuple[int, str, str]:
    """Execute cmd locally in cwd"""
    result = subprocess.run(cmd, cwd=cwd, check=False, shell=True, 
        capture_output=True)
    return (result.returncode, 
        result.stdout.decode("utf8").strip(), 
        result.stderr.decode("utf8").strip())

def exec_cmd_remote(
    cmd: str,
    uri: str,
    private_key_path: str,
    cwd: str=None,
    warn: bool=True,
) -> Tuple[int, str, str]:
    """Execute cmd on uri using private_key_path in cwd"""
    connect_args={
        "key_filename": [private_key_path]
    }
    with Connection(uri, connect_kwargs=connect_args) as c:
        if cwd is not None:
            c.cd(cwd)
        return exec_cmd_remote_line(c, cmd, warn)

def exec_cmd_remote_line(
    connection: Connection,
    cmd: str,
    warn: bool=True,
) -> Tuple[int, str, str]:
    """Execute cmd on connection optionally suppressing exceptions with a
    warning"""
    result = connection.run(cmd, warn=warn)
    return (result.exited, 
        result.stdout.strip(), 
        result.stderr.strip())

def internal_exec_cmd(
    command: str,
    target_compute: str=".",
    cwd: str=None):
    """Internal method to execute a command on the target"""
    pass

# TODO: an internal method that we test separately from one that wraps
# functionality like logging, formatting, progress, status etc.

def exec_command(ez: Ez, 
                 command: str, 
                 log: bool=False, 
                 terminate_on_error: bool=True,
                 description: str="", 
                 input_file_path: str=None,
                 cwd: str=None,
                 stdin: str=None) -> Tuple[int, str]:
    """Shell execute command and optionally log output incrementally."""
    description = format_output_string(description)
    completed = format_output_string(f"completed: {description}")
    command_array = shlex.split(command)
    is_ssh = command_array[0].lower() == "ssh"
    if input_file_path is not None:
        with open(input_file_path, "rt") as f:
            stdin = f.read()

    if ez.debug:
        printf(f"executing: {command}")
        if stdin is not None:
            printf(f"stdin: \n{stdin}")

    p = subprocess.Popen(command_array, 
                         cwd=cwd,
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         stdin=subprocess.PIPE)
    if stdin is not None:
        p.stdin.write(stdin.encode("utf-8"))
        p.stdin.close()

    console = Console(height=20, force_interactive=True)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        t = progress.add_task(description)

        output = []
        while True:
            retcode = p.poll()
            line = p.stdout.readline().decode("utf-8").rstrip()
            output.append(line)
            if log:
                progress.console.log(line)
            if retcode is not None:
                break

        progress.console.bell()
        description = format_output_string(f"completed: {description}")
        progress.update(t, description=description)
        if terminate_on_error:
            if is_ssh and p.returncode == 255:
                stderr = (p.stderr.read().decode('utf-8'))
                printf_err(f"({p.returncode}) {stderr}")
                printf(f"... during execution of: {command}")
                exit(p.returncode)
            elif not is_ssh and p.returncode != 0:
                stderr = (p.stderr.read().decode('utf-8'))
                printf_err(f"({p.returncode}) {stderr}")
                printf(f"... during execution of: {command}")
                exit(p.returncode)
        
        progress.update(t, description=completed)
        return (p.returncode, "\n".join(output))
    
# Use fabric to exec script
def exec_script_using_ssh(ez: Ez, 
                          compute_name :str, 
                          script_path: str=None, 
                          script_text: str=None,
                          description: str="",
                          line_by_line: bool=False,
                          hide_output: bool=False,
                          connect_timeout: int=120,
                          reboot: bool=False) -> Tuple[int, str]:
    """Execute script_name on compute_name using the fabric ssh library.
    script_path must be an absolute path."""

    if script_path is None and script_text is None:
        printf_err("Must pass either script_path or script_text")
        exit(1)
    elif script_path is not None and script_text is not None:
        printf_err("Cannot pass both script_path and script_text")
        exit(1)
    
    description=format_output_string(description)
    host_uri = f"{compute_name}.{ez.region}.cloudapp.azure.com"
    c = Connection(host_uri, 
        user=ez.user_name, 
        connect_timeout=connect_timeout,
        connect_kwargs={
            "key_filename": [ez.private_key_path],
        })

    if script_path is not None:
        with open(script_path, "rt") as f:
            lines = f.readlines()
    else:
        lines = script_text.split("\n")

    console = Console(height=20, force_interactive=True)
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        t0 = progress.add_task(description)
        completed = format_output_string(f"completed: {description}")
        task_name = ""
        if line_by_line:
            # Process line by line and 
            i = 0
            t = 0
            while i < len(lines):
                current_line = lines[i].strip()
                if current_line == "":
                    i += 1
                    continue
                if current_line.startswith("##"):
                    if task_name != "":
                        progress.update(t, 
                            description=format_output_string(
                                f"completed: {task_name}"), 
                            completed=100)
                    i += 1
                    task_name = current_line[2:].strip()
                    t = progress.add_task(format_output_string(
                        f"running: {task_name}"))
                    continue
                if current_line.startswith("#"):
                    i += 1
                    continue
                if current_line.endswith("\\"):
                    while i < len(lines):
                        i += 1
                        block_line = lines[i].strip()
                        current_line += f"\n  {block_line}"
                        if not block_line.endswith("\\"):
                            break
                console.log(
                        format_output_string(f"{task_name}: {current_line}"))
                c.run(current_line, warn=True)
                i += 1

            progress.update(t, description=format_output_string(
                f"completed: {task_name}"), completed=100)
            progress.console.bell()

            # Complete - reboot if needed
            try:
                if reboot:
                    c.run("sudo reboot", warn=True)
            except Exception:
                pass
            progress.update(t0, description=completed)
            return (0, "")
        else:
            # Run everything as a single block
            single_block = "\n".join(lines)
            if hide_output:
                result = c.run(single_block, hide='stdout', warn=True)
            else:
                result = c.run(single_block, warn=True)
            progress.update(t0, description=completed)
            return (result.exited, result.stdout)

def exec_command_return_dataframe(cmd):
    # TODO: delegate to exec_command
    result = subprocess.run(shlex.split(cmd), capture_output=True)
    stdout = result.stdout.decode("utf-8")
    stream = StringIO(stdout)
    return pd.read_csv(stream, sep="\t", header=None)
