from click.testing import CliRunner
from ez import ez

runner = CliRunner()
result = runner.invoke(ez, ['--debug', 'vm', 'ssh'])
# result = runner.invoke(ez, ['--debug', 'env', 'run', '-n', 'pytorch-tutorials',
#                             '-g', 'https://github.com/jflam/pytorch-tutorials'])
print(result)