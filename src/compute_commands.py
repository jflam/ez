# Compute commands

import click
import constants as C
import json
import subprocess

from azutil import (copy_to_clipboard, enable_jit_access_on_vm, is_gpu, 
    jit_activate_vm, get_vm_size, get_active_compute_name, 
    mount_storage_account)
from exec import exec_script_using_ssh, exec_command
from ez_state import Ez
from fabric import Connection
from formatting import printf, printf_err
from os import path, system
from rich import print
from typing import Tuple

@click.command()
@click.option("--compute-name", "-n", required=True, 
              help="Name of compute to create")
@click.option("--compute-size", "-s", 
              help="Size of Azure VM or '.' for local creation")
@click.option("--compute-type", "-t", default="vm",
              help=("Type of compute: vm (virtual machine) or "
              "k8s (Kubernetes)"))
@click.option("--image", "-i", default="UbuntuLTS", 
              help="Image to use to create the VM (default UbuntuLTS)")
@click.option("--check-dns", "-c", is_flag=True, 
              help=("Check if DNS name is available for "
              "--compute-name in region"))
@click.option("--no-install", "-q", is_flag=True, default=False,
              help=("Do not install system software"))
@click.pass_obj
def create(ez: Ez, compute_name, compute_size, compute_type, image, 
           check_dns, no_install):
    """Create a compute node"""

    # User can pass in nothing for --compute-size and we will helpfully list
    # all available vm sizes in the workspace region
    
    if compute_size == None:
        print(f"Missing VM size. VM sizes available in {ez.region}:")
        cmd = (f"az vm list-sizes --subscription {ez.subscription} "
               f"--location {ez.region} --output table")
        subprocess.run(cmd.split(" "))
        exit(1)

    # Check to see if the compute-name is taken already
    if check_dns:
        compute_dns_name = f"{compute_name}.{ez.region}.cloudapp.azure.com"
        if system(f"nslookup {compute_dns_name} > /dev/null") == 0:
            printf_err(f"The domain name {compute_dns_name} is already "
                "taken. Try a different --compute-name")
            exit(1)

    # Select provisioning scripts for the VM based on whether compute_size is
    # a GPU
    if compute_type == "vm":
        provision_vm_script = "provision-cpu"
        if is_gpu(compute_size):
            provision_vm_script = "provision-gpu"

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
        returncode, out = exec_command(ez, cmd, description=description)
        if returncode != 0:
            print(out)
            exit(1)
        
        if no_install:
            exit(0)

        # TODO: analyze output for correct flags
        enable_jit_access_on_vm(ez, compute_name)

        description = "Installing system software on compute"
        provision_vm_script_path = (
            f"{path.dirname(path.realpath(__file__))}/scripts/"
            f"{provision_vm_script}"
        )
        exec_script_using_ssh(
            ez, 
            script_path=provision_vm_script_path, 
            compute_name=compute_name, 
            line_by_line=True,
            description=description)

        __enable_acr(ez, compute_name)
        __enable_github(ez, compute_name)

        # Ask machine to reboot (need to swallow exception here)
        try:
            exec_script_using_ssh(
                ez,
                compute_name,
                script_text="sudo reboot",
                description=f"Rebooting {compute_name}"
            )
        except Exception:
            pass

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
def update_system(ez: Ez, compute_name, compute_size):
    """Update the system software on compute"""
    description = "Updating system software on compute"
    provision_vm_script = "provision-cpu"
    if is_gpu(compute_size):
        provision_vm_script = "provision-gpu"
    provision_vm_script_path = (
        f"{path.dirname(path.realpath(__file__))}/scripts/"
        f"{provision_vm_script}"
    )
    exec_script_using_ssh(
        ez, 
        script_path=provision_vm_script_path, 
        compute_name=compute_name, 
        description=description,
        line_by_line=True)
    # Update current remote compute state
    ez.active_remote_compute = compute_name 
    ez.active_remote_compute_type = "vm"

def __enable_acr(ez: Ez, compute_name: str) -> Tuple[int, str]:
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
    retval, output = exec_command(ez, 
        cmd, 
        description=f"generating {fq_repo_name} token")

    if retval != 0:
        print(output)
        exit(retval)

    j = json.loads(output)
    token_name = j["name"]

    # Retrieve the generated passwords and use them for the token
    password1 = j["credentials"]["passwords"][0]["value"]
    password2 = j["credentials"]["passwords"][1]["value"]

    # Generate the .bashrc that needs to existing on the server to assign the
    # token on each startup. TODO: need a better story for generating and
    # assigning the password in the future.
    bashrc = (f"echo \"docker login -u {token_name} -p {password1} "
              f"{ez.registry_name}.azurecr.io\" >> ~/.bashrc")

    # Append the docker login command to the ~/.bashrc on compute_name
    return exec_script_using_ssh(ez, 
        script_text=bashrc, 
        compute_name=compute_name,
        description=f"Updating ~/.bashrc on {compute_name}")

@click.option("--compute-name", "-c", required=True, 
              help="Name of compute to update")
@click.command()
@click.pass_obj
def enable_acr(ez: Ez, compute_name: str):
    """Enable ACR on compute_name"""
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
    result = exec_script_using_ssh(ez,
        script_text=cmd,
        compute_name=compute_name,
        description=f"Generating public/private key pair on {compute_name}")

    # cat the public key
    cmd = f"cat /home/{ez.user_name}/.ssh/id_rsa_github.pub"
    result = exec_script_using_ssh(ez, 
        compute_name=compute_name, 
        script_text=cmd,
        hide_output=True,
        description="Reading generated public key")
    if result[0] != 0:
        printf_err(f"{result[1]}")
        exit(1)
    public_key = result[1].strip()

    # Ensure that github RSA key is in the known-hosts file
    hostname = f"{compute_name}.{ez.region}.cloudapp.azure.com"
    with Connection(hostname, user=ez.user_name) as c:
        # Retrieve the GitHub public key
        c.run("ssh-keyscan -H github.com > /tmp/github.pub", hide="both")

        # Compute the SHA256 hash of the public key
        result = c.run("ssh-keygen -lf /tmp/github.pub -E sha256", 
                       hide="both")

        # Compare computed SHA256 hash of public key with known good value
        if C.GITHUB_PUBLIC_KEY_SHA256 in result.stdout:

            # Append the retrieved GitHub public key to known_hosts
            c.run("cat /tmp/github.pub >> ~/.ssh/known_hosts")

            # Verify that we can actually connect to GitHub
            result = c.run("ssh -T git@github.com", warn=True, hide="both")
            if "successfully authenticated" in result.stdout:
                printf("completed: validating GitHub public key and adding "
                       "to known_hosts")
            else:
                printf_err(f"error connecting to GitHub: {result.stderr}")
        else:
            printf_err(f"Possible man-in-the-middle attack! "
                       f"Computed SHA256 hash from public key retrieved from "
                       f"github.com is: {result.stdout} and known "
                       f"SHA256 hash is {C.GITHUB_PUBLIC_KEY_SHA256}.")
            exit(1)

    gh_config = """
Host github.com
    HostName github.com
    AddKeysToAgent yes
    IdentityFile ~/.ssh/id_rsa_github
"""
    # Write locally
    with open("/tmp/gh_config", "w") as f:
        f.write(gh_config)

    with Connection(hostname, user=ez.user_name) as c:
        c.put("/tmp/gh_config", f"/home/{ez.user_name}/gh_config")
        c.run(f"cat /home/{ez.user_name}/gh_config "
              f">> /home/{ez.user_name}/.ssh/config")

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
            
        # pass tmp file to gh cli
        cmd = (f"gh ssh-key add /tmp/id_rsa_github.pub "
               f"--title \"{compute_name}-token\"")
        exec_command(ez, 
            cmd, 
            description="registering public key with GitHub")

@click.option("--compute-name", "-c", required=True, 
              help="Name of compute to update")
@click.option("--manual", "-m", is_flag=True, default=False,
              help=("Manual install: won't use GitHub CLI"))
@click.command()
@click.pass_obj
def enable_github(ez: Ez, 
    compute_name: str, 
    manual: bool):
    """Enable github on compute_name"""
    __enable_github(ez, compute_name, manual)
    exit(0)

@click.command()
@click.option("--compute-name", "-c", help="Name of VM to delete")
@click.pass_obj
def delete(ez: Ez, compute_name):
    """Delete a compute node"""
    compute_name = get_active_compute_name(ez, compute_name)
    description = f"deleting compute node {compute_name}"
    exec_command(ez, (
        f"az vm delete --yes --name {compute_name} "
        f"--resource-group {ez.resource_group}"),
        description=description)
    exit(0)

@click.command()
@click.pass_obj
def ls(ez: Ez):
    """List running compute nodes"""
    ls_cmd = (
        f"az vm list -d --resource-group {ez.resource_group} "
        f"--query=\"[?powerState=='VM running'].[name]\" -o tsv"
    )
    description = f"querying Azure"
    _, output = exec_command(ez, ls_cmd, description=description)

    # TODO cleanup output
    print("RUNNING VMs (* == current)")
    lines = output.splitlines()
    for line in lines:
        if line == ez.active_remote_compute:
            print(f"* [green]{line}[/green]")
        else:
            print(f"  {line}")

    print("RUNNING AKS clusters (* == current)")
    print("...TODO")
    exit(0)

@click.command()
@click.option("--compute-name", "-c", help="Name of VM to start")
@click.pass_obj
def start(ez: Ez, compute_name):
    """Start a virtual machine"""
    # TODO: do nothing if compute-name is not a VM
    compute_name = get_active_compute_name(ez, compute_name)
    jit_activate_vm(ez, compute_name)
    exec_command(ez, 
                 (f"az vm start --name {compute_name} "
                  f"--resource-group {ez.resource_group}"),
                 description=f"starting compute node {compute_name}")
    ez.active_remote_compute = compute_name
    exit(0)

@click.command()
@click.option("--compute-name", "-c", help="Name of VM to stop")
@click.pass_obj
def stop(ez: Ez, compute_name):
    """Stop a virtual machine"""
    compute_name = get_active_compute_name(ez, compute_name)
    # TODO: get compute_type too and fail for now on this
    exec_command(ez, 
                 (f"az vm deallocate --name {compute_name} "
                  f"--resource-group {ez.resource_group}"),
                 description=f"stopping compute node {compute_name}")
    exit(0)

@click.command()
@click.option("--compute-name", "-c", help="Name of VM to ssh into")
@click.pass_obj
def ssh(ez: Ez, compute_name):
    """SSH to a virtual machine"""
    compute_name = get_active_compute_name(ez, compute_name)
    # TODO: get compute_type too and fail for now on this
    jit_activate_vm(ez, compute_name)
    ez.active_remote_compute = compute_name
    ssh_remote_host = (
        f"{ez.user_name}@{compute_name}."
        f"{ez.region}.cloudapp.azure.com"
    )
    cmd = (
        f"ssh -i {ez.private_key_path} "
        f" -o StrictHostKeyChecking=no "
        f"{ssh_remote_host}"
    )
    printf(f"Connecting to {ssh_remote_host}")
    system(cmd)

@click.command()
@click.option("--compute-name", "-n", help="Name of compute node")
@click.option("--compute-type", "-t", default="vm",
              help=("Type of compute: vm (virtual machine) or "
              "k8s (Kubernetes)"))
@click.pass_obj
def select(ez: Ez, compute_name, compute_type):
    """Select a compute node"""
    compute_name = get_active_compute_name(ez, compute_name)

    # TODO: implement menu
    if compute_type == "vm":
        _ = get_vm_size(ez, compute_name)

        # Just select the compute node now
        print(f"SELECTING VM {compute_name}")
        ez.active_remote_compute = compute_name
        ez.active_remote_compute_type = compute_type
        ez.active_remote_env = ""
        exit(0)
    elif compute_type == "k8s":
        exec_command(ez, f"kubectl config use-context {compute_name}")
        ez.active_remote_compute = compute_name
        ez.active_remote_compute_type = compute_type
        ez.active_remote_env = ""
        exit(0)

@click.command()
@click.option("--compute-name", "-n", help="Name of compute node")
@click.pass_obj
def info(ez: Ez, compute_name):
    """Get info about compute hardware"""
    compute_name = get_active_compute_name(ez, compute_name)
    compute_size = get_vm_size(ez, compute_name)
    # TODO: do this with AKS and the correct compute pool

    # Now use the vm_size to get hardware details 
    retcode, out = exec_command(
        ez, 
        f"az vm list-sizes -l {ez.region} --output tsv | grep {compute_size}",
        description=f"querying {compute_name} for details",
        debug=True)
    print(out)
    if retcode == 0:
        specs = out.split("\t")
        print((
            f"[green]INFO[/green] for {compute_name} size: {specs[2]}: "
            f"cores: {specs[3]} RAM: {specs[1]}MB Disk: {specs[5].strip()}MB"))
    else:
        printf_err(out)
    exit(retcode)

@click.command()
@click.option("--compute-name", "-c", required=False,
              help="Compute name to migrate the environment to")
@click.pass_obj
def mount(ez: Ez, compute_name: str):
    """Mount the workspace file share onto the compute and storage"""
    if compute_name is None:
        compute_name = ez.active_remote_compute

    # TODO: figure out whether to mount onto VM or onto each env
    # TODO: figure out where to mount - for now let's call it data
    # mount_path = f"/home/{ez.user_name}/src/{env_name}/data"
    mount_path = f"/home/{ez.user_name}/data"

    if mount_storage_account(ez, compute_name, mount_path):
        exit(0)
    else:
        exit(1)
