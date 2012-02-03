jQuery.fn.dialog = function(opts){
  
  // opts.bg_color, opts.contents, opts.auto_trigger, opts.hide_button, opts.onShow
  
  var button = $(this);
  
  
  button.click(function(){
    
    $('body').append('<div id="overlay"></div><div id="dialog_box"><a id="close" href="#">Close</a></div>');
    
    $('#overlay').css({
      position: 'absolute',
      left: '0',
      top: '0', 
      width: '100%',
      height: $(document).height(),
      background: opts.bg_color,
      opacity: 0.4,
      zIndex: 1000
    })
    
    $('#dialog_box').css({
      position: 'absolute',
      width: '50%',
      minHeight: '100px',
      left: '25%',
      background: '#FFF',
      opacity: 1,
      zIndex: 1001
    }).append($(opts.contents));
    
    $('#close').click(function(){
      $(opts.contents).appendTo('body').hide();
      $('#overlay').detach();
      $('#dialog_box').detach();
      return false;
    })
    
    $(opts.contents).show();
    
    $(document).scroll(function(){
      $('#dialog_box').offset({
        top: $(document).scrollTop() + ($(window).height()*0.5) - ($('#dialog_box').height()*0.5) 
      })
    }).trigger('scroll');    
    return false;
  })
  
  $(opts.contents).hide();
  
  if(opts.auto_trigger){
    button.trigger('click');
  }
  
  if(opts.hide_button){
    button.hide();
  }
  
  if(opts.onShow){
    opts.onShow(button);
  }
  else{
    return button;
  }
  
}