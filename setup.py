import ast
from io import open
import re
from setuptools import setup, find_packages

'''
How to build and upload this package to PyPi
    python setup.py sdist
    python setup.py bdist_wheel --universal
    twine upload dist/*
'''

_version_re = re.compile(r"__version__\s+=\s+(.*)")

with open("farm/__init__.py", "rb") as f:
    version = str(
        ast.literal_eval(_version_re.search(f.read().decode("utf-8")).group(1))
    )


def open_file(filename):
    """Open and read the file *filename*."""
    with open(filename) as reader:
        return reader.read()


readme = open_file("README.md")

setup(
    name='robotslacker-farm',
    version=version,
    description='Regress test tool',
    long_description=readme,
    keywords='test regress',
    platforms='any',
    install_requires=['click', 'robotframework'],

    author='RobotSlacker',
    author_email='184902652@qq.com',
    url='https://github.com/robotslacker/farm',

    packages=find_packages(),
    package_data={"farm": ["farm", ]},

    entry_points={
        "console_scripts": ["farm = farm.main:farm"],
        "distutils.commands": ["lint = tasks:lint", "test = tasks:test"],
    },
)
