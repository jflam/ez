from setuptools import setup

setup(
    name='ez',
    version='0.1',
    py_modules=['ez'],
    install_requires=['Click'],
    entry_points='''
        [console_scripts]
        ez=ez:ez
    ''',
)