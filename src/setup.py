from setuptools import setup

setup(
    name='ez',
    version='0.1',
    py_modules=['ez', 
                'workspace_commands', 
                'env_commands', 
                'compute_commands', 
                'constants',
                'ez_state',
                'azutil'],
    install_requires=['Click', 'rich'],
    data_files=[('scripts', ['scripts/provision-gpu', 
                             'scripts/provision-gpu'])],
    entry_points='''
        [console_scripts]
        ez=ez:ez
    ''',
)