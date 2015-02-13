from django.conf.urls import patterns, url
from django.views.decorators.cache import cache_page

from oscar.core.application import Application

from oscar_shipping import views


class ShippingApplication(Application):
    name = 'shipping'
    pecom_city_lookup_view = views.PecomCityLookupView

    
    def get_urls(self):
        urlpatterns = super(ShippingApplication, self).get_urls()
        urlpatterns += patterns('',
            url(r'^city-lookup/(?P<slug>[\w-]+)/$', cache_page(60*10)(self.pecom_city_lookup_view.as_view()),
                name='city-lookup'),
        )
        return self.post_process_urls(urlpatterns)


application = ShippingApplication()