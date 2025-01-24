import setuptools

import netbucket
netbucket.server
version = {
    "year" :2025,
    "minor" :0,
    "patch" :1
}

setuptools.setup(
    name='netbucket',
    version=f"{version["year"]}.{version["minor"]}.{version["patch"]}",
    description='netbucket - network programming made simple',
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
    author='Izaiyah Stokes',
    author_email='d34d.dev@gmail.com',
    url='https://github.com/d34d0s/netbucket',
    packages=setuptools.find_packages(),
    install_requires=[
        "rich"
    ],
    entry_points={
        'console_scripts': [
            'cbuild = cbuild:main'
        ]
    },
    classifiers=[
        'Programming Language :: Python :: 3.12',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)