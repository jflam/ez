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
    install_requires=['Click', 'rich', 'fabric'],
    entry_points='''
        [console_scripts]
        ez=ez:ez
    ''',
)