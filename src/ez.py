import click
from os import path, system
import configparser

CONFIGURATION_FILENAME = "~/.ez.conf"

# Import sub-commands
import workspace_commands
import vm_commands
import env_commands

from azutil import exec_command

# Ez object defines application-wide state 

class Ez(object):
    # Options
    debug: str
    trace: str
    insiders: bool

    # Workspace
    workspace_name: str
    resource_group: str
    subscription: str
    region: str
    private_key_path: str
    user_name: str

    # Remotes
    active_remote_vm: str 
    active_remote_env: str

    # Runtime state
    logged_in: bool
    jit_activated: bool

    def __init__(self, debug=False, trace=False, insiders=False):
        self.debug = debug 
        self.trace = trace
        self.insiders = insiders
        self.logged_in = False
        self.jit_activated = False
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
            self.active_remote_vm = config["Remotes"]["active_remote_vm"]
            self.active_remote_env = config["Remotes"]["active_remote_env"]
        else:
            self.workspace_name = "ez-workspace"
            self.resource_group = "ez-workspace-rg"
            self.subscription = ""
            self.region = ""
            self.private_key_path = ""
            self.user_name = "ezuser"
            self.active_remote_vm = ""
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
        config["Remotes"]["active_remote_vm"] = self.active_remote_vm
        config["Remotes"]["active_remote_env"] = self.active_remote_env
        with open(path.expanduser(CONFIGURATION_FILENAME), 'w') as file:
            config.write(file)
    
    def get_active_vm_name(self, vm_name) -> str:
        """Get the active VM name or exit"""
        if vm_name == None:
            if self.active_remote_vm == "":
                print("No active remote VM, so you must specify --vm-name")
                exit(1)
            else:
                return self.active_remote_vm
        else:
            return vm_name

    def get_vm_size(self, vm_name) -> str:
        """Return the vm size of vm_name"""
        # Special return value for localhost
        if vm_name == '.':
            return '.'

        self.debug_print(f"GET vm size for {vm_name}...")
        get_vm_size_cmd = (
            f"az vm show --name {vm_name} "
            f"--resource-group {self.resource_group} "
            f"--query hardwareProfile.vmSize -o tsv"
        )
        _, vm_size = exec_command(self, get_vm_size_cmd)
        self.debug_print(f"RESULT: {vm_size}")
        return vm_size

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
@click.pass_context
def ez(ctx, debug, trace, insiders):
    """Command-line interface for creating and using portable Python
    environments"""
    ctx.obj = Ez(debug, trace, insiders)
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

# vm sub-commands

@ez.group()
def vm():
    """Manage virtual machines"""
    pass

vm.add_command(vm_commands.create)
vm.add_command(vm_commands.delete)
vm.add_command(vm_commands.ls)
vm.add_command(vm_commands.start)
vm.add_command(vm_commands.stop)
vm.add_command(vm_commands.select)
vm.add_command(vm_commands.info)
vm.add_command(vm_commands.ssh)

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
