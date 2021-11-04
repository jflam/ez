import os 

from click.testing import CliRunner
from ez import ez

# Set current working dir
os.chdir(os.path.expanduser("~/src/"))
current_dir = os.getcwd()
runner = CliRunner()
result = runner.invoke(ez, ['--debug', 'env', 'go', '-g', 
    'git@github.com:jflam/riiid-acp-pub'])