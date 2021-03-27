# Workspace commands

from os import path, system
from settings import CONFIGURATION_FILENAME
import sys
import click
sys.path.insert(0, "..")
from settings import ez_settings, save_settings
from azutil import login

@click.command()
@click.option("--workspace-name", "-n", default="ez-workspace", help="Name of workspace to create (default ezworkspace)")
@click.option("--subscription", "-s", required=True, help="Azure subscription id")
@click.option("--region", "-r", required=True, help="Region to create workspace in")
@click.option("--private-key-path", "-k", required=True, help="Path to private key to use for this registration")
@click.option("--user-name", "-u", default="ezuser", help="Username for all VMs (default is ezuser)")
def create(workspace_name, subscription, region, private_key_path, user_name):
    """Create a workspace"""

    # A workspace is defined by ~/.easy.conf file
    if path.exists(path.expanduser(CONFIGURATION_FILENAME)):
        print(f"{CONFIGURATION_FILENAME} exists already. easy only supports a single registration")
        print("at a time today. To register a new configuration, make sure to manually")
        print("delete the current configuration by running easy workspace delete or")
        print(f"deleting the {CONFIGURATION_FILENAME} file")
        exit(1)

    click.echo(f"CREATING a new workspace: {workspace_name}")
    ez_settings.workspace_name = workspace_name
    ez_settings.subscription = subscription
    ez_settings.region = region
    ez_settings.private_key_path = private_key_path
    ez_settings.user_name = user_name
    save_settings(ez_settings)

    login()
    print("Creating a new ez workspace:")
    print("============================")
    print(f"Name:              {workspace_name}")
    print(f"Subscription:      {subscription}")
    print(f"Region:            {region}")
    print(f"Private Key Path:  {private_key_path}")
    print(f"User name:         {user_name}\n\n")

    resource_group = f"{workspace_name}-rg"
    print(f"Creating a new Azure Resource Group: {resource_group}\n")
    system(f"az group create --location {region} --name {resource_group} --output table")
    print("DONE!")

@click.command()
def delete():
  """Delete a workspace"""
  pass

@click.command()
def ls():
  """List workspaces"""
  pass
