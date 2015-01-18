from django.contrib import admin

from oscar.core.loading import get_model

ShippingCompany = get_model('shipping', 'ShippingCompany')
ShippingContainer = get_model('shipping', 'ShippingContainer')

    
class ShippingCompanyAdmin(admin.ModelAdmin):
    filter_horizontal = ('countries', 'containers')
    list_display = ('name', 'description', 'status', 'is_active')


class ShippingContainerAdmin(admin.ModelAdmin):
    list_display = ('name', 'height', 'width', 'lenght', 'max_load')
    


admin.site.register(ShippingCompany, ShippingCompanyAdmin)
admin.site.register(ShippingContainer, ShippingContainerAdmin)