import constants as C
import json, os

from os import path
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict

@dataclass
class Ez:
    # Workspace
    workspace_name: str=None
    resource_group: str=None
    registry_name: str=None
    storage_account_name: str=None
    file_share_name: str=None
    subscription: str=None
    region: str=None
    private_key_path: str=None
    user_name: str=None

    # Remotes
    active_remote_compute: str=None
    active_remote_compute_type: str=None
    active_remote_env: str=None

    # Authentication state
    last_auth_check: datetime=None

@dataclass
class EzConfig:
    current_workspace: str=None
    workspaces: Dict[str, Ez]=field(default_factory=dict)

class EzRuntime:
    debug: str
    trace: str
    insiders: bool
    disable_jit: bool

    last_auth_check: datetime

    logged_in: bool
    jit_activated: bool

    config: EzConfig

    """Manages ez workspaces in ~/.ez.json configuration file

    The ~/.ez.json file contains a dictionary of workspace metadata. Each
    workspace is represented by an Ez object. The workspace_name property of
    the workspace object is the key into the master dictionary stored in 
    ~/.ez.json.
    """
    def __init__(self, ez_config_path: str="~/.ez.json"):
        """Creates and inits new EzRuntime object

        Loads the configuration from ~/.ez.json or a caller-provided path

        Args:
            ez_config_path (str, optional): [description]. Defaults to "~/.ez.json".
        """

        self.debug = False 
        self.trace = False
        self.insiders = False
        self.disable_jit = False

        self.last_auth_check = None

        self.logged_in = False
        self.jit_activated = False
        self.config = EzConfig()

        path = os.path.expanduser(ez_config_path)
        if os.path.exists(path):
            try:
                with open(os.path.expanduser(ez_config_path), "rt") as f:
                    state = json.load(f)
            except json.decoder.JSONDecodeError:
                return

            try:
                self.config = EzConfig(**state)
            except TypeError:
                pass

            for workspace_name, workspace in self.config.workspaces.items():
                self.config.workspaces[workspace_name] = Ez(**workspace)

    def update(self, ez: Ez) -> None:
        """Update configuration using this workspace config

        Args:
            ez (Ez): workspace config to update
        """
        self.config.workspaces[ez.workspace_name] = ez

    def save(self, ez_config_path: str="~/.ez.json") -> None:
        """Save current configuration

        Writes the configuration to ~/.ez.json or a caller-provided path.

        Args:
            ez (Ez): [description]
            ez_config_path (str, optional): config path. Defaults to "~/.ez.json".
        """
        # Swizzle Ez dataclasses back to dicts
        for key, value in self.config.workspaces.items():
            self.config.workspaces[key] = value.__dict__
        with open(os.path.expanduser(ez_config_path), "w") as f:
            json.dump(self.config.__dict__, f)

    def select(self, workspace_name: str) -> Ez:
        """Selects workspace_name as current workspace

        Args:
            workspace_name (str): Workspace name

        Returns:
            Ez: configuration object for selected workspace
        """
        self.config.current_workspace = workspace_name
        return self.config.workspaces[workspace_name]

    def add(self, ez: Ez, replace: bool=False) -> None:
        """Add a new Ez configuration to the global configuration object

        Adds ez to the EzConfig dictionary and also sets it as the current
        workspace.

        Args:
            ez (Ez): an Ez object that contains a configuration to add
            replace (bool): replace an existing configuration (default False) 

        Raises:
            ValueError: if the workspace_name of ez object already exists and replace
            is false
        """
        if ez.workspace_name in self.config.workspaces:
            raise ValueError(f"workspace {ez.workspace_name} already exists "
                f"in configuration. Use replace=True to replace")
        self.config.current_workspace = ez.workspace_name
        self.config.workspaces[ez.workspace_name] = ez

    def current(self) -> Ez:
        """Selects the current workspace 

        Returns:
            Ez: configuration object for current workspace
        """
        return self.config.workspaces[self.config.current_workspace]