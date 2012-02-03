from google.appengine.api import mail
from google.appengine.api import taskqueue
from google.appengine.api import images
from google.appengine.ext import webapp, db
from google.appengine.ext.webapp import util, template
from gaesessions import get_current_session
from django.template.defaultfilters import slugify

import logging
import datetime
import random
import sys
sys.path.insert(0, 'libs/tweepy.zip')
from tweepy import *

import keys

#helpers
from django.utils.html import escape

# Helper
def rreplace(s, old, new, occurrence):
  li = s.rsplit(old, occurrence)
  return new.join(li)

def sanitize(string):
  return escape(string)

#models
class AccessRequest(db.Model):
  request_token_key    = db.StringProperty(required=True)
  request_token_secret = db.StringProperty(required=True)

class User(db.Model):
  access_token_key    = db.StringProperty(required=False)
  access_token_secret = db.StringProperty(required=False)
  nickname            = db.StringProperty(required=False)
  email               = db.StringProperty(required=False)
  twitter_id          = db.StringProperty(required=False)
  created             = db.DateTimeProperty(auto_now_add=True)
  admin               = db.BooleanProperty(default=False)

  @staticmethod
  def get_or_create_user_by_twitter_id(id):
    user_query = User.all().filter("twitter_id", id).fetch(1)
    if len(user_query) == 0:
      user = User(twitter_id=id)
      user.put()
    else:
      user = user_query[0]
    return user

class StartupInfo(db.Model):
  logo        = db.BlobProperty()
  logo_raw    = db.BlobProperty()
  logo_small  = db.BlobProperty()
  name        = db.StringProperty(required=True)
  description = db.StringProperty(default="")
  overview    = db.TextProperty()
  created     = db.DateTimeProperty(auto_now_add=True)
  founded_at  = db.DateTimeProperty()
  ended_at    = db.DateTimeProperty()
  homepage    = db.StringProperty(default="")
  blog        = db.StringProperty(default="")
  email       = db.StringProperty(default="")
  category    = db.StringProperty(default="")
  author      = db.ReferenceProperty(User,collection_name="edits")
  startup     = db.ReferenceProperty()

class Startup(db.Model):
  created   = db.DateTimeProperty(auto_now_add=True)
  last_info = db.ReferenceProperty(StartupInfo)  
  slug      = db.StringProperty()

  def active(self):
    return not self.last_info.ended_at

class Founder(db.Model):
  created = db.DateTimeProperty(auto_now_add=True)
  twitter = db.StringProperty()
  profile_image = db.StringProperty()
  profile_image_small = db.StringProperty()
  name = db.StringProperty(default="")
  city = db.StringProperty(default="")
  country = db.StringProperty(default="")
  website = db.StringProperty(default="")
  linked_in = db.StringProperty(default="")
  github = db.StringProperty(default="")
  facebook = db.StringProperty(default="")

  @staticmethod
  def get_or_create(twitter):
    twitter = twitter.lower().replace(' ','')
    founder_query = Founder.all().filter("twitter",twitter).fetch(1)
    if len(founder_query) == 0:
      founder = Founder(twitter=twitter)
      founder.put()
      taskqueue.add(url='/tasks/get_founder_info_from_twitter', params={'twitter': twitter})
    else:
      founder = founder_query[0]
    return founder
 
class FounderStartup(db.Model):
  created = db.DateTimeProperty(auto_now_add=True)
  founder = db.ReferenceProperty(Founder, collection_name="startups")
  startup = db.ReferenceProperty(Startup, collection_name="founders")
  active  = db.BooleanProperty()

class ChangeSubscription(db.Model):
  created = db.DateTimeProperty(auto_now_add=True)
  user    = db.ReferenceProperty(User, collection_name="subscriptions")
  startup = db.ReferenceProperty(Startup, collection_name="subscriptors")

#controllers
class MainHandler(webapp.RequestHandler):
  def get(self):
    session = get_current_session()
    if session.has_key('user'):
      logged_in_user = session['user']

    self.response.out.write(template.render('templates/main.html', locals()))

#controllers
class PleaseLoginHandler(webapp.RequestHandler):
  def get(self):
    session = get_current_session()
    if session.has_key('user'):
      self.redirect('/')
    else:
      self.redirect('/login')

class LoginHandler(webapp.RequestHandler):
  def get(self):
    session = get_current_session()
    if session.is_active():
      session.terminate()
    session.regenerate_id()
    auth = OAuthHandler(keys.TWITTER_CONSUMER, keys.TWITTER_SECRET)
    auth_url = auth.get_authorization_url()
    AccessRequest(request_token_key = auth.request_token.key,
                  request_token_secret = auth.request_token.secret).put()
    self.redirect(auth_url)

class LogoutHandler(webapp.RequestHandler):
  def get(self):
    session = get_current_session()
    if session.is_active():
      session.terminate()
    session.regenerate_id()
    self.redirect('/')

class OAuthCallbackHandler(webapp.RequestHandler):
  def get(self):
    oauth_token = self.request.get("oauth_token")
    access_requests = AccessRequest.all().filter("request_token_key", oauth_token).fetch(1)
    if len(access_requests) > 0:
      access_request = access_requests[0]
      auth = OAuthHandler(keys.TWITTER_CONSUMER, keys.TWITTER_SECRET)
      auth.set_request_token(access_request.request_token_key, access_request.request_token_secret)
      try:
        auth.get_access_token(self.request.get("oauth_verifier"))

        api = API(auth)

        api_user = api.verify_credentials()
        user = User.get_or_create_user_by_twitter_id(api_user.id_str)
        user.access_token_secret = auth.access_token.secret
        user.access_token_key = auth.access_token.key
        user.nickname = api_user.screen_name
        user.put()

        session = get_current_session()
        session['user'] = user
        self.redirect('/')
      except TweepError:
        self.response.out.write(template.render('templates/oauth_error.html', locals()))
    else:
      # we don't have an Access Request with that Token, this is probably a developer
      self.response.out.write(template.render('templates/oauth_error.html', locals()))
      return

#startup_handler
class StartupNewHandler(webapp.RequestHandler):
  def get(self):
    session = get_current_session()
    if not session.has_key('user'):
      self.redirect('/registrate')
    else:
      logged_in_user = session['user']
      self.response.out.write(template.render('templates/startup_new.html', locals()))

  def post(self):
    session = get_current_session()
    if not session.has_key('user'):
      self.redirect('/registrate')
    else:
      logged_in_user = session['user']
      name = sanitize(self.request.get("name"))
      startup = Startup()
      startup.put()

      startup_info = StartupInfo(name=name, 
        description=sanitize(self.request.get("description")), 
        overview=sanitize(self.request.get("overview")), 
        homepage=sanitize(self.request.get("homepage")), 
        blog=sanitize(self.request.get("blog")), 
        email=sanitize(self.request.get("email")), 
        category=sanitize(self.request.get("category")), 
        startup=startup, 
        author=logged_in_user)
      try:
        parsed_date = datetime.datetime.strptime(self.request.get("founded_at"),"%m/%Y")
        startup_info.founded_at = parsed_date
      except ValueError:
        logging.info("Wrong date")
      try:
        parsed_date = datetime.datetime.strptime(self.request.get("ended_at"),"%m/%Y")
        startup_info.ended_at = parsed_date
      except ValueError:
        logging.info("Wrong date")




      if self.request.get("img"):
        startup_info.logo_raw = db.Blob(self.request.get("img"))
        startup_info.logo = db.Blob(images.resize(self.request.get("img"), 73, 73))
        startup_info.logo_small  = db.Blob(images.resize(self.request.get("img"), 48, 48))
      startup_info.put()
    
      startup.last_info = startup_info
      startup.slug = slugify(name)
      startup.put()

      self.redirect('/startup/' + startup.slug)

class StartupLogoImageHandler (webapp.RequestHandler):
  def get(self,key):
    startup_info = db.get(key)
    if startup_info.logo:
      self.response.headers['Content-Type'] = "image/png"
      if self.request.get("size") == 'small':
        self.response.out.write(startup_info.logo_small)
      elif self.request.get("size") == 'raw':
        self.response.out.write(startup_info.logo_raw)
      else:
        self.response.out.write(startup_info.logo)
    else:
      self.response.out.write("No image")

class StartupEditHandler(webapp.RequestHandler):
  def get(self,slug):
    session = get_current_session()
    if not session.has_key('user'):
      self.redirect('/registrate')
    else:
      logged_in_user = session['user']
      startup = Startup.all().filter("slug",slug).fetch(1)
      if len(startup) > 0:
        startup = startup[0]
        edit = True
        self.response.out.write(template.render('templates/startup_new.html', locals()))
      else:
        self.redirect('/')

  def post(self,slug):
    session = get_current_session()
    if not session.has_key('user'):
      self.redirect('/registrate')
    else:
      logged_in_user = session['user']
      startup = Startup.all().filter("slug",slug).fetch(1)
      if len(startup) > 0:
        startup = startup[0]
        name = self.request.get("name")

        startup_info = StartupInfo(name=name, 
          description=sanitize(self.request.get("description")), 
          overview=sanitize(self.request.get("overview")), 
          homepage=sanitize(self.request.get("homepage")), 
          blog=sanitize(self.request.get("blog")), 
          email=sanitize(self.request.get("email")), 
          category=sanitize(self.request.get("category")), 
          startup=startup, 
          author=logged_in_user)
        try:
          parsed_date = datetime.datetime.strptime(self.request.get("founded_at"),"%m/%Y")
          startup_info.founded_at = parsed_date
        except ValueError:
          logging.info("Wrong date")
        try:
          parsed_date = datetime.datetime.strptime(self.request.get("ended_at"),"%m/%Y")
          startup_info.ended_at = parsed_date
        except ValueError:
          logging.info("Wrong date")


        if self.request.get("img"):
          startup_info.logo_raw = db.Blob(self.request.get("img"))
          startup_info.logo = db.Blob(images.resize(self.request.get("img"), 73, 73))
          startup_info.logo_small  = db.Blob(images.resize(self.request.get("img"), 48, 48))
        elif startup.last_info.logo:
          startup_info.logo = startup.last_info.logo
        startup_info.put()
    
        startup.last_info = startup_info
        startup.put()

        taskqueue.add(url='/tasks/send_emails_on_startup_change', params={'startup_key': str(startup.key())})
        self.redirect('/startup/' + startup.slug)
      else:
        self.redirect('/')

class StartupVersionHandler(webapp.RequestHandler):
  def get(self,startup_slug,version):
    session = get_current_session()
    if session.has_key('user'):
      logged_in_user = session['user']
    
    startup = Startup.all().filter("slug",startup_slug).fetch(1)
    if len(startup):    
      startup = startup[0]
      if session.has_key('user'):
        subscribed = len(ChangeSubscription.all().filter("startup",startup).filter("user",logged_in_user).fetch(1)) > 0
      title = startup.last_info.name
      info = db.get(version)
      startup.last_info = info
      self.response.out.write(template.render('templates/startup.html', locals()))
    else:
      self.redirect('/')

class StartupHandler(webapp.RequestHandler):
  def get(self,startup_slug):
    session = get_current_session()
    if session.has_key('user'):
      logged_in_user = session['user']
    
    # TODO : Get startup by its startup_name
    startup = Startup.all().filter("slug",startup_slug).fetch(1)
    if len(startup):    
      startup = startup[0]
      if session.has_key('user'):
        subscribed = len(ChangeSubscription.all().filter("startup",startup).filter("user",logged_in_user).fetch(1)) > 0
        is_founder = len([f for f in startup.founders if f.founder.twitter.lower() == logged_in_user.nickname.lower()]) > 0
      title = startup.last_info.name
      self.response.out.write(template.render('templates/startup.html', locals()))
    else:
      self.redirect('/')

class StartupVersionsHandler(webapp.RequestHandler):
  def get(self,startup_slug):
    session = get_current_session()
    if session.has_key('user'):
      logged_in_user = session['user']
    
    # TODO : Get startup by its startup_name
    startup = Startup.all().filter("slug",startup_slug).fetch(1)
    if len(startup):    
      startup = startup[0]
      startup_infos = StartupInfo.all().filter("startup",startup).order('-created').fetch(1000)
      self.response.out.write(template.render('templates/startup_versions.html', locals()))
    else:
      self.redirect('/')

  def post(self,startup_slug):
    session = get_current_session()
    if session.has_key('user'):
      logged_in_user = session['user']
      startup = Startup.all().filter("slug",startup_slug).fetch(1)
      if len(startup):    
        startup = startup[0]
        startup_info = db.get(self.request.get("version"))
        startup.last_info = startup_info
        startup.put()
        self.response.out.write(template.render('templates/startup_versions.html', locals()))
      else:
        self.redirect('/')
    else:
      self.redirect('/')
    
    # find the version
    # find the startup
    # poner la nueva version
  
    self.redirect('/startup/' + startup_slug)

#startup_handler
class StartupAddFounderHandler(webapp.RequestHandler):
  def get(self,slug):
    session = get_current_session()
    if not session.has_key('user'):
      self.redirect('/registrate')
    else:
      logged_in_user = session['user']
      self.response.out.write(template.render('templates/startup_add_founder.html', locals()))

  def post(self,slug):
    session = get_current_session()
    if not session.has_key('user'):
      self.redirect('/registrate')
    else:
      logged_in_user = session['user']
      startup = Startup.all().filter("slug",slug).fetch(1)
      if len(startup) > 0:
        startup = startup[0]
        twitter = self.request.get("twitter")
        
        founder = Founder.get_or_create(twitter)
        founder_startup = FounderStartup(founder=founder, startup=startup)
        founder_startup.put()
 
        self.redirect('/startup/' + startup.slug)
      else:
        self.redirect('/')

class FounderHandler(webapp.RequestHandler):
  def get(self,twitter):
    session = get_current_session()
    if session.has_key('user'):
      logged_in_user = session['user']
      can_edit = logged_in_user.nickname == twitter or logged_in_user.admin
 
    founder = Founder.all().filter("twitter",twitter).fetch(1)
    if len(founder):    
      founder = founder[0]
      startups = FounderStartup.all().filter("founder",founder).fetch(1000)
      for startup in startups:
        startup.startup.founders_filter = [x for x in startup.startup.founders if x.founder.twitter != twitter]
      if founder.name:
        title = founder.name
      else:
        title = founder.twitter
      self.response.out.write(template.render('templates/founder.html', locals()))
    else:
      self.redirect('/')

class FounderEditHandler(webapp.RequestHandler):
  def get(self,twitter):
    session = get_current_session()
    if session.has_key('user'):
      logged_in_user = session['user']
      can_edit = logged_in_user.nickname == twitter or logged_in_user.admin
      if can_edit:
        founder = Founder.all().filter("twitter",twitter).fetch(1)
        if len(founder):    
          founder = founder[0]
          self.response.out.write(template.render('templates/founder_edit.html', locals()))
        else:
          self.redirect('/')
      else:
        self.redirect('/')
    else:
      self.redirect('/')

  def post(self,twitter):
    session = get_current_session()
    if session.has_key('user'):
      logged_in_user = session['user']
      can_edit = logged_in_user.nickname == twitter or logged_in_user.admin
      if can_edit:
        founder = Founder.all().filter("twitter",twitter).fetch(1)
        if len(founder):    
          founder = founder[0]
          founder.name = sanitize(self.request.get("name"))
          founder.city = sanitize(self.request.get("city"))
          founder.country = sanitize(self.request.get("country"))
          founder.website = sanitize(self.request.get("website"))
          founder.linked_in = sanitize(self.request.get("linked_in"))
          founder.github = sanitize(self.request.get("github"))
          founder.facebook = sanitize(self.request.get("facebook"))
          founder.put()
          self.redirect('/founder/' + twitter)
        else:
          self.redirect('/')
      else:
        self.redirect('/')
    else:
      self.redirect('/')

class FoundersHandler(webapp.RequestHandler):
  def get(self):
    session = get_current_session()
    if session.has_key('user'):
      logged_in_user = session['user']
    founders = Founder.all().order('name').fetch(1000)
    self.response.out.write(template.render('templates/founders.html', locals()))

class StartupsHandler(webapp.RequestHandler):
  def get(self):
    session = get_current_session()
    if session.has_key('user'):
      logged_in_user = session['user']
    startups = Startup.all().order('slug').fetch(1000)
    self.response.out.write(template.render('templates/startups.html', locals()))

class UnsubscribeHandler(webapp.RequestHandler):
  def post(self):
    session = get_current_session()
    if session.has_key('user'):
      logged_in_user = session['user']
      startup = db.get(self.request.get("startup_key")) 
      subscription = ChangeSubscription.all().filter("startup",startup).filter("user",logged_in_user).fetch(1)[0]
      subscription.delete()
      self.redirect('/startup/'+startup.slug)
    else:
      self.redirect('/')

class SubscribeHandler(webapp.RequestHandler):
  def post(self):
    session = get_current_session()
    if session.has_key('user'):
      logged_in_user = session['user']
      startup = db.get(self.request.get("startup_key")) 
      subscription = ChangeSubscription(user=logged_in_user,startup=startup) 
      subscription.put()
      self.redirect('/startup/'+startup.slug)
    else:
      self.redirect('/')

class AddEmailAndSubscribeHandler(webapp.RequestHandler):
  def post(self):
    session = get_current_session()
    if session.has_key('user'):
      logged_in_user = session['user']
      email = self.request.get("email")
      startup = db.get(self.request.get("startup_key")) 
      user = db.get(logged_in_user.key())
      user.email = email
      user.put()
      session['user'] = user
      subscription = ChangeSubscription(user=logged_in_user,startup=startup) 
      subscription.put()
      self.redirect('/startup/'+startup.slug)
       
    else:
      self.redirect('/')

#tasks
class TaskGetFounderInfoHandler(webapp.RequestHandler):
  def post(self):
    founder = Founder.all().filter('twitter', self.request.get('twitter')).fetch(1)
    if len(founder):
      founder = founder[0]
      auth = OAuthHandler(keys.TWITTER_CONSUMER,keys.TWITTER_SECRET )
      #Here we set the credentials that we just verified and passed in.
      auth.set_access_token(keys.MAIN_ACCESS_TOKEN, keys.MAIN_ACCESS_SECRET)
      #Here we authorize with the Twitter API via OAuth
      twitterapi = API(auth)
      try:
        info = twitterapi.get_user(screen_name=self.request.get('twitter'))
        founder.name = info.name
        founder.city = info.location
        founder.website = info.url
        founder.profile_image = rreplace(info.profile_image_url, "_normal", "_bigger", 1)
        founder.profile_image_small = info.profile_image_url
        founder.put()
      except TweepError:
        logging.error("Failed to fetch info from:" + self.request.get('twitter'))
    else:
      logging.error("Failed to find founder:" + self.request.get('twitter'))

class TaskGetFounderImagesHandler(webapp.RequestHandler):
  def post(self):
    founder = Founder.all().filter('twitter', self.request.get('twitter')).fetch(1)
    founder = founder[0]
    auth = OAuthHandler(keys.TWITTER_CONSUMER,keys.TWITTER_SECRET )
    #Here we set the credentials that we just verified and passed in.
    auth.set_access_token(keys.MAIN_ACCESS_TOKEN, keys.MAIN_ACCESS_SECRET)
    #Here we authorize with the Twitter API via OAuth
    twitterapi = API(auth)
    info = twitterapi.get_user(screen_name=self.request.get('twitter'))
    founder.profile_image = rreplace(info.profile_image_url, "_normal", "_bigger", 1)
    founder.profile_image_small = info.profile_image_url
    founder.put()

class TaskSendSubscriptionEmailsHandler(webapp.RequestHandler):
  def post(self):
    startup = db.get(self.request.get("startup_key")) 
    subscribers = ChangeSubscription.all().filter("startup",startup).fetch(1000)
    host = self.request.url.replace(self.request.path,'',1)
    for s in subscribers:
      if not s.user.email:
        continue
      mail.send_mail(sender="Santiago Zavala <santiago1717@gmail.com>",
                     to= s.user.email,
                     subject="Se ha modificado " + startup.last_info.name + " en radar.mexican.vc",
                     html=template.render('templates/mail/startup_changed_email.html', locals()),
                     body=template.render('templates/mail/startup_changed_email_plain.html', locals()))

# Admin
class AdminReloadImagesFromTwitterHandler(webapp.RequestHandler):
  def get(self):
    self.response.out.write(template.render('templates/admin_reload_images_from_twitter.html', locals()))
    
  def post(self):
    founders = Founder.all().fetch(1000)
    for founder in founders: 
      taskqueue.add(url='/tasks/get_founder_images_from_twitter', params={'twitter': founder.twitter})
    self.redirect('/')

# Admin
class AdminRemoveWhitespaceFromFounderHandler(webapp.RequestHandler):
  def get(self):
    founders = Founder.all().fetch(1000)
    for founder in founders: 
      founder.twitter = founder.twitter.replace(' ','')
      founder.put()
    self.redirect('/')

# Admin
class AdminReloadInfoFromTwitterHandler(webapp.RequestHandler):
  def get(self):
    founders = Founder.all().fetch(1000)
    for founder in founders: 
      taskqueue.add(url='/tasks/get_founder_info_from_twitter', params={'twitter': founder.twitter})
    self.redirect('/')

# Admin
class DeleteEmailSubscriptionWithNoEmailInTheUserHandler(webapp.RequestHandler):
  def get(self):
    subs = ChangeSubscription.all().fetch(1000)
    for sub in subs: 
      if not sub.user.email:
        sub.delete()
    self.redirect('/')

def main():
  application = webapp.WSGIApplication([
    ('/', MainHandler),
    ('/login', LoginHandler),
    ('/logout', LogoutHandler),
    ('/registrate', PleaseLoginHandler),
    ('/add-email-and-subscribe', AddEmailAndSubscribeHandler),
    ('/subscribe', SubscribeHandler),
    ('/unsubscribe', UnsubscribeHandler),
    ('/oauth_callback', OAuthCallbackHandler),
    ('/startups', StartupsHandler),
    ('/startup/nuevo', StartupNewHandler),
    ('/startup/edit/(.+)', StartupEditHandler),
    ('/startup/historial/(.+)', StartupVersionsHandler),
    ('/startup/add/founder/(.+)', StartupAddFounderHandler),
    ('/startup_logo/(.+)', StartupLogoImageHandler),
    ('/startup/(.+)/(.+)', StartupVersionHandler),
    ('/startup/(.+)', StartupHandler),
    ('/founders', FoundersHandler),
    ('/founder/edit/(.+)', FounderEditHandler),
    ('/founder/(.+)', FounderHandler),
    ('/tasks/get_founder_info_from_twitter',TaskGetFounderInfoHandler),
    ('/tasks/get_founder_images_from_twitter',TaskGetFounderImagesHandler),
    ('/tasks/send_emails_on_startup_change',TaskSendSubscriptionEmailsHandler),
    ('/admin/reload_images_from_twitter',AdminReloadImagesFromTwitterHandler),
    ('/admin/reload_info_from_twitter',AdminReloadInfoFromTwitterHandler),
    ('/admin/remove_whitespace_from_founder_twitter',AdminRemoveWhitespaceFromFounderHandler),
    ('/admin/delete_email_subscriptions_with_no_email_in_the_user',DeleteEmailSubscriptionWithNoEmailInTheUserHandler),
  ],debug=True)
  util.run_wsgi_app(application)

if __name__ == '__main__':
    main()
