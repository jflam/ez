import click
import constants as C
import json
import os
import pandas as pd
import pathlib
import subprocess

import compute_commands
import env_commands
import workspace_commands

from azutil import exec_command
from io import StringIO
from os import path, system
from rich import print
from rich.console import Console 
from rich.prompt import IntPrompt, Prompt

# Ez object defines application-wide state 

class Ez(object):
    # Options
    debug: str
    trace: str
    insiders: bool
    disable_jit: bool

    # Workspace
    workspace_name: str
    resource_group: str
    registry_name: str
    subscription: str
    region: str
    private_key_path: str
    user_name: str

    # Remotes
    active_remote_compute: str 
    active_remote_compute_type: str 
    active_remote_env: str

    # Runtime state
    logged_in: bool
    jit_activated: bool

    def __init__(self, debug=False, trace=False, insiders=False, 
                 disable_jit=False):
        self.debug = debug 
        self.trace = trace
        self.insiders = insiders
        self.logged_in = False
        self.jit_activated = False
        self.disable_jit = disable_jit
        if disable_jit:
            self.jit_activated = True
        self.load()

    def load(self):
        """Load configuration settings from ~/.ez.json"""
        config_path = os.path.expanduser(C.WORKSPACE_CONFIG)

        if path.exists(config_path):
            with open(config_path, "r") as f:
                ez_config = json.load(f)
            self.workspace_name = ez_config["workspace_name"]
            self.resource_group = ez_config["resource_group"]
            self.registry_name = ez_config["registry_name"]
            self.subscription = ez_config["subscription"]
            self.region = ez_config["region"]
            self.private_key_path = ez_config["private_key_path"]
            self.user_name = ez_config["user_name"]
            self.active_remote_compute = ez_config["active_compute"]
            self.active_remote_compute_type = ez_config["active_compute_type"]
            self.active_remote_env = ez_config["active_env"]
        else:
            self.workspace_name = None
            self.resource_group = None 
            self.registry_name = None
            self.subscription = None
            self.region = None
            self.private_key_path = None
            self.user_name = None
            self.active_remote_compute = None
            self.active_remote_compute_type = None
            self.active_remote_env = None

    def save(self):
        """Save configuration settings to ~/.ez.json"""
        config_path = os.path.expanduser(C.WORKSPACE_CONFIG)
        ez_config = {
            "workspace_name": self.workspace_name,
            "resource_group": self.resource_group,
            "registry_name": self.registry_name,
            "subscription": self.subscription,
            "region": self.region,
            "private_key_path": self.private_key_path,
            "user_name": self.user_name,
            "active_compute": self.active_remote_compute,
            "active_compute_type": self.active_remote_compute_type,
            "active_env": self.active_remote_env 
        }
        with open(config_path, "w") as f:
            json.dump(ez_config, f, indent=4)

    def get_active_compute_name(self, compute_name) -> str:
        """Get the active compute name or exit. Passing None for compute_name
        returns the active remote compute, if it is set."""
        if compute_name == None:
            if self.active_remote_compute == "":
                print("No active remote compute, must specify --compute-name")
                exit(1)
            else:
                return self.active_remote_compute
        else:
            return compute_name

    def get_compute_size(self, compute_name) -> str:
        """Return the compute size of compute_name"""
        # Special return value for localhost
        if compute_name == '.':
            return '.'

        if self.active_remote_compute_type == "k8s":
            # TODO: handle case where compute_type is AKS
            # For now, it always returns a GPU-enabled SKU
            return "Standard_NC6_Promo"
        elif self.active_remote_compute_type == "vm":
            self.debug_print(f"GET compute size for {compute_name}...")
            get_compute_size_cmd = (
                f"az vm show --name {compute_name} "
                f"--resource-group {self.resource_group} "
                f"--query hardwareProfile.vmSize -o tsv"
            )
            _, compute_size = exec_command(self, get_compute_size_cmd)
            self.debug_print(f"RESULT: {compute_size}")
            return compute_size
        else:
            print(f"Unknown active_remote_compute_type in ~/.ez.conf "
                f"detected: {self.active_remote_compute_type}")
            exit(1)

    def debug_print(self, str):
        if self.debug:
            print(str)

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
        print(f"ERROR: required dependency {command} not installed")
        if install_help is not None:
            print(f"TO INSTALL: {install_help}")
        return False

def check_dependencies(force = False) -> bool:
    """Install dependencies required for ez to run"""
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
    # TODO: remove permanently when we have stripped this dependency
    # if not check_installed("jupyter-repo2docker", 
    #     ("The Python package repo2docker must be installed to generate the "
    #      "container images used by ez.\n"
    #     "pip install jupyter-repo2docker"), force):
    #     return False
    return True

@click.group()
@click.option("--debug", is_flag=True, help="Output diagnostic information")
@click.option("--trace", is_flag=True, help="Trace execution")
@click.option("--insiders", is_flag=True, help="Run using VS Code Insiders")
@click.option("--dependencies", is_flag=True, help="Force check dependencies")
@click.option("--disable-jit", is_flag=True, help="Disable JIT activation")
@click.pass_context
def ez(ctx, debug, trace, insiders, dependencies, disable_jit):
    """Command-line interface for creating and using portable Python
    environments. To get started run ez init!"""
    # TODO: restore this once jit support is back
    # ctx.obj = Ez(debug, trace, insiders, disable_jit)
    ctx.obj = Ez(debug, trace, insiders, True)
    if not check_dependencies(dependencies):
        exit(1)
    def _save_context():
        ctx.obj.save()
    ctx.call_on_close(_save_context)

# TODO: delete after refactor
def exec_command_return_dataframe(cmd):
    result = subprocess.run(cmd.split(' '), capture_output=True)
    stdout = result.stdout.decode("utf-8")
    stream = StringIO(stdout)
    return pd.read_csv(stream, sep="\t", header=None)

@click.command()
@click.pass_obj
def init(ez):
    """Start here to initialize ez"""

    print("Step 1/5: Select Azure subscription to use\n")

    # Read subscriptions into a pandas dataframe
    cmd = "az account list -o tsv"
    df = exec_command_return_dataframe(cmd)
    df = df.sort_values(by=[5])

    # Print out a list of subscriptions for the user to select from
    current_subscription = -1
    for i, name in enumerate(df.iloc[:,5]):
        if df.iloc[i][3]:
            print(f"{i} {name} [green]<== CURRENT[/green]")
            current_subscription = i
        else:
            print(f"{i} {name}")

    # Ask the user to select the subscription
    while True:
        choice = IntPrompt.ask("Enter subscription # to use", 
                               default=current_subscription)
        if choice >= 0 and choice < df.shape[0]:
            break

    # Set default subscription in the Azure CLI 
    subscription_name = df.iloc[choice][5]
    subscription_id = df.iloc[choice][2]
    print(f"Selected {subscription_name}, subscription id: {subscription_id}")

    cmd = f"az account set --subscription {subscription_id}"
    subprocess.run(cmd.split(' '))

    # Select or create a new workspace
    # TODO: today this only creates a new resource group, make it select 
    # in the future
    print("\nStep 2/5: Create a new workspace\n")

    # Ask for name
    workspace_name = Prompt.ask("Workspace name", default="ezws")

    # Show existing resource groups scoped to selected subscription
    print("\nStep 3/5: Select or create Azure resource group to use\n")

    cmd = "az group list -o tsv"
    df = exec_command_return_dataframe(cmd)
    df = df.sort_values(by=[3])
    for i, name in enumerate(df.iloc[:,3]):
        print(f"{i} {name}")
    
    while True:
        choice = IntPrompt.ask("Enter resource group # to "
                               "use (-1 to create a new resource group)", 
                               default=-1)
        if choice >= -1 and choice < df.shape[0]:
            break

    if choice == -1:
        # Ask for resource group
        workspace_resource_group = Prompt.ask("Azure resource group name", 
                                          default=f"{workspace_name}-rg")

        # Ask user to select region
        cmd = "az account list-locations -o tsv"
        df = exec_command_return_dataframe(cmd)

        for i, name in enumerate(df.iloc[:,0]):
            print(f"{i} {name}")

        while True:
            choice = IntPrompt.ask("Enter region # to use", default=-1)
            if choice >= 0 and choice < df.shape[0]:
                break

        workspace_region = df.iloc[choice][1]

        print(f"Creating {workspace_resource_group} "
              f"in region {workspace_region}")

        # Create the resource group
        cmd = (f"az group create --location {workspace_region}" 
            f"--name {workspace_resource_group}")
        result = subprocess.run(cmd.split(' '))
        if result.returncode != 0:
            print(f"Azure resource group creation failed "
                  f"with return code {result.returncode}")
            exit(result.returncode)

        # Ask to create an Azure Container Registry
        choice = Prompt.ask("Create an Azure Container Registry? (blank "
                            "name will not create one)", default="")
        if choice != "":
            registry_name = choice
            cmd = (f"az acr create --resource-group {workspace_resource_group}"
                   f"--name {registry_name} --sku Basic")
            result = subprocess.run(cmd.split(' '))
            if result.returncode != 0:
                print(f"Azure Container Registry creation failed "
                      f"with return code {result.returncode}")
                exit(result.returncode)

    else:
        workspace_resource_group = df.iloc[choice][3]
        workspace_region = df.iloc[choice][1]
        print(f"Selected {workspace_resource_group}, "
              f"region {workspace_region}")

        # List Azure Container Registries in this resource group
        cmd = (f"az acr list --resource-group {workspace_resource_group} "
               "-o tsv")
        df = exec_command_return_dataframe(cmd)
        count = df.shape[0]

        if count == 0:
            registry_name = ""
            registry_region = ""
        elif count == 1:
            registry_name = df.iloc[0][10]
            registry_region = df.iloc[0][8]
        else:
            for i, name in enumerate(df.iloc[:,9]):
                print(f"{i} {name}")
            
            while True:
                choice = IntPrompt.ask("Enter registry # to use", default=-1)
                if choice >= 0 and choice < df.shape[0]:
                    break
            
            registry_name = df.iloc[choice][10]
            registry_region = df.iloc[choice][8]

        print(f"Selected registry {registry_name} in {registry_region}")

    # Ask for username 
    print("\nStep 4/5: Select user account name to use for compute resources")
    user_name = Prompt.ask("User name for VMs", default="ezuser")

    # Ask user to select an existing private key or create a new public/key 
    ssh_path = os.path.expanduser(C.SSH_DIR)
    files = [f for f in os.listdir(ssh_path) 
             if os.path.isfile(os.path.join(ssh_path, f))]
    keyfiles = []
    for file in files:
        extension = pathlib.Path(file).suffix
        if extension == "":
            if f"{file}.pub" in files:
                keyfiles.append(file)
    
    print("\nStep 5/5: Select or create SSH keys to use\n") 
    for i, keyfile in enumerate(keyfiles):
        print(f"{i} {keyfile}")
    
    # Ask the user to select the SSH key to use
    while True:
        choice = IntPrompt.ask("Enter # of key file to "
                               "use (-1 to create a new key)", 
                               default=-1)
        if choice >= -1 and choice < len(keyfiles):
            break
    
    # Generate a new keyfile
    if choice == -1:
        while True:
            choice = Prompt.ask("SSH keyfile name", default="id_rsa_keyfile")
            if choice in keyfiles:
                print(f"{choice} keyfile already exists")
            else:
                break

        keypath = os.path.expanduser(f"~/.ssh/{choice}")
        cmd = f"ssh-keygen -m PEM -t rsa -b 4096 -f {keypath} -q -N"
        cmdline = cmd.split(' ')
        cmdline.append('')
        result = subprocess.run(cmdline)
        keyfile = choice
        if result.returncode != 0:
            exit(result.returncode)
    else:
        keyfile = keyfiles[choice]
    
    keyfile_path = os.path.expanduser(f"~/.ssh/{keyfile}")
    print(f"SSH keyfile: {keyfile}/{keyfile}.pub")

    # Write the configuration file
    ez_config = {
        "workspace_name": workspace_name,
        "resource_group": workspace_resource_group,
        "registry_name": registry_name,
        "subscription": subscription_id,
        "region": workspace_region,
        "private_key_path": keyfile_path,
        "user_name": user_name,

        # Define fields
        "active_compute": "",
        "active_compute_type": "",
        "active_env": ""
    }

    ez_config_path = os.path.expanduser(C.WORKSPACE_CONFIG)
    if os.path.isfile(ez_config_path):
        choice = Prompt.ask(f"{ez_config_path} exists. Overwrite?", 
                            default="n")
        if choice == "y":
            os.remove(ez_config_path)
        else:
            exit(0)

    with open(ez_config_path, "w") as f:
        json.dump(ez_config, f, indent=4)

    print(f"""
ez is now configured, configuration file written to {ez_config_path}.

Try running creating a compute and running a GitHub
repo using it. Here's an example:

1. Create a new ez compute VM. This will create a VM and install GPU
   drivers and Docker.

ez compute create -n my-ez-gpu-vm -s Standard_NC6_Promo

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
compute.add_command(compute_commands.install_system)

# environment sub-commands

@ez.group()
def env():
    """Manage environments"""
    pass

env.add_command(env_commands.run)
env.add_command(env_commands.ls)
env.add_command(env_commands.cp)
env.add_command(env_commands.ssh)
env.add_command(env_commands.stop)
env.add_command(env_commands.up)
env.add_command(env_commands.go)