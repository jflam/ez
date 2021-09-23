from setuptools import setup

setup(
    name='ez',
    version='0.1',
    py_modules=['ez', 
                'workspace_commands', 
                'env_commands', 
                'compute_commands', 
                'constants',
                'azutil'],
    install_requires=['Click', 'rich'],
    entry_points='''
        [console_scripts]
        ez=ez:ez
    ''',
)