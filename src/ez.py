import click
import constants as C
import os
import platform
import subprocess

import compute_commands
import env_commands
import workspace_commands

from ez_state import Ez, EzConfig, EzRuntime
from formatting import printf_err
from os import system
from rich import print
from rich.console import Console 
from rich.prompt import Prompt

def check_installed(command: str, 
                    install_help: str = None,
                    force = False) -> bool:
    """Check if command is installed and display install_help if not"""
    if force:
        console = Console()
        console.print(f"Checking: {command}", style="green")
        
    returncode = system(f"which {command} > /dev/null")
    if returncode == 0:
        return True
    else:
        printf_err(f"Required dependency {command} not installed")
        if install_help is not None:
            print(f"TO INSTALL: {install_help}")
        return False

def check_dependencies(force: bool=False) -> bool:
    """Install dependencies required for ez to run"""
    # NOTE: these are Windows instructions
    if platform.system() == "Linux":
        if not check_installed("az", 
            ("The Azure Command Line Interface (CLI) must be installed to "
            "communicate with Azure.\n"
            "curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash"), force):
            return False
        if not check_installed("docker", 
            ("Cannot find docker, which is needed to run the ez containers\n"
            "https://hub.docker.com/editions/community/docker-ce-desktop-windows/"
            ), force):
            return False
    elif platform.system() == "Darwin":
        if not check_installed("az", 
            ("The Azure Command Line Interface (CLI) must be installed to "
            "communicate with Azure.\n"
            "brew update && brew install azure-cli"), force):
            return False
        if not check_installed("docker", 
            ("Cannot find docker, which is needed to run the ez containers\n"
            "https://docs.docker.com/desktop/mac/apple-silicon/"
            ), force):
            return False
    if not check_installed("gh",
        ("Cannot find the GitHub CLI (gh), which is needed for interactions "
         "with GitHub. https://cli.github.com/manual/installation"), force):
        return False
    result = subprocess.run(["gh", "auth", "status"], capture_output=True)
    output = result.stderr.decode("utf-8")
    if not "Logged in to github.com as" in output:
        printf_err("Not logged into Github.com using the GitHub CLI. "
                   "Log in using: gh auth login")
        return False
    return True

@click.group()
@click.option("--debug", is_flag=True, help="Output diagnostic information")
@click.option("--insiders", is_flag=True, help="Run using VS Code Insiders")
@click.option("--dependencies", is_flag=True, help="Force check dependencies")
@click.option("--disable-jit", is_flag=True, help="Disable JIT activation")
@click.pass_context
def ez(ctx, debug, insiders, dependencies, disable_jit):
    """Command-line interface for creating and using portable Python
    environments. To get started run ez init!"""

    runtime = EzRuntime()
    runtime.debug = debug
    runtime.insiders = insiders 
    runtime.disable_jit = disable_jit

    ctx.obj = runtime

    if not check_dependencies(dependencies):
        exit(1)

@click.command()
@click.pass_obj
def init(runtime: EzRuntime) -> None:
    """First (and one-time) initialization of ez

    One-time initialization of ez. If it finds an existing ~/.ez.json file
    it will prompt you to overwrite it.
    """

    ez = workspace_commands.create_workspace()
    ez_config_path = os.path.expanduser(C.WORKSPACE_CONFIG)
    if os.path.isfile(ez_config_path):
        choice = Prompt.ask(f"{ez_config_path} exists. Overwrite?", 
                            default="n")
        if choice == "y":
            os.remove(ez_config_path)
        else:
            exit(0)
    runtime.add(ez)
    runtime.save()

    print(f"""
ez is now configured, configuration file written to {ez_config_path}.

Try running creating a compute and running a GitHub
repo using it. Here's an example:

1. Create a new ez compute VM. This will create a VM and install GPU
   drivers and Docker.

ez compute create -c ezgpu1 -s Standard_NC6_Promo

2. Run a GitHub repo of notebooks using the VM you just created. This may
   take a while to generate the Docker container image needed to run that 
   repo (pytorch containers are >25GB in size!)

ez env run -g https://github.com/jflam/pytorch-tutorials 

3. Shutdown the VM once you're done using it. This will help you save money
   by not leaving the VM running when you're not using it.

ez compute stop

For support, please create a GitHub issue at https://github.com/jflam/ez
""")

ez.add_command(init)

# workspace sub-commands

@ez.group()
def workspace():
    """Manage workspaces"""
    # Tell the user what they need to get started
    # They need to have the Azure CLI installed
    # They need to have Docker installed
    # 1. Login to azure (or check to see if they are logged in)
    # 2. List subscriptions and ask which one you'd like to set as default
    # Ideally it will print out a list of the Azure subs that you have
    # and let you pick from it. Do this experiment with rich 

    pass

workspace.add_command(workspace_commands.create)
workspace.add_command(workspace_commands.delete)
workspace.add_command(workspace_commands.select)
workspace.add_command(workspace_commands.ls)
workspace.add_command(workspace_commands.info)

# compute sub-commands

@ez.group()
def compute():
    """Manage compute nodes"""
    pass

compute.add_command(compute_commands.create)
compute.add_command(compute_commands.delete)
compute.add_command(compute_commands.ls)
compute.add_command(compute_commands.start)
compute.add_command(compute_commands.stop)
compute.add_command(compute_commands.select)
compute.add_command(compute_commands.info)
compute.add_command(compute_commands.ssh)
compute.add_command(compute_commands.update_system)
compute.add_command(compute_commands.enable_acr)
compute.add_command(compute_commands.enable_github)
compute.add_command(compute_commands.mount)
compute.add_command(compute_commands.get_host_key)

# environment sub-commands

@ez.group()
def env():
    """Manage environments"""
    pass

# env.add_command(env_commands.ls)
env.add_command(env_commands.cp)
env.add_command(env_commands.ssh)
# env.add_command(env_commands.stop)
env.add_command(env_commands.up)
env.add_command(env_commands.go)