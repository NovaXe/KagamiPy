from setuptools import setup, find_packages

with open('requirements.txt') as f:
    requirements = f.read().splitlines()


setup(
    name="kagami",
    packages=find_packages(),
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'start-kagami=kagami.main:main'
        ]
    }
)