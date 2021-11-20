import click
import constants as C
import json
import os
import pandas as pd
import pathlib
import platform
import subprocess

import compute_commands
import env_commands
import workspace_commands

from azutil import get_storage_account_key
from exec import exec_cmd, exec_cmd_return_dataframe, exit_on_error
from ez_state import Ez
from formatting import printf_err, printf
from os import system
from rich import print
from rich.console import Console 
from rich.prompt import IntPrompt, Prompt

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

def check_dependencies(ez: Ez, force: bool=False) -> bool:
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
    ctx.obj = Ez(debug=debug, insiders=insiders, disable_jit=disable_jit)
    if not check_dependencies(ctx.obj, dependencies):
        exit(1)
    def _save_context():
        ctx.obj.save()
    ctx.call_on_close(_save_context)

@click.command()
@click.pass_obj
def init(ez: Ez):
    """Start here to initialize ez"""

    print("Step 1/5: Select Azure subscription to use\n")

    # Read subscriptions into a pandas dataframe
    cmd = "az account list -o tsv"
    df = exec_cmd_return_dataframe(cmd)
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
    result = exec_cmd(cmd)
    exit_on_error(result)

    # Show existing resource groups scoped to selected subscription
    print("\nStep 2/5: Select or create Azure resource group to use\n")

    cmd = "az group list -o tsv"
    df = exec_cmd_return_dataframe(cmd)
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
        df = exec_cmd_return_dataframe(cmd)

        for i, name in enumerate(df.iloc[:,0]):
            print(f"{i} {name}")

        while True:
            choice = IntPrompt.ask("Enter region # to use", default=-1)
            if choice >= 0 and choice < df.shape[0]:
                break

        workspace_region = df.iloc[choice][3]

        # Create the resource group
        cmd = (f"az group create --location {workspace_region} " 
            f"--resource-group {workspace_resource_group}")
        result = exec_cmd(cmd, description=f"Creating "
            "{workspace_resource_group} in {workspace_region}")
        exit_on_error(result)

        # Ask to create an Azure Container Registry
        choice = Prompt.ask("Name of Azure Container Registry to create? "
                    "(blank will not create one; name cannot have dashes "
                    "earn it)", default="")
        if choice != "":
            registry_name = choice
            cmd = (f"az acr create --resource-group "
                f"{workspace_resource_group} --name {registry_name} "
                f"--sku Premium")
            result = exec_cmd(cmd, description=f"Creating Premium Azure "
                f"Container Registry {registry_name}")
            exit_on_error(result)

        # Ask to create an Azure Storage Account
        choice = Prompt.ask("Name of Azure Storage Account to create? (blank "
            "name will not create one; name cannot have dashes in it)", 
            default="")
        if choice != "":
            storage_account_name = choice
            cmd = (f"az storage account create --name {storage_account_name} "
                f"--resource-group {workspace_resource_group}")
            result = exec_cmd(cmd, description=f"Creating Azure Storage "
                f"Account {storage_account_name}")
            exit_on_error(result)

            # Create file share
            choice = Prompt.ask("Create an Azure File Share?", 
                default="ezdata")
            if choice == "":
                # TODO: make this loop if empty rather than exiting
                printf_err("Must create an Azure File Share when creating "
                    "an Azure Storage Account")
                exit(1)
            else:
                file_share_name = choice
                # TODO: prompt about quota size of file share and give user an
                # option to increase
                cmd = (f"az storage share-rm create --name {file_share_name} "
                    f"--quota 512 --storage-account {storage_account_name}")
                result = exec_cmd(cmd, description=f"Creating Azure File "
                    f"Share {file_share_name}")
                exit_on_error(result)
    else:
        workspace_resource_group = df.iloc[choice][3]
        workspace_region = df.iloc[choice][1]
        printf(f"Selected {workspace_resource_group}, "
            f"region {workspace_region}")

        # List Azure Container Registries in this resource group
        cmd = (f"az acr list --resource-group {workspace_resource_group} "
               "-o tsv")
        df = exec_cmd_return_dataframe(cmd)
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

        if registry_name is not None:
            printf(f"Selected registry {registry_name} in {registry_region}")

        # Discover storage account
        cmd = (f"az storage account list --resource-group "
            f"{workspace_resource_group} -o json")
        result = exec_cmd(cmd)
        exit_on_error(result)
        j = json.loads(result.stdout)
        df = pd.DataFrame(columns=["Name"])
        for account in j:
            name = account["name"]
            df = df.append({
                "Name": name,
            }, ignore_index=True)
        count = df.shape[0]
        if count == 0:
            storage_account_name = ""
        elif count == 1:
            storage_account_name = df.iloc[0][0]
        else:
            for i, name in enumerate(df.iloc[:,1]):
                print(f"{i} {name}")

            while True:
                choice = IntPrompt.ask("Enter storage account # to use", 
                    default=-1)
                if choice >= 0 and choice < df.shape[0]:
                    break
            
            storage_account_name = df.iloc[choice][0]

        if storage_account_name is not None:
            printf(f"Selected storage account {storage_account_name}")

        # Discover file share name
        key = get_storage_account_key(storage_account_name, 
            workspace_resource_group)
        if key is None:
            printf_err("Could not retrieve storage account key")
            exit(1)

        cmd = (f"az storage share list --account-name "
            f"{storage_account_name} --account-key {key} -o tsv")
        df = exec_cmd_return_dataframe(cmd)
        count = df.shape[0]

        if count == 0:
            file_share_name = ""
        elif count == 1:
            file_share_name = df.iloc[0][1]
        else:
            for i, name in enumerate(df.iloc[:,2]):
                print(f"{i} {name}")

            while True:
                choice = IntPrompt.ask("Enter storage account # to use", 
                    default=-1)
                if choice >= 0 and choice < df.shape[0]:
                    break
            
            file_share_name = df.iloc[choice][1]
        
        if file_share_name is not None:
            printf(f"Selected file share {file_share_name}")

    # Create a new workspace 
    print("\nStep 3/5: Create a new workspace\n")

    # Ask for name which defaults to indicating region in workspace
    workspace_name = Prompt.ask("Workspace name", 
        default=f"ezws-{workspace_region}")

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
        keyfile = choice
        cmd = f"ssh-keygen -m PEM -t rsa -b 4096 -f {keypath} -q -N"
        result = exec_cmd(cmd)
        exit_on_error(result)
    else:
        keyfile = keyfiles[choice]
    
    keyfile_path = os.path.expanduser(f"~/.ssh/{keyfile}")
    printf(f"Using SSH keyfile: {keyfile}/{keyfile}.pub")

    # Set the configuration
    ez.workspace_name = workspace_name
    ez.resource_group = workspace_resource_group
    ez.registry_name = registry_name
    ez.storage_account_name = storage_account_name
    ez.file_share_name = file_share_name
    ez.subscription = subscription_id
    ez.region = workspace_region
    ez.private_key_path = keyfile_path
    ez.user_name = user_name
    ez.active_remote_compute = ""
    ez.active_remote_compute_type = ""
    ez.active_remote_env = ""
    
    ez_config_path = os.path.expanduser(C.WORKSPACE_CONFIG)
    if os.path.isfile(ez_config_path):
        choice = Prompt.ask(f"{ez_config_path} exists. Overwrite?", 
                            default="n")
        if choice == "y":
            os.remove(ez_config_path)
        else:
            exit(0)

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