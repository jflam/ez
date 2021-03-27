# File that manages the ~/.easy.conf file

from io import open
from os import path
import configparser

CONFIGURATION_FILENAME = "~/.ez.conf"

class EzSettings:
    # Workspace
    workspace_name: str
    subscription: str
    region: str
    private_key_path: str
    user_name: str

    # Remotes
    active_remote_vm: str 
    active_remote_env: str

def load_settings() -> EzSettings:
    """Load configuration settings from the ~/.easy.conf file"""
    config = configparser.ConfigParser()
    settings = EzSettings()

    easy_conf_file = path.expanduser(CONFIGURATION_FILENAME)
    if path.exists(easy_conf_file):
        config.read(easy_conf_file)
    else:
        settings.workspace_name = "ezworkspace"
        settings.subscription = ""
        settings.region = ""
        settings.private_key_path = ""
        settings.user_name = "ezuser"
        settings.active_remote_vm = ""
        settings.active_remote_env = ""
        return settings

    settings = EzSettings()
    settings.workspace_name = config["Workspace"]["workspace_name"]
    settings.subscription = config["Workspace"]["subscription"]
    settings.region = config["Workspace"]["region"]
    settings.private_key_path = config["Workspace"]["private_key_path"]
    settings.user_name = config["Workspace"]["user_name"]
    settings.active_remote_vm = config["Remotes"]["active_remote_vm"]
    settings.active_remote_env = config["Remotes"]["active_remote_env"]
    return settings

def save_settings(settings: EzSettings) -> None:
    """Save configuration settings to the ~/.easy.conf file"""
    config = configparser.ConfigParser()
    config["Workspace"] = {}
    config["Remotes"] = {}
    config["Workspace"]["workspace_name"] = settings.workspace_name
    config["Workspace"]["subscription"] = settings.subscription
    config["Workspace"]["region"] = settings.region
    config["Workspace"]["private_key_path"] = settings.private_key_path
    config["Workspace"]["user_name"] = settings.user_name
    config["Remotes"]["active_remote_vm"] = settings.active_remote_vm
    config["Remotes"]["active_remote_env"] = settings.active_remote_env
    with open(path.expanduser(CONFIGURATION_FILENAME), 'w') as file:
        config.write(file)

# Initialize settings
ez_settings = load_settings()

def get_active_vm_name(vm_name) -> str:
    """Get the active VM name or exit"""
    if vm_name == None:
        if ez_settings.active_remote_vm == "":
            print("No active remote VM, so you must specify --vm-name")
            exit(1)
        else:
            return ez_settings.active_remote_vm
    else:
        return vm_name