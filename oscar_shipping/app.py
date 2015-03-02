from django.conf.urls import patterns, url
from django.views.decorators.cache import cache_page

from oscar.core.application import Application

from . import views


class ShippingApplication(Application):
    name = 'shipping'
    city_lookup_view = views.PecomCityLookupView
    pecom_details_view = views.PecomDetailsView
    
    def get_urls(self):
        urlpatterns = super(ShippingApplication, self).get_urls()
        urlpatterns += patterns('',
            url(r'^city-lookup/(?P<slug>[\w-]+)/$', cache_page(60*10)(self.city_lookup_view.as_view()),
                name='city-lookup'),
        )
        urlpatterns += patterns('',
            url(r'^details/(?P<slug>[\w-]+)/$', cache_page(60*10)(self.pecom_details_view.as_view()),
                name='charge-details'),
        )
        return self.post_process_urls(urlpatterns)


application = ShippingApplication()