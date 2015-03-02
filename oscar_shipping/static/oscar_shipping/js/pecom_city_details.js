$(document).ready(function() {
	function remove_form(){
		var details_div = $('.shipping-details-form');
		if (details_div) {
			details_div.fadeOut(1000);
			details_div.remove();	
		}
	}
    // bind classes select2 single-city-selector' onchange event 
    $('.city-selector, .single-city-selector').on('change', function(){
			remove_form();
			$.ajax({ 
				    type: $(this).attr('method'), 
				    url: $(this).data('lookup-url'),
				    beforeSend: function() { 
				    	$(this).after('<div id="wait">calulating...</div>');
				    },
        			complete: function() { 
        				$('#wait').remove();
        			}, 
				    data: {'from': $(this).closest('form').find("input[name='senderCityId']:hidden:first").val(), 
				            'to': $(this).val()}, 
				    context: this,
				    success: function(data, status) {
				        $(this).after(data);
				    }
			});
			return false;            		
    }); 
            	
            //$(document).on('change', '.city-selector', function(){
			//	remove_form(); 
			//	do_ajax();
			//	return false;
			//});		
}); 

