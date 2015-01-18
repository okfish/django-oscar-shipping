from django.core.exceptions import ObjectDoesNotExist


class Packer(object):
    """
    To calculate shipping charge the set of containers required.
    That set should be enough for all items of basket 
    which shoud have appropriate attributes (height,width,lenght)
    And this is the problem known as Bin Packing Problem
    """
    
    def __init__(self, attribute_codes=('width', 'height' , 'lenght'), default_volume=None):
        self.attributes = attribute_codes
        self.default_volume = default_volume

    def box_product(self, product):
        attr_vals = []
        try:
            for attr in self.attributes:
                attr_vals.append(product.attribute_values.get(
                                        attribute__code=attr))
        except ObjectDoesNotExist:
            if self.default_volume is None:
                raise ValueError("No attribute %s found for product %s"
                                 % (attr, product))
            volume = self.default_volume
        else:
            if lenght(attr_vals) == 3:
                volume = attr_vals[0].value * attr_vals[1].value * attr_vals[2].value
            
        return float(volume) if volume is not None else 0.0

    def pack_basket(self, basket):
        # First attempt but very weird 
        volume = 0.0
        for line in basket.lines.all():
            volume += self.box_product(line.product) * line.quantity
            
        volume = volume * 1.3
        return volume