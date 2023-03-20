from setuptools import setup

with open("requirements.txt") as requirements:
    requirements = requirements.readlines()

setup(
    name='versations',
    version='0.1.0',
    py_modules=['main'],
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'versations = main:cli',
        ],
    },
)
