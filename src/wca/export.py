import collections
import csv
import logging

import cloudstorage as gcs
from google.appengine.api import app_identity
from google.appengine.ext import deferred
from google.appengine.ext import ndb

from src.post_import import mutations
from src.models.wca.competition import Competition
from src.models.wca.continent import Continent
from src.models.wca.country import Country
from src.models.wca.event import Event
from src.models.wca.export import WcaExport
from src.models.wca.export import set_latest_export
from src.models.wca.format import Format
from src.models.wca.person import Person
from src.models.wca.rank import RankAverage
from src.models.wca.rank import RankSingle
from src.models.wca.result import Result
from src.models.wca.round import RoundType


def fname(table, shard):
  return '/%s/export/%s.%d.tsv' % (app_identity.get_default_gcs_bucket_name(), table, shard)


def old_fname(table, shard):
  return '/%s/export/%s_old.%d.tsv' % (app_identity.get_default_gcs_bucket_name(), table, shard)


def process_file(table, object_type, shard, total_shards, queue, export_id):
  logging.info('Processing table %s shard %d/%d' % (table, shard, total_shards))
  filename = fname(table, shard)
  row_filter = object_type.Filter()

  with gcs.open(filename, 'r') as gcs_file:
    reader = csv.DictReader(gcs_file, delimiter='\t')
    id_to_dict = collections.defaultdict(dict)
    for row in reader:
      if not row_filter(row):
        continue
      id_to_dict[object_type.GetId(row)] = row
    logging.info('Finished reading file.  Found %d entries' % len(id_to_dict))

    keys_to_delete = []

    try:
      # Check for rows that have not changed, so we don't need to rewrite them.
      with gcs.open(old_fname(table, shard), 'r') as old_file:
        columns_to_diff = object_type.ColumnsUsed()
        old_reader = csv.DictReader(old_file, delimiter='\t')
        for old_row in old_reader:
          row_id = object_type.GetId(old_row)
          if row_id in id_to_dict:
            new_row = id_to_dict[row_id]
            is_diff = False
            for col in columns_to_diff:
              if new_row[col] != old_row[col]:
                is_diff = True
            if not is_diff:
              del id_to_dict[row_id]
          else:
            # This entry has been deleted, so we delete it.
            keys_to_delete.append(ndb.Key(object_type, row_id))
    except gcs.NotFoundError:
      # This is fine, it just means we can't diff the new file against the old one.
      pass

    logging.info('Finished diffing.  Inserting %d entries.' % len(id_to_dict))
    logging.info('Deleting %d entries.' % len(keys_to_delete))
    if keys_to_delete:
      logging.info('Deleting: %s' % (', '.join(key.id() for key in keys_to_delete[:10])))

    ndb.delete_multi(keys_to_delete)

    object_ids = id_to_dict.keys()
    keys = [ndb.Key(object_type, object_id) for object_id in object_ids]
    query_result = ndb.get_multi_async(keys)
    objects_to_put = []
    objects_to_get = []
    for object_id, query_result in zip(object_ids, query_result):
      obj = query_result.get_result() or object_type(id=object_id)
      obj.ParseFromDict(id_to_dict[object_id])
      objects_to_put.append(obj)
      # For some objects, fetch other entities in batch to save time.  This will
      # store them in memcache, which is faster than reading from the datastore.
      objects_to_get.extend(obj.ObjectsToGet())
    logging.info('Starting write')
    ndb.get_multi(objects_to_get)
    ndb.put_multi(objects_to_put)
    logging.info('Finished write')

  # We're done with this shard, make it the new finished table.
  # But, we can't just copy the file, we need to filter out rows that we didn't consider.
  with gcs.open(filename, 'r') as gcs_file:
    reader = csv.DictReader(gcs_file, delimiter='\t')
    fields_to_write = object_type.ColumnsUsed()
    if 'id' in reader.fieldnames:
      fields_to_write.append('id')
    with gcs.open(old_fname(table, shard), 'w') as old_file:
      writer = csv.DictWriter(old_file, delimiter='\t', fieldnames=fields_to_write)
      writer.writeheader()
      for row in reader:
        if row_filter(row):
          writer.writerow({k: v for k, v in row.iteritems() if k in fields_to_write})

  if shard + 1 < total_shards:
    deferred.defer(process_file, table, object_type, shard + 1, total_shards, queue, export_id)
  elif queue:
    new_table, new_object_type, new_shards = queue.pop(0)
    deferred.defer(process_file, new_table, new_object_type, 0, new_shards, queue, export_id)
  else:
    export_key = ndb.Key(WcaExport, export_id)
    old_export = set_latest_export(export_key)
    if old_export:
      old_export.key.delete()
    mutations.DoMutations()
  

def get_tables():
  return [('Continents', Continent, 1),
          ('Countries', Country, 1),
          ('Events', Event, 1),
          ('Formats', Format, 1),
          ('RoundTypes', RoundType, 1),
          ('Persons', Person, 6),
          ('RanksSingle', RankSingle, 20),
          ('RanksAverage', RankAverage, 20),
          ('Competitions', Competition, 1),
          ('Results', Result, 40),
         ]


def process_export(export_id):
  queue = get_tables()
  table, object_type, shards = queue.pop(0)
  deferred.defer(process_file, table, object_type, 0, shards, queue, export_id)
