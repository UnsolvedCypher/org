from google.appengine.ext import ndb

from src.models.wca.base import BaseModel
from src.models.wca.continent import Continent
from src.models.wca.export import WcaExport

class Country(BaseModel):
  name = ndb.StringProperty()
  continent = ndb.KeyProperty(kind=Continent)
  iso2 = ndb.StringProperty()

  export = ndb.KeyProperty(kind=WcaExport)

  def ParseFromDict(self, row):
    self.name = row['name']
    self.continent = ndb.Key(Continent, row['continentId'])
    self.iso2 = row['iso2']

  @staticmethod
  def ColumnsUsed():
    return ['name', 'continentId', 'iso2']
