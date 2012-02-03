$(function(){
  var positions = new Array();
  $('#content h3').each(function(key,value){ positions[key] = $(value).position().top + 80; }); 
  for(var i=0; i < positions.length; i++){
    $('#main').append('<div class="stripe"/>');
    $('.stripe:last').css('top', positions[i]);
  }
})