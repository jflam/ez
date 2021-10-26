import constants as C
import json
import os

from os import path
from datetime import datetime

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

    # Authentication state
    last_auth_check: datetime

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

        # TODO: handle older versions of .ez.json gracefully
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
            self.last_auth_check = datetime.strptime(
                ez_config["last_auth_check"], "%c")
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
            self.last_auth_check = datetime.now()

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
            "active_env": self.active_remote_env,
            "last_auth_check": datetime.strftime(self.last_auth_check, "%c")
        }
        with open(config_path, "w") as f:
            json.dump(ez_config, f, indent=4)

    def debug_print(self, str):
        if self.debug:
            print(str)