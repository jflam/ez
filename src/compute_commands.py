# Compute commands

import click
import constants as C
import json
import os
import pandas as pd

from azutil import (copy_to_clipboard, enable_jit_access_on_vm, is_gpu, 
    jit_activate_vm, get_vm_size, get_active_compute_name, 
    mount_storage_account, get_compute_uri, get_host_ecdsa_key)
from exec import ExecResult, exec_cmd, exec_file, exit_on_error
from ez_state import Ez, EzRuntime
from fabric import Connection
from formatting import printf, printf_err
from os import path, system
from rich import print

@click.command()
@click.option("--compute-name", "-c", required=True, 
              help="Name of compute to create")
@click.option("--compute-size", "-s", 
              help="Size of Azure VM or '.' for local creation")
@click.option("--compute-type", "-t", default="vm",
              help=("Type of compute: vm (virtual machine) or "
              "k8s (Kubernetes)"))
@click.option("--image", "-i", default="UbuntuLTS", 
              help="Image to use to create the VM (default UbuntuLTS)")
@click.option("--no-install", "-q", is_flag=True, default=False,
              help=("Do not install system software"))
@click.pass_obj
def create(runtime: EzRuntime, compute_name, compute_size, compute_type, image, 
           no_install):
    """Create a compute node"""

    ez = runtime.current()

    # User can pass in nothing for --compute-size and we will helpfully list
    # all available vm sizes in the workspace region
    
    if compute_size == None:
        print(f"Missing VM size. VM sizes available in {ez.region}:")
        cmd = (f"az vm list-sizes --subscription {ez.subscription} "
               f"--location {ez.region} --output table")
        result = exec_cmd(cmd)
        exit_on_error(result)
        print(result.stdout)
        exit(1)

    # Check to see if the compute-name is taken already
    cmd = (f"az vm list --resource-group {ez.resource_group} -d -o table "
        f"--query \"[?name=='{compute_name}']\"")
    result = exec_cmd(cmd)
    if result.exit_code != 0:
        # Don't exit on error as failure here will be caught when trying to
        # create the VM instance.
        printf_err(result.stderr)
    else:
        if result.stdout != "":
            printf_err(f"The compute {compute_name} is already "
                "taken. Try a different --compute-name")
            exit(1)

    # Select provisioning scripts for the VM based on whether compute_size is
    # a GPU
    if compute_type == "vm":

        # TODO: parameterize this in .ez.conf
        os_disk_size = 256

        description = (
            f"creating virtual machine {compute_name} size "
            f"{compute_size} in resource group {ez.resource_group}...")

        cmd = (
            f"az vm create --name {compute_name}"
            f"             --resource-group {ez.resource_group}"
            f"             --size {compute_size}"
            f"             --image {image}"
            f"             --ssh-key-values {ez.private_key_path}.pub"
            f"             --admin-username {ez.user_name}"
            f"             --public-ip-address-dns-name {compute_name}"
            f"             --public-ip-sku Standard"
            f"             --os-disk-size-gb {os_disk_size}"
        )   
        result = exec_cmd(cmd, description=description)
        exit_on_error(result)
        
        if no_install:
            exit(0)

        # Once the VM is created, we need to trust the created VM. This
        # requires that we use a trusted code-path to retrieve the host ECDSA
        # key of the newly-created VM and add that to the known_hosts list in
        # ~/.ssh/known_hosts. We will use the Azure CLI to invoke a script
        # on the server that will return the host's ECDSA key. We will then
        # append that to the known_hosts file.
        # Unfortunately, this is a very slow code path for some reason and
        # it takes ~30s to retrieve the host's ECDSA key.

        host_key = get_host_ecdsa_key(ez, compute_name)
        hostname = f"{compute_name}.{ez.region}.cloudapp.azure.com"
        
        with open(os.path.expanduser("~/.ssh/known_hosts"), "a") as f:
            f.write(f"{hostname} {host_key}")

        # TODO: analyze output for correct flags
        enable_jit_access_on_vm(ez, compute_name)

        __update_system(ez, compute_name, compute_size)
        __enable_acr(ez, compute_name)
        __enable_github(ez, compute_name)

        # Ask machine to reboot (need to swallow exception here)
        uri = get_compute_uri(ez, compute_name)
        exec_cmd("sudo reboot", uri=uri, 
            private_key_path=ez.private_key_path, 
            description=f"Rebooting {compute_name}")

        ez.active_remote_compute = compute_name 
        ez.active_remote_compute_type = compute_type
        exit(0)
    elif compute_type == "k8s":
        # TODO: implement
        print(f"NOT IMPLEMENTED create --compute-type=k8s. Manually create.")
        exit(1)
    else:
        print(f"Unknown --compute-type: {compute_type}")
        exit(1)

@click.option("--compute-name", "-c", required=True, 
              help="Name of compute to update")
@click.option("--compute-size", "-s", 
              help="Size of Azure VM or '.' for local update")
@click.command()
@click.pass_obj
def update_system(runtime: EzRuntime, compute_name, compute_size):
    """Update the system software on compute_name"""
    ez = runtime.current()
    result = __update_system(ez, compute_name, compute_size)
    exit_on_error(result)

    # Update current remote compute state
    ez.active_remote_compute = compute_name 
    ez.active_remote_compute_type = "vm"
    exit(0)

def __update_system(ez: Ez, compute_name: str, 
    compute_size: str) -> ExecResult:
    """Update the system software on compute_name and using compute_size to
    determine if we need to install CPU or GPU system software"""
    provision_vm_script = "provision-cpu"
    if is_gpu(compute_size):
        provision_vm_script = "provision-gpu"

    description = "Installing system software on compute"
    provision_vm_script_path = (
        f"{path.dirname(path.realpath(__file__))}/scripts/"
        f"{provision_vm_script}"
    )

    uri = get_compute_uri(ez, compute_name)
    result = exec_file(provision_vm_script_path, uri=uri, 
        private_key_path=ez.private_key_path, description=description)
    return result

def __enable_acr(ez: Ez, compute_name: str) -> ExecResult:
    """Internal function to enable ACR on compute_name"""
    # Repository name maps to workspace name
    # Environment name maps to tag
    # e.g., jflamregistry.azurecr.io/ezws:pytorch_tutorials
    repository_name = ez.workspace_name

    # az acr token create will recreate token if exists already
    # the system-generated _repositories_push scope-map implies pull
    cmd = (f"az acr token create --name {compute_name} "
           f"--registry {ez.registry_name} "
           f"--scope-map _repositories_push "
           f"--output json")
    fq_repo_name = f"{ez.registry_name}.azurecr.io/{repository_name}"
    result = exec_cmd(cmd, description=f"generating {fq_repo_name} token")
    exit_on_error(result)

    j = json.loads(result.stdout)
    token_name = j["name"]

    # Retrieve the generated passwords and use them for the token
    password1 = j["credentials"]["passwords"][0]["value"]

    # Generate the .bashrc that needs to existing on the server to assign the
    # token on each startup. TODO: need a better story for generating and
    # assigning the password in the future.
    bashrc = (f"echo \"docker login -u {token_name} -p {password1} "
              f"{ez.registry_name}.azurecr.io\" >> ~/.bashrc")

    # Append the docker login command to the ~/.bashrc on compute_name
    uri = get_compute_uri(ez, compute_name)
    result = exec_cmd(bashrc, uri=uri, private_key_path=ez.private_key_path,
        description=f"Updating ~/.bashrc on {compute_name}")
    exit_on_error(result)
    return result

@click.option("--compute-name", "-c", required=True, 
              help="Name of compute to update")
@click.command()
@click.pass_obj
def enable_acr(runtime: EzRuntime, compute_name: str):
    """Enable ACR on compute_name"""
    ez = runtime.current()
    __enable_acr(ez, compute_name)
    exit(0)

def __enable_github(ez: Ez, 
    compute_name: str, 
    manual: bool=False):
    """Internal function to enable github on compute_name"""
    # Generate a new public/private key pair on compute_name
    # TODO: fix the terrible echo hack
    comment = f"ez generated token for {compute_name}" 
    cmd = (f"echo -e 'y\n' | ssh-keygen -t ed25519 -C \"{comment}\" "
           f"-N '' -f /home/{ez.user_name}/.ssh/id_rsa_github "
           f"> /dev/null 2>&1")
    uri = get_compute_uri(ez, compute_name)
    result = exec_cmd(cmd, uri=uri, private_key_path=ez.private_key_path,
        description=f"Generating public/private key pair on {compute_name}")
    exit_on_error(result)

    # cat the public key
    cmd = f"cat /home/{ez.user_name}/.ssh/id_rsa_github.pub"
    result = exec_cmd(cmd, uri=uri, private_key_path=ez.private_key_path,
        description="Reading generated public key")
    exit_on_error(result)
    public_key = result.stdout.strip()

    # Ensure that github RSA key is in the known-hosts file

    # Retrieve the GitHub public key from github.com
    result = exec_cmd("ssh-keyscan -H github.com > /tmp/github.pub")
    exit_on_error(result)

    # Compute the SHA256 hash of the github.com public key
    result = exec_cmd("ssh-keygen -lf /tmp/github.pub -E sha256")
    exit_on_error(result)

    # Compare computed SHA256 hash with known github.com public key
    if C.GITHUB_PUBLIC_KEY_SHA256 in result.stdout:

        # Append the GitHub public key to known_hosts
        result = exec_cmd("cat /tmp/github.pub >> ~/.ssh/known_hosts")
        exit_on_error(result)

        # Test connection with GitHub by trying to SSH using the key
        result = exec_cmd("ssh -T git@github.com")
        if "successfully authenticated" in result.stderr:
            printf("completed: validating GitHub public key and adding "
                    "to known_hosts", indent=2)
        else:
            printf_err(f"error connecting to GitHub: {result.stderr}")
    else:
        printf_err(f"Possible man-in-the-middle attack! "
                    f"Computed SHA256 hash from public key retrieved from "
                    f"github.com is: {result.stdout} and known "
                    f"SHA256 hash is {C.GITHUB_PUBLIC_KEY_SHA256}.")
        exit(1)

    # Append this file to VM ~/.ssh/config file so that git on the VM 
    # knows how to connect
    gh_config = f"""
Host github.com
    HostName github.com
    AddKeysToAgent yes
    IdentityFile /home/{ez.user_name}/.ssh/id_rsa_github
"""
    # Write locally and copy the local file to the server
    with open("/tmp/gh_config", "w") as f:
        f.write(gh_config)

    # TODO: consider writing a copy to server function using fabric
    hostname = f"{compute_name}.{ez.region}.cloudapp.azure.com"
    with Connection(hostname, user=ez.user_name) as c:
        c.put("/tmp/gh_config", f"/home/{ez.user_name}/gh_config")

    result = exec_cmd(f"cat /home/{ez.user_name}/gh_config "
        f">> /home/{ez.user_name}/.ssh/config", uri=uri, 
        private_key_path=ez.private_key_path)
    exit_on_error(result)

    # Append github.com to the list of known hosts on the server
    result = exec_cmd("ssh-keyscan -H github.com >> ~/.ssh/known_hosts",
        uri = get_compute_uri(ez, compute_name), 
        private_key_path=ez.private_key_path)
    exit_on_error(result)

    if manual:
        # Put it on the clipboard 
        copy_to_clipboard(ez, public_key)

        # Open https://github.com/settings/ssh/new
        printf("Copied public key to clipboard")
        printf("Open https://github.com/settings/ssh/new in "
            "your web browser and paste the contents of the public key into "
            "the public key field and name your new SSH token to match this "
            f"machine. Suggested name: {compute_name}-token")
    else:
        # write public key to tmp file
        with open(f"/tmp/id_rsa_github.pub", "w") as f:
            f.write(public_key)
            
        # Register this public key with GitHub and ensure that the GitHub
        # title (displayed in https://github.com/settings/keys) contains the
        # fully-qualified name of the VM to make it easier to GC keys as
        # GitHub doesn't provide a way to programmatically remove SSH keys.
        cmd = (f"gh ssh-key add /tmp/id_rsa_github.pub "
               f"--title \"{compute_name}.{ez.region}.cloudapp.azure.com\"")
        result = exec_cmd(cmd, 
            description="Registering public key with GitHub")
        exit_on_error(result)

@click.option("--compute-name", "-c", required=True, 
              help="Name of compute to update")
@click.option("--manual", "-m", is_flag=True, default=False,
              help=("Manual install: won't use GitHub CLI"))
@click.command()
@click.pass_obj
def enable_github(runtime: EzRuntime, compute_name: str, manual: bool):
    """Enable github on compute_name"""
    ez = runtime.current()
    __enable_github(ez, compute_name, manual)
    exit(0)

@click.command()
@click.option("--compute-name", "-c", help="Name of VM to delete")
@click.pass_obj
def delete(runtime: EzRuntime, compute_name):
    """Delete a compute node"""
    ez = runtime.current()
    compute_name = get_active_compute_name(ez, compute_name)
    description = f"deleting compute node {compute_name}"
    result = exec_cmd((f"az vm delete --yes --name {compute_name} "
        f"--resource-group {ez.resource_group}"), description=description)
    exit_on_error(result)

    # Remove this VM from known_hosts 
    uri = f"{compute_name}.{ez.region}.cloudapp.azure.com"
    result = exec_cmd(f"ssh-keygen -R {uri}", 
        description=f"Removing {uri} from known_hosts")
    exit_on_error(result)

    # NOTE: GitHub does not provide programmatic access to remove SSH keys
    # from GitHub, so we may need to improve the experience on this end to
    # make it easier for people to "GC" their GitHub keys.
    exit(0)

@click.command()
@click.option("--all", "-a", is_flag=True, default=False,
              help=("List all (current workspace is default)"))
@click.pass_obj
def ls(runtime: EzRuntime, all: bool):
    """List available compute nodes"""
    
    ez = runtime.current()

    # The information to retrieve for each VM are:
    # Name, Size, vCPU, RAM, Disk Size, (GPU Config), On/Off
    if all:
        cmd = f"az vm list -d -o json"
        description = "Querying all workspaces for a list of VMs"
    else:
        cmd = f"az vm list --resource-group {ez.resource_group} -d -o json"
        description = (f"Querying workspace {ez.workspace_name} for a list "
            "of VMs")
    result = exec_cmd(cmd, description=description)
    exit_on_error(result)

    all_vm_sizes = {}
    j = json.loads(result.stdout)
    df = pd.DataFrame(columns=["Name", "Size", "Resource_Group", "RAM(GB)", 
        "Cores", "Region", "State"])
    for vm in j:
        name = vm["name"]
        vm_size = vm["hardwareProfile"]["vmSize"]
        region = vm["location"]
        all_vm_sizes[region] = None
        power_state = vm["powerState"]
        resource_group = vm["resourceGroup"]
        df = df.append({
            "Name": name,
            "Size": vm_size,
            "RAM(GB)": "",
            "Cores": "",
            "Resource_Group": resource_group,
            "Region": region, 
            "State": power_state
        }, ignore_index=True)
    
    # Get VM sizes for each region 
    # Maybe consider caching these values in the future
    for region in all_vm_sizes.keys():
        cmd = f"az vm list-sizes -l {region} --output json"
        result = exec_cmd(cmd, 
            description=f"Querying Azure for VM sizes in {region}")
        exit_on_error(result)
        vm_sizes = json.loads(result.stdout)
        vm_sizes_in_region = {}
        for vm_size in vm_sizes:
            vm_sizes_in_region[vm_size["name"]] = {
                "memory": int(int(vm_size["memoryInMb"])/1024),
                "cores": vm_size["numberOfCores"]
            }
        all_vm_sizes[region] = vm_sizes_in_region

    # Lookup VM sizes from each region
    for i, row in df.iterrows():
        region = row["Region"]
        vm_size = row["Size"]
        if region in all_vm_sizes:
            region_table = all_vm_sizes[region]
            if vm_size in region_table:
                entry = region_table[vm_size]
                df.at[i, "RAM(GB)"] = entry["memory"]
                df.at[i, "Cores"] = entry["cores"]

    print(df)
    exit(0)

@click.command()
@click.option("--compute-name", "-c", help="Name of VM to start")
@click.pass_obj
def start(runtime: EzRuntime, compute_name):
    """Start a virtual machine"""

    ez = runtime.current()
    if compute_name == ".":
        printf("Nothing done, local compute is already started")
        exit(0)

    compute_name = get_active_compute_name(ez, compute_name)
    jit_activate_vm(ez, compute_name)
    result = exec_cmd(f"az vm start --name {compute_name} "
        f"--resource-group {ez.resource_group}",
        description=f"starting compute node {compute_name}")
    exit_on_error(result)
    ez.active_remote_compute = compute_name
    exit(0)

@click.command()
@click.option("--compute-name", "-c", help="Name of VM to stop")
@click.pass_obj
def stop(runtime: EzRuntime, compute_name):
    """Stop a virtual machine"""
    ez = runtime.current()
    compute_name = get_active_compute_name(ez, compute_name)
    # TODO: get compute_type too and fail for now on this
    result = exec_cmd(f"az vm deallocate --name {compute_name} "
        f"--resource-group {ez.resource_group}",
        description=f"stopping compute node {compute_name}")
    exit_on_error(result)
    ez.active_remote_compute = compute_name
    exit(0)

@click.command()
@click.option("--compute-name", "-c", help="Name of VM to ssh into")
@click.pass_obj
def ssh(runtime: EzRuntime, compute_name):
    """SSH to a virtual machine"""
    ez = runtime.current()
    compute_name = get_active_compute_name(ez, compute_name)
    # TODO: get compute_type too and fail for now on this
    jit_activate_vm(ez, compute_name)
    ez.active_remote_compute = compute_name
    ssh_remote_host = get_compute_uri(ez, compute_name)
    cmd = (
        f"ssh -i {ez.private_key_path} "
        f" -o StrictHostKeyChecking=no "
        f"{ssh_remote_host}"
    )
    printf(f"Connecting to {ssh_remote_host}")

    # Use system() here because we want to have an interactive session
    system(cmd)

@click.command()
@click.option("--compute-name", "-n", help="Name of compute node")
@click.option("--compute-type", "-t", default="vm",
              help=("Type of compute: vm (virtual machine) or "
              "k8s (Kubernetes)"))
@click.pass_obj
def select(runtime: EzRuntime, compute_name, compute_type):
    """Select a compute node"""
    ez = runtime.current()
    compute_name = get_active_compute_name(ez, compute_name)

    # TODO: implement menu
    if compute_type == "vm":
        # Just select the compute node now
        print(f"SELECTING VM {compute_name}")
    elif compute_type == "k8s":
        result = exec_cmd(f"kubectl config use-context {compute_name}")
        exit_on_error(result)

    ez.active_remote_compute = compute_name
    ez.active_remote_compute_type = compute_type
    ez.active_remote_env = ""
    exit(0)

@click.command()
@click.option("--compute-name", "-n", help="Name of compute node")
@click.pass_obj
def info(runtime: EzRuntime, compute_name):
    """Get info about compute hardware"""
    ez = runtime.current()
    compute_name = get_active_compute_name(ez, compute_name)
    compute_size = get_vm_size(ez, compute_name)
    # TODO: do this with AKS and the correct compute pool

    # Now use the vm_size to get hardware details 
    result = exec_cmd(f"az vm list-sizes -l {ez.region} --output tsv "
        f"| grep {compute_size}", description=f"Querying {compute_name}")
    if result.exit_code == 0:
        specs = result.stdout.split("\t")
        print(f"  [green]INFO[/green] for {compute_name} size: {specs[2]}: "
            f"cores: {specs[3]} RAM: {specs[1]}MB Disk: {specs[5].strip()}MB")
        exit(0)
    else:
        printf_err(result.stderr)
        exit(result.exit_code)

@click.command()
@click.option("--compute-name", "-c", required=False,
              help="Compute name to migrate the environment to")
@click.pass_obj
def mount(runtime: EzRuntime, compute_name: str):
    """Mount the workspace file share onto the compute and storage"""
    ez = runtime.current()
    if compute_name is None:
        compute_name = ez.active_remote_compute

    # TODO: figure out whether to mount onto VM or onto each env
    # TODO: figure out where to mount - for now let's call it data
    # mount_path = f"/home/{ez.user_name}/src/{env_name}/data"
    mount_path = f"/home/{ez.user_name}/data"

    exit(mount_storage_account(ez, compute_name, mount_path))

@click.command()
@click.option("--compute-name", "-c", help="Name of host to get key from")
@click.pass_obj
def get_host_key(runtime: EzRuntime, compute_name):
    """Retrieve the ECDSA host key of compute_name"""
    ez = runtime.current()
    key = get_host_ecdsa_key(ez, compute_name)
    print(key)
