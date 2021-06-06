import click
from os import path, system
import configparser

CONFIGURATION_FILENAME = "~/.ez.conf"

# Import sub-commands
import workspace_commands
import compute_commands
import env_commands

from azutil import exec_command

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
        """Load configuration settings from the ~/.easy.conf file"""
        config = configparser.ConfigParser()

        easy_conf_file = path.expanduser(CONFIGURATION_FILENAME)
        if path.exists(easy_conf_file):
            config.read(easy_conf_file)
            self.workspace_name = config["Workspace"]["workspace_name"]
            self.resource_group = config["Workspace"]["resource_group"]
            self.subscription = config["Workspace"]["subscription"]
            self.region = config["Workspace"]["region"]
            self.private_key_path = config["Workspace"]["private_key_path"]
            self.user_name = config["Workspace"]["user_name"]
            self.active_remote_compute = (
                config["Remotes"]["active_remote_compute"])
            self.active_remote_compute_type = (
                config["Remotes"]["active_remote_compute_type"])
            self.active_remote_env = config["Remotes"]["active_remote_env"]
        else:
            self.workspace_name = "ez-workspace"
            self.resource_group = "ez-workspace-rg"
            self.subscription = ""
            self.region = ""
            self.private_key_path = ""
            self.user_name = "ezuser"
            self.active_remote_compute = ""
            self.active_remote_compute_type = ""
            self.active_remote_env = ""

    def save(self):
        """Save configuration settings to the ~/.easy.conf file"""
        config = configparser.ConfigParser()
        config["Workspace"] = {}
        config["Remotes"] = {}
        config["Workspace"]["workspace_name"] = self.workspace_name
        config["Workspace"]["resource_group"] = self.resource_group
        config["Workspace"]["subscription"] = self.subscription
        config["Workspace"]["region"] = self.region
        config["Workspace"]["private_key_path"] = self.private_key_path
        config["Workspace"]["user_name"] = self.user_name
        config["Remotes"]["active_remote_compute"] = (
            self.active_remote_compute)
        config["Remotes"]["active_remote_compute_type"] = (
            self.active_remote_compute_type)
        config["Remotes"]["active_remote_env"] = self.active_remote_env
        with open(path.expanduser(CONFIGURATION_FILENAME), 'w') as file:
            config.write(file)
    
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
        # TODO: handle case where compute_type is AKS
        if compute_name == '.':
            return '.'

        self.debug_print(f"GET compute size for {compute_name}...")
        get_compute_size_cmd = (
            f"az vm show --name {compute_name} "
            f"--resource-group {self.resource_group} "
            f"--query hardwareProfile.vmSize -o tsv"
        )
        _, compute_size = exec_command(self, get_compute_size_cmd)
        self.debug_print(f"RESULT: {compute_size}")
        return compute_size

    def debug_print(self, str):
        if self.debug:
            print(str)

# ez top-level command

def check_installed(command: str, 
                    install_help: str = None) -> bool:
    """Check if command is installed and display install_help if not"""
    returncode = system(f"which {command} > /dev/null")
    if returncode == 0:
        return True
    else:
        print(f"ERROR: required dependency {command} not installed")
        if install_help is not None:
            print(f"TO INSTALL: {install_help}")
        return False

def check_dependencies() -> bool:
    """Install dependencies required for ez to run"""
    if not check_installed("az", 
        "curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash"):
        return False
    if not check_installed("docker", 
        ("If you are using WSL2, you must install Docker Desktop on Windows. "
         "https://hub.docker.com/editions/community/docker-ce-desktop-windows/"
        )):
        return False
    if not check_installed("jupyter-repo2docker", 
        "pip install jupyter-repo2docker"):
        return False
    return True

@click.group()
@click.option("--debug", is_flag=True, help="Output diagnostic information")
@click.option("--trace", is_flag=True, help="Trace execution")
@click.option("--insiders", is_flag=True, help="Run using VS Code Insiders")
@click.option("--disable-jit", is_flag=True, help="Disable JIT activation")
@click.pass_context
def ez(ctx, debug, trace, insiders, disable_jit):
    """Command-line interface for creating and using portable Python
    environments"""
    ctx.obj = Ez(debug, trace, insiders, disable_jit)
    if not check_dependencies():
        exit(1)
    def _save_context():
        ctx.obj.save()
    ctx.call_on_close(_save_context)

# workspace sub-commands

@ez.group()
def workspace():
    """Manage workspaces"""
    pass

workspace.add_command(workspace_commands.create)
workspace.add_command(workspace_commands.delete)
workspace.add_command(workspace_commands.ls)

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
