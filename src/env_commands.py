# env commands

import click, glob, json, os, random, shutil, subprocess, uuid

from azutil import (build_container_image, launch_vscode, pick_vm, 
    generate_vscode_project, is_gpu, jit_activate_vm, 
    get_active_compute_name, get_compute_size)
from exec import exec_script_using_ssh, exec_command
from ez_state import Ez
from formatting import printf, printf_err
from os import getcwd, path

def launch_user_interface(ez: Ez, user_interface, path_to_vscode_project, 
                          jupyter_port, token):
    """Bind user_interface to the running instance"""
    if user_interface == "code":
        printf(f"launch VS Code {path_to_vscode_project}")
        launch_vscode(ez, path_to_vscode_project)
    elif user_interface == "notebook" or user_interface == "lab":
        printf(f"launch Classic Jupyter "
              f"http://localhost:{jupyter_port}?token={token}")

def run_k8s(ez: Ez, env_name, git_uri, jupyter_port, compute_name,
            user_interface, git_clone, token, has_gpu, force_generate):
    """Run the environment in Kubernetes"""
    printf_err("k8s support needs reimplementation")
    exit(1)

    path_to_vscode_project = generate_vscode_project(ez, getcwd(), git_uri, 
                                                     jupyter_port, token, 
                                                     ".", has_gpu, 
                                                     force_generate, True)

    # ASSUME if path_to_vscode_project exists that image built alredy
    if not path.exists(path_to_vscode_project):
        build_cmd = (f"jupyter-repo2docker --image-name jflam/{env_name} "
                    f"--no-run {path_to_vscode_project}")
        print(f"BUILD Docker image locally: {build_cmd}")
        exec_command(ez, build_cmd)
        docker_cmd = (f"docker push jflam/{env_name}")
        print(f"PUSH Docker image to Docker Hub: {docker_cmd}")
        exec_command(ez, docker_cmd)

    launch_user_interface(ez, user_interface, path_to_vscode_project, 
                          jupyter_port, token)

    jupyter_variant = "notebook"
    if user_interface == "lab":
        jupyter_variant = "lab"

    kdo_cmd = (f"kdo -p {jupyter_port}:{jupyter_port} "
               "--spec '{\"resources\":{\"limits\":{\"nvidia.com/gpu\":\"1\"}}}' "
               f"jflam/{env_name} "
               f"nohup jupyter {jupyter_variant} --no-browser "
               f"--port {jupyter_port} --ip=0.0.0.0 "
               f"--NotebookApp.token={token} .")

    # kdo blocks while syncing local filesystem into the pod
    # CTRL+C will terminate.
    print(f"START pod {kdo_cmd}")
    print("TERMINATE using CTRL+C")
    exec_command(ez, kdo_cmd)

def run_vm(ez: Ez, env_name, git_uri, jupyter_port, compute_name,
           user_interface, git_clone, token, has_gpu, force_generate):
    """Run the environment in a VM"""
    build_container_image(ez, env_name, git_uri, jupyter_port, compute_name,
                          user_interface, git_clone)
    path_to_vscode_project = generate_vscode_project(ez, getcwd(), git_uri, 
                                                     jupyter_port, token, 
                                                     compute_name, has_gpu, 
                                                     force_generate)

    launch_user_interface(ez, user_interface, path_to_vscode_project, 
                          jupyter_port, token)

@click.command()
@click.option("--env-name", "-n", required=True, 
              help="Name of environment to start")
@click.option("--git-uri", "-g", required=True, 
              help="URI of git repo to load in the environment")
@click.option("--user-interface", "-u", default="code", 
              help="UI {notebook|lab|code} to use. Default is code")
@click.option("--compute-name", "-c", 
              help=("compute node to use (default is the "
              "current active compute node)"))
@click.option("--git-clone", is_flag=True, 
              help=("Force fresh clone of GitHub repo before "
              "starting environment"))
@click.option("--force-generate", is_flag=True, default=False,
              help="Force generation of the local VS Code project")
@click.pass_obj
def run(ez: Ez, env_name, git_uri, user_interface, compute_name, git_clone, 
        force_generate):
    """Create and run an environment"""
    printf_err("deprecated: Use ez env go instead")
    exit(0)

    compute_name = get_active_compute_name(ez, compute_name)

    # Initialize context
    ez.active_remote_compute = compute_name
    ez.active_remote_env = env_name
    ez.local_repo_name = path.basename(git_uri)

    jupyter_port = random.randint(1024, 8192)
    token = uuid.uuid4().hex 

    compute_size = get_compute_size(ez, compute_name)
    has_gpu = is_gpu(compute_size)

    if ez.active_remote_compute_type == 'vm':
        run_vm(ez, env_name, git_uri, jupyter_port, compute_name,
               user_interface, git_clone, token, has_gpu, force_generate)
    elif ez.active_remote_compute_type == 'k8s':
        run_k8s(ez, env_name, git_uri, jupyter_port, compute_name,
                user_interface, git_clone, token, has_gpu, force_generate)
    else:
        print(f"Unknown active_remote_compute_type in ~/.ez.conf: "
            f"{ez.active_remote_compute_type}")
        exit(1)
    exit(0)

@click.command()
@click.pass_obj
def ls(ez: Ez):
    """List running environments"""
    pass

@click.command()
@click.argument("src")
@click.argument("dest")
@click.pass_obj
def cp(ez: Ez, src, dest):
    """
Copy local files to/from an environment.

ez env cp <source> <dest>

The format of <source> and <dest> are important. Examples:

\b
foo.txt :.               Copy foo.txt to active environment /workspace dir
foo.txt :/remote/path    Copy foo.txt to active environment /remote/path dir
:/remote/path/foo.txt .  Copy active environment /remote/path/foo.txt locally
./*.txt :/remote/path    Copy local .txt files to active environment /remote/path
:/remote/path/*.txt ./   Copy active environment /remote/path/*.txt files locally
    """
    if ez.active_remote_compute == ".":
        # TODO: this might not be the case though - let's get feedback on this
        printf_err("Not needed for locally running environments. You can "
            "copy files to/from the local directory of the GitHub repo "
            "using existing filesystem commands.")
        exit(1)

    if not ez.active_remote_env:
        printf_err("No running environment")
        exit(1)
    
    if not src:
        printf_err("Missing src parameter")
        exit(1)
    
    if not dest:
        printf_err("Missing dest parameter")
        exit(1)
    
    if src.startswith(":") and dest.startswith(":"):
        printf_err("Both src and dest cannot start with ':' "
                   "to indicate remote")
        exit(1)
    elif src.startswith(":"):
        cmd = (f"scp -i {ez.private_key_path} {ez.user_name}@"
               f"{ez.active_remote_compute}.{ez.region}"
               f".cloudapp.azure.com:/home/{ez.user_name}/src/"
               f"{ez.active_remote_env}/{src[1:]} {dest}") 
        subprocess.run(cmd.split(" "))
    elif dest.startswith(":"):
        cmd = (f"scp -i {ez.private_key_path} {src} {ez.user_name}@"
               f"{ez.active_remote_compute}.{ez.region}"
               f".cloudapp.azure.com:/home/{ez.user_name}/src/"
               f"{ez.active_remote_env}/{dest[1:]}") 
        subprocess.run(cmd.split(" "))
    else:
        printf_err("One of src or dest must start with ':' to "
                   "indicate remote")
        exit(1)

@click.command()
@click.option("--compute-name", "-c", required=False,
              help="Compute name to migrate the environment to")
@click.option("--env-name", "-n", required=False,
              help="Environment name to start")
@click.pass_obj
def ssh(ez: Ez, compute_name, env_name):
    """SSH to an environment"""
    if not ez.active_remote_compute:
        if not compute_name:
            printf_err("--compute-name parameter must be specified "
                       "because there isn't an active compute environment.")
            exit(1)
    else:
        compute_name = ez.active_remote_compute

    if not ez.active_remote_env:
        if not env_name:
            printf_err("--env-name parameter must be specified "
                       "because there isn't an active environment.")    
            exit(1)
    else:
        env_name = ez.active_remote_env

    if compute_name != ".":
        # Run docker ps on the remote VM to figure out what the container id
        # of the running VS Code container is
        cmd = (f"ssh -i {ez.private_key_path} {ez.user_name}@{compute_name}."
            f"{ez.region}.cloudapp.azure.com docker ps --format "
            "{{.Image}},{{.ID}}")
    else:
        # Run a local docker ps command to get the container id
        cmd = "docker ps --format {{.Image}},{{.ID}}"
    result = subprocess.run(cmd.split(' '), capture_output=True)
    containers = result.stdout.decode("utf-8").split("\n")
    active_container_name = f"vsc-{env_name}-"
    vsc_containers = [c for c in containers if c.startswith(
                                                    active_container_name)]
    if len(vsc_containers) != 1:
        printf_err(f">1 container running with same env_name:")
        print(vsc_containers)
        exit(1)

    image_name, container_id = vsc_containers[0].split(",")
    if compute_name != ".":
        # Open a tunneled SSH connection into the running remote container
        cmd = (f"ssh -tt -i {ez.private_key_path} "
            f"{ez.user_name}@{compute_name}.{ez.region}.cloudapp.azure.com "
            f"docker exec -it -w /workspace {container_id} /bin/bash")
        printf(f"opened SSH connection to container {container_id} running "
            f"using image {image_name} on "
            f"{compute_name}.{ez.region}.cloudapp.azure.com")
    else:
        # Handle the local case
        cmd = f"docker exec -it -w /workspace {container_id} /bin/bash"
        printf(f"opened SSH connection to container {container_id} running "
               f"using image {image_name} on localhost")
    subprocess.run(cmd.split(' '))

@click.command()
@click.pass_obj
def stop(ez: Ez):
    pass

@click.command()
@click.option("--compute-name", "-c", required=False,
              help="Compute name to migrate the environment to")
@click.option("--env-name", "-n", required=False,
              help="Environment name to start")
@click.pass_obj
def up(ez: Ez, compute_name, env_name):
    """Migrate the current environment to a new compute node"""

    # Let's assume that we are in a local environment for the purpose
    # of this. Later I will add heuristics to error out if this is not
    # the case.

    # Get the URI of the repo we are currently in
    _, git_remote_uri = exec_command(ez, 
        "git config --get remote.origin.url")

    if git_remote_uri == "":
        printf_err(f"Directory {getcwd()} is not in a git repo")
        exit(1)

    printf(f"migrating {git_remote_uri} to {compute_name}")

    # Start the remote VM
    jit_activate_vm(ez, compute_name)
    ez.active_remote_compute = compute_name

    # Check to see if there are uncommitted changes
    patch_file = None
    exit_code, _ = exec_command(ez, 
        'git status | grep "Changes not staged for commit"', False)
    if exit_code == 0:
        printf("stashing uncommitted changes")
        exec_command(ez, "git stash")
        exec_command(ez, "git stash show -p --binary > ~/tmp/changes.patch")

        printf(f"copying changes.patch to {compute_name}")
        scp_cmd = (
            f"scp -i {ez.private_key_path} "
            f"~/tmp/changes.patch "
            f"{ez.user_name}@{compute_name}.{ez.region}.cloudapp.azure.com:"
            f"/home/{ez.user_name}/tmp/changes.patch"
        )
        exec_command(ez, scp_cmd)
        patch_file = "changes.patch"

    printf(f"starting {git_remote_uri} on {compute_name}")
    jupyter_port = 1235
    token = "1234"
    compute_size = get_compute_size(ez, compute_name)
    has_gpu = is_gpu(compute_size)
    build_container_image(ez, env_name, git_remote_uri, jupyter_port,
                          compute_name, "code", True, patch_file)
    path_to_vscode_project = generate_vscode_project(ez, getcwd(),
                                                     git_remote_uri,
                                                     jupyter_port, token,
                                                     compute_name, has_gpu, 
                                                     True)
    launch_vscode(ez, path_to_vscode_project)
    exit(0)

@click.command()
@click.option("--git-uri", "-g", required=True, 
              help="URI of git repo to load in the environment")
@click.option("--compute-name", "-c", required=False,
              help="Compute name to migrate the environment to")
@click.option("--env-name", "-n", required=False,
              help="Environment name to start")
@click.option("--use-acr", is_flag=True, default=False,
              help="Generate container using Azure Container Registry")
@click.option("--build", is_flag=True, default=False,
              help="When used with --use-acr forces a build of the container")
@click.pass_obj
def go(ez: Ez, git_uri, compute_name, env_name, use_acr: bool, build: bool):
    """New experimental version of the run command that will remove the need
    to have repo2docker installed."""

    # If compute name is "-" OR there is no active compute defined, prompt
    # the user to select (or create) a compute
    if compute_name == "-":
        print("Select which VM to use from this list of VMs provisioned "
              f"in resource group {ez.resource_group}")
        compute_name = pick_vm(ez.resource_group)
    elif not compute_name:
        # Use the current compute_name or prompt if none defined
        if not ez.active_remote_compute:
            print("Select which VM to use from this list of VMs provisioned "
                f"in resource group {ez.resource_group}")
            compute_name = pick_vm(ez.resource_group)
        else:
            compute_name = ez.active_remote_compute
    else:
        printf(f"using {compute_name} to run {git_uri}")

    if env_name is None:
        env_name = git_uri.split("/")[-1]
        printf(f"using {env_name} (repo name) as the env name")

    # env_name will be used for local name of repository and is the path
    # on a remote machine as well

    # If the local path exists already, then we don't clone unless the
    # --force-clone switch is specified.

    # Clone the repository locally to a subdirectory of the directory where
    # the command is run from.
    local_env_path = f"{getcwd()}/{env_name}"
    if path.exists(local_env_path):
        exec_command(ez, 
                     "git pull", 
                     description=f"updating {git_uri} in {local_env_path}", 
                     cwd=local_env_path)
    else:
        git_cmd = f"git clone {git_uri} {local_env_path}"
        exec_command(ez, 
                     git_cmd, 
                     description=f"cloning {git_uri} into {local_env_path}")

    # Read the ez.json configuration file at the root of the repository. This
    # needs to be read per project and contains some additional information:
    # - requires_gpu: True/False 
    # - base_container_image: name of the base container image
    env_json_path = f"{local_env_path}/ez.json"
    if path.exists(env_json_path):
        with open(env_json_path, "r") as f:
            ez_json = json.load(f)
    else:
        print("Need to have a default ez.json in the repo. Would you like "
              "me to generate one for you? (TODO)")
        # TODO: generate
        exit(1)

    if compute_name != ".":
        # Check to see if the remote compute has the GPU capability if needed
        # and fail if it doesn't.

        # TODO: Start the remote compute if necessary. Wait for it to complete
        # starting
        remote_env_path = f"/home/{ez.user_name}/src/{env_name}"

        # In the remote case, it needs to conditionally clone the git repo
        # onto the remote VM. If the repo was already cloned on the VM, then
        # we need to cd into the dir and git pull that repo. Otherwise just do
        # the clone.
        description = (f"clone/update {git_uri} on {compute_name} "
                       f"at {remote_env_path}")
        remote_pull_cmd = (f"[ -d '{remote_env_path}' ] && "
                           f"cd {remote_env_path} && git pull")
        exec_script_using_ssh(ez, 
            compute_name=compute_name, 
            script_text=remote_pull_cmd, 
            hide_output=True,
            description=description)

        remote_clone_cmd = (f"[ ! -d '{remote_env_path}' ] && "
                            f"git clone {git_uri} {remote_env_path}")
        exec_script_using_ssh(ez, 
            compute_name=compute_name, 
            script_text=remote_clone_cmd, 
            hide_output=True,
            description=description)

        # The .vscode directory contains a dynamically generated settings.json
        # file which points to the VM that the remote container will run on.

        # If it is a remote launch, we will need to generate the information
        # needed for the local devcontainer.json file, as well as for the
        # settings.json file that contains the .vscode/settings.json file that
        # contains "docker.host":
        # "ssh://user@machine.region.cloudapp.azure.com"

        printf("Generating .vscode/settings.json")
        ssh_connection = (f"{ez.user_name}@{compute_name}.{ez.region}"
                          ".cloudapp.azure.com")
        settings_json = f"""
{{
    "docker.host": "ssh://{ssh_connection}",
}}
"""
        vscode_dir = f"{local_env_path}/.vscode"
        settings_json_path = f"{vscode_dir}/settings.json"
        if not os.path.exists(vscode_dir):
            os.mkdir(vscode_dir)
        with open(settings_json_path, "wt+", encoding="utf-8") as f:
            f.write(settings_json)
    else:
        # local contrainer execution, so we need to generate a null 
        # .vscode/settings.json file (or delete existing file if there)

        # TODO: what really needs to be done is to remove an existing 
        # docker.host key from an existing settings.json file if it is there
        vscode_dir = f"{local_env_path}/.vscode"
        if os.path.exists(vscode_dir):
            if os.path.exists("settings.json"):
                os.remove(f"{vscode_dir}/settings.json")

    # Generate the devcontainer.json file. Much of this will eventually be
    # parameterized

    # The .devcontainer directory contains dynamically generated artifacts:
    #
    # 1. The devcontainer.json file that instructs VS Code what to do to
    #    create the container
    # 2. The generated Dockerfile that instructs Docker what to do to build
    #    the container
    # 3. The requirements.txt or environment.yml file that is called from the
    #    Dockerfile to install the python modules needed to run the code
    # 4. Any additional python files that are used to initialize the
    #    container, e.g., downloading data, caching models etc. 
    #
    # Note that 3) and 4) are all contained within the /build directory at the
    # root of the GitHub repo and are copied into the .devcontainer directory.
    # Those files could all be run from the /build directory as well with
    # a hand-written Dockerfile

    printf("Generating .devcontainer/devcontainer.json")
    if compute_name == ".":
        mount_path = local_env_path
    else:
        mount_path = remote_env_path

    # The generated devcontainer.json file will differ based on whether we 
    # are letting remote containers generate the container on the VM or 
    # whether we will ask it to pull from ACR on the remote machine.

    # In the case where it pulls the image from ACR, the remote machine will
    # need to have the ability to access ACR, which means that it will need
    # to have an Azure public/private key pair in place unless I make the
    # ACR image publicly accessible.

    # Using tokens for this and the compute must be configured to use it
    # by logging in automatically into Docker when you ask it to.
    if use_acr:
        if ez.registry_name is None:
            printf_err(f"Resource group {ez.resource_group} "
                "does not have an Azure Container Registry configured.")
            exit(1)
        docker_source=f"""
    "image": "{ez.registry_name}.azurecr.io/{ez.workspace_name}:{env_name}",
"""
    else:
        docker_source=f"""
    "dockerFile": "./Dockerfile",
"""

    requires_gpu = ez_json["requires_gpu"]
    if requires_gpu:
        runargs = """
        "--gpus=all",
        "--ipc=host",
"""
    else:
        runargs = ""

    devcontainer_json = f"""
{{
    {docker_source}
    "containerUser": "root",
    "workspaceFolder": "/workspace",
    "workspaceMount": "source={mount_path},target=/workspace,type=bind,consistency=cached",
    "extensions": [
        "ms-python.python",
        "ms-python.vscode-pylance"
    ],
    "runArgs": [
        {runargs}
    ],
}}
"""
    devcontainer_dir = f"{local_env_path}/.devcontainer"
    devcontainer_json_path = f"{devcontainer_dir}/devcontainer.json"
    if not os.path.exists(devcontainer_dir):
        os.mkdir(devcontainer_dir)
    with open(devcontainer_json_path, "wt+", encoding="utf-8") as f:
        f.write(devcontainer_json)

    # Generate the Dockerfile to be used by the project. The Dockerfile is
    # generated at launch time, and will have comments in it that will say
    # that it is machine-generated. Furthermore, the Dockerfile should be
    # excluded from the GH repo via .gitignore so that it doesn't pollute the
    # git history of the project. The Dockerfile will be generated and placed
    # in the .devcontainer directory locally or scp'd to the remote machine in
    # the well-known place where the cloned repo is stored:
    # /home/<ezuser>/ez/<GH repo name>

    # To generate the Dockerfile, information will be needed from the repo.
    # This first version of the command will just clone the repo into the
    # surrogate project directory. A future optimization may avoid the need to
    # clone the project locally as well.

    # Copy files from the /build directory into the .devcontainer directory
    printf("Copying /build files to /.devcontainer")
    build_files = glob.glob(f"{local_env_path}/build/*")
    for file in build_files:
        if os.path.isfile(file):
            shutil.copy(file, devcontainer_dir)

    # Only generate a default Dockerfile if the user doesn't supply one in
    # their /build directory
    if not os.path.exists(f"{devcontainer_dir}/Dockerfile"):
        dockerfile = f"""
FROM {ez_json["base_container_image"]}

COPY requirements.txt /tmp/requirements.txt
WORKDIR /tmp
RUN pip install -v -r requirements.txt
    """
        printf("Generating default .devcontainer/Dockerfile")
        dockerfile_path = f"{devcontainer_dir}/Dockerfile"
        with open(dockerfile_path, "wt+", encoding="utf-8") as f:
            f.write(dockerfile)

    # If the resource group contains ACR, we could optionally build the 
    # docker image there and import it. Sample command:
    #
    # az acr build --registry jflamregistry --image wine . 
    if use_acr and build:
        # TODO: only build if it isn't in the registry already
        # probably need a --force-build switch to force this happening too
        full_registry_name = (f"{ez.registry_name}.azurecr.io/"
                              f"{ez.workspace_name}")
        cmd = f"docker images {full_registry_name}"
        result = exec_command(ez, 
            cmd, 
            log=True, 
            description=f"checking if {full_registry_name} exists")
        if result[0] != 0:
            exit(1)
        if result[1].find(full_registry_name):
            printf(f"Skipping build, {full_registry_name} exists already")
        else:
            cmd = (f"az acr build --registry {ez.registry_name} "
                f"--image {env_name} .")
            exec_command(ez, 
                cmd, 
                cwd=f"{local_env_path}/build",
                log=True,
                description="building container image using ACR Tasks")

    # Launch the project by launching VS Code using "code .". In the future
    # this command will be replaced with "devcontainer open ." but because of
    # the remote bug in devcontainer, we will avoid doing this for now and
    # manually reopen the VS Code project.
    printf(f"Launching VS Code ... you will need to reload in "
           f"remote container by clicking the Reopen in Container button in "
           f"the notification box in the bottom right corner.")
    launch_vscode(ez, local_env_path)

    # Update ez state
    ez.active_remote_env = env_name
    ez.active_remote_compute = compute_name
    if compute_name != ".":
        ez.active_remote_compute_type = "vm"