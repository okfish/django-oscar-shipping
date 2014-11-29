#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys

import oscar_shipping

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

version = oscar_shipping.__version__

if sys.argv[-1] == 'publish':
    os.system('python setup.py sdist upload')
    print("You probably want to also tag the version now:")
    print("  git tag -a %s -m 'version %s'" % (version, version))
    print("  git push --tags")
    sys.exit()

readme = open('README.rst').read()
history = open('HISTORY.rst').read().replace('.. :changelog:', '')

setup(
    name='django-oscar-shipping',
    version=version,
    description="""Shipping app for Oscar Ecommerce projects. Supports APIs for some post services and companies, such as EMS Russian Post, PEC etc.""",
    long_description=readme + '\n\n' + history,
    author='Oleg Rybkin',
    author_email='okfish@yandex.ru',
    url='https://github.com/okfish/django-oscar-shipping',
    packages=[
        'oscar_shipping',
    ],
    include_package_data=True,
    install_requires=[
    ],
    license="BSD",
    zip_safe=False,
    keywords='django-oscar-shipping',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Framework :: Django',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 2.6',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
    ],
)
