=============================
django-oscar-shipping
=============================

.. image:: https://travis-ci.org/okfish/django-oscar-shipping.png?branch=master
    :target: https://travis-ci.org/okfish/django-oscar-shipping

.. image:: https://coveralls.io/repos/okfish/django-oscar-shipping/badge.png?branch=master
    :target: https://coveralls.io/r/okfish/django-oscar-shipping?branch=master


API-based shipping app for the Oscar Ecommerce project. 
Supports APIs for some post services and companies, such as EMS Russian Post, PEC(Pervaya Ekspeditsionnaya), DHL etc.



Documentation
-------------

The full documentation will be available soon at https://django-oscar-shipping.readthedocs.org.

Quickstart
----------

Install django-oscar-shipping::

    pip install -e git+https://github.com/okfish/django-oscar-shipping/django-oscar-shipping.git#egg=dajngo-oscar-shipping

then add 'oscar_shipping' to the INSTALLED_APPS. From now you can override Oscar's shipping app
using oscar_shipping within your project

	e.g.::

	#apps/shipping/methods.py

	from oscar_shipping.methods import SelfPickup

	#apps/shipping/repository.py
	
	from oscar.apps.shipping import repository

	from .methods import * 
	from . import models

	# Override shipping repository in order to provide our own
	# custom methods
	class Repository(repository.Repository):
	    
	    def get_available_shipping_methods(self, basket, user=None, shipping_addr=None, request=None, **kwargs):
	        methods = [SelfPickup(),]
	        #...
	        methods.extend(list(models.ShippingCompany.objects.all().filter(is_active=True)))
	        return methods
	
	#apps/shipping/models.py
	
	from oscar.apps.shipping import abstract_models
	from oscar_shipping.models import * 
	
	#... your methods goes here
	
	from oscar.apps.shipping.models import *

	#apps/shipping/admin.py
	
	from oscar_shipping.admin import *
	from oscar.apps.shipping.admin import *

Dependencies
------------

Install pecomsdk if you would like enable pecom shipping facade::

	pip install -e git+https://github.com/okfish/pecomsdk.git#egg=pecomsdk

Features
--------
* SelfPickup() shipping method. Simply inherited from methods.Free and renamed.
* Easy customisable facades for different APIs
* Facade to the Russian Post EMS
* Facade to the PEC (Pervaya Ekspeditsionnaya Kompania) using pecomsdk package
* Models for shipping companies and containers for packing and shipping cost calculation 
* Packer module assumes Bin Packing Problem can be solved in different ways: using own algorithms or via external APIs

* TODO
