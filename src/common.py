import webapp2

class Common(object):
  def __init__(self, uri):
    self.uri_for = webapp2.uri_for
    self.uri = uri

  def uri_matches(self, uri):
    return self.uri.endswith(uri)

  def uri_matches_any(self, uri_list):
    for text, uri in uri_list:
      if self.uri_matches(uri):
        return True
    return False
