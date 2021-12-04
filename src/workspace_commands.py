# Workspace commands

import click, json, os, pathlib, subprocess
import constants as C
import pandas as pd
import subprocess

from ez_state import Ez, EzConfig, EzRuntime

from azutil import get_storage_account_key
from exec import exec_cmd, exec_cmd_return_dataframe, exit_on_error
from ez_state import Ez, EzConfig
from formatting import printf_err, printf
from rich import print
from rich.prompt import IntPrompt, Prompt

def get_subscription_name(subscription):
    """Helper function to query Azure CLI for info about subscription"""
    cmd = ["az", "account", "show", "-s", subscription, "-o", "tsv"]
    result = subprocess.run(cmd, stdout=subprocess.PIPE)
    fields = result.stdout.decode("utf-8").split("\t")
    return fields[5]

def create_workspace() -> Ez:
    """Create a new workspace

    Interactively asks the user for information about a new workspace. This
    includes the Azure subscription to use, the resource group to create or
    use, whether to create additional resources such as an Azure container
    registry or an Azure storage account, name of the new workspace, the
    SSH keys to use to authenticate with Azure and GitHub, etc.

    Returns:
        Ez: a configuration object populated with answers to questions
    """

    # Construct an empty ez configuration object
    ez = Ez()

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
        # Move this later
        workspace_resource_group = Prompt.ask("Azure resource group name", 
                                          default=f"ezws-todo_region-rg")

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
        if df is None:
            registry_name = ""
            registry_region = ""
        else:
            count = df.shape[0]
            if count == 1:
                # TODO: soemthing less fragile
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

        if registry_name != "":
            printf(f"Selected registry {registry_name} in {registry_region}")
        else:
            printf(f"No registry selected")

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

        if storage_account_name != "":
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
        else:
            file_share_name = ""
        
        if file_share_name != "":
            printf(f"Selected file share {file_share_name}")
        else:
            printf(f"No file share selected")

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
        # TODO: handle passphrases properly instead of specifying empty
        cmd = f"ssh-keygen -m PEM -t rsa -b 4096 -f {keypath} -q -N ''"
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

    return ez

@click.command()
@click.pass_obj
def create(runtime: EzRuntime):
    """Create a workspace interactively"""

    ez = create_workspace()
    runtime.add(ez)
    runtime.save()

@click.command()
@click.pass_obj
def delete(runtime: EzRuntime):
    """Delete a workspace"""
    pass

@click.command()
@click.option("--name", "-n", required=True, 
              help="Name of workspace to select")
@click.pass_obj
def select(runtime: EzRuntime, name: str):
    """Select workspace"""
    runtime.select(name)
    printf(f"Selected workspace {name}")
    runtime.save()

@click.command()
@click.pass_obj
def ls(runtime: EzRuntime):
    """List workspaces"""
    pass

@click.command()
@click.pass_obj
def info(runtime: EzRuntime):
    """Show information about the ez workspace"""

    # TODO: clean this up
    ez = runtime.current()
    subscription_name = get_subscription_name(ez.subscription)
    subscription_info = f"{subscription_name} ({ez.subscription})"

    print(f"Current workspace:\n")
    print(f"[green]Name[/green]:           {ez.workspace_name}")
    print(f"[green]Subscription[/green]:   {subscription_info}")
    print(f"[green]Resource Group[/green]: {ez.resource_group}")
    print(f"[green]Azure Region[/green]:   {ez.region}")