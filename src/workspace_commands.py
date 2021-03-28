# Workspace commands

from os import path, system
import click
from ez import CONFIGURATION_FILENAME
from azutil import login

@click.command()
@click.option("--workspace-name", "-n", default="ez-workspace", 
              help="Name of workspace to create (default ezworkspace)")
@click.option("--subscription", "-s", required=True, 
              help="Azure subscription id")
@click.option("--region", "-r", required=True, 
              help="Region to create workspace in")
@click.option("--private-key-path", "-k", required=True, 
              help="Path to private key to use for this registration")
@click.option("--user-name", "-u", default="ezuser", 
              help="Username for all VMs (default is ezuser)")
@click.pass_obj
def create(ez, workspace_name, subscription, region, 
           private_key_path, user_name):
    """Create a workspace"""

    # A workspace is defined by ~/.easy.conf file
    if path.exists(path.expanduser(CONFIGURATION_FILENAME)):
        print((
               f"{CONFIGURATION_FILENAME} exists already. ez only "
               f"supports a single registration at a time today."))
        exit(1)

    click.echo(f"CREATING a new workspace: {workspace_name}")
    ez.workspace_name = workspace_name
    ez.subscription = subscription
    ez.region = region
    ez.private_key_path = private_key_path
    ez.user_name = user_name

    print("Creating a new ez workspace:")
    print("============================")
    print(f"Name:              {workspace_name}")
    print(f"Subscription:      {subscription}")
    print(f"Region:            {region}")
    print(f"Private Key Path:  {private_key_path}")
    print(f"User name:         {user_name}\n\n")

    print(f"Creating a new Azure Resource Group: {ez.resource_group}\n")
    system((
           f"az group create --location {region} --name {ez.resource_group} "
           f"--output table"))
    print("DONE!")

@click.command()
def delete():
  """Delete a workspace"""
  pass

@click.command()
def ls():
  """List workspaces"""
  pass
