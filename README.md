# ez
Commands for working with portable environments

## Automated Installation and Configuration

`ez` has been developed and tested in two environments: Mac OS and Ubuntu
20.04 running under WSL 2 on Windows. It has not been tested on Windows yet. 
`ez` is a Python 3 application.

If you are running `ez` on Ubuntu in WSL 2, I've created a script to help
setup the environment for you. 

Before you can run this script, you will need to have [Docker
Desktop](https://docs.microsoft.com/en-us/windows/wsl/tutorials/wsl-containers)
installed with WSL 2 integrations enabled. You can learn more about installing
[WSL 2 from the Windows Store from
here](https://devblogs.microsoft.com/commandline/a-preview-of-wsl-in-the-microsoft-store-is-now-available/).

```sh
curl --remote-name https://gist.githubusercontent.com/jflam/bb75d1172607eba59edfec0157fa724b/raw/f4fdee178235d9a658be47ba1efd708b03e2d968/preinstall-ubuntu.sh
bash preinstall-ubuntu.sh
```

This script does the following things:

1. Installs a few dependencies: `git`, `curl`
1. Installs `Miniconda3`
1. Generates two SSH keys: `id_rsa_azure` and `id_rsa_github` that will be 
used to connect to GitHub and connect to resources that you create with
Azure.
1. Install the GitHub CLI
1. Install the Azure CLI
1. Logs into GitHub and Azure
1. Installs `ez` by cloning this repo
1. Initializes `ez`

## Manual installation

If you are installing manually from this repo and you have everything setup

To setup the tool for running in development mode, you will first need to
run from `src/`:

```
python setup.py develop
```

This will make it possible to continue to develop locally and have your 
changes immediately reflected each time you run `ez` from any directory.
