# bash script for setting up pre-requisites for installing Ez on Linux
# This script has some pre-requisites of its own too:
# 
# 1. Need to have WSL 2 + Ubuntu installed if running locally on Windows
# 2. Need to have Docker Desktop installed with WSL 2 integration turned on

# Warm up by updating system
sudo apt update && sudo apt upgrade -y

# Install git, curl
# sudo apt install git curl keychain -y
sudo apt install git curl -y

# Install Python via miniconda silently
cd ~/ && mkdir ~/tmp 
cd ~/tmp
curl https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh \
  --remote-name
bash Miniconda3-latest-Linux-x86_64.sh -b

# Configure conda into current bash
echo 'eval "$(~/miniconda3/bin/conda shell.bash hook)"' >> ~/.bashrc

# Do the same thing but within this session
eval "$(~/miniconda3/bin/conda shell.bash hook)"

# Generate SSH keys for accessing Azure and GitHub
# You will need to enter passphrases for these
# TODO: remove the -q -N flags later once we figure out passphrase management
ssh-keygen -t ed25519 -C "Github key" -f ~/.ssh/id_rsa_github -q -N ""
ssh-keygen -t rsa -b 4096 -C "Azure key" -f ~/.ssh/id_rsa_azure -q -N ""

# Map the keys to the appropriate domains
cat > ~/.ssh/config << EOF
Host github.com
  AddKeysToAgent yes
  IdentityFile ~/.ssh/id_rsa_github

Host *.cloudapp.azure.com
  AddKeysToAgent yes
  IdentityFile ~/.ssh/id_rsa_azure
EOF

# Install GitHub CLI
curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
 | sudo gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
 | sudo tee /etc/apt/sources.list.d/github-cli.list > /dev/null
sudo apt update
sudo apt install gh

# Install the Azure CLI
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

# Log into GitHub
gh auth login

# Log into Azure
az login

# Install ez
mkdir ~/src 
cd ~/src
git clone https://github.com/jflam/ez
cd ez/src 
python setup.py install

# Initialize ez
ez init

# Reload bash environment
exec bash