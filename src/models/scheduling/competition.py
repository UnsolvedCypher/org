from google.appengine.ext import ndb

from src.models.refresh_token import RefreshToken
from src.models.wca.competition import Competition
from src import timezones

class ScheduleCompetition(ndb.Model):
  wca_competition = ndb.KeyProperty(kind=Competition)
  timezone = ndb.StringProperty()
  name = ndb.StringProperty()
  refresh_token = ndb.KeyProperty(kind=RefreshToken)

  contact_email = ndb.StringProperty()
  staff_signup_deadline = ndb.DateTimeProperty()

  def GetStaffSignupDeadline(self):
    if not self.staff_signup_deadline:
      return None
    return timezones.ToLocalizedTime(self.staff_signup_deadline, self.timezone)
