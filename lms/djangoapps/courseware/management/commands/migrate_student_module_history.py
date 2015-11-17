# pylint: disable=missing-docstring

from datetime import timedelta
from textwrap import dedent
import time
from optparse import make_option
from sys import exit
import traceback
import os, socket

from django.core.management.base import BaseCommand
from django.db import transaction

from courseware.models import StudentModuleHistory, StudentModuleHistoryArchive
from django.db import connections


class Command(BaseCommand):
    """
    Command to migrate data from StudentModuleHistoryArchive into StudentModuleHistory.
    Works from largest ID to smallest.
    """
    help = dedent(__doc__).strip()
    option_list = BaseCommand.option_list + (
        make_option('-w', '--window', type='int', default=1000, dest='window',
            help='how many rows to migrate per query [default: %default]'),
        #TODO: make option for naming locking table
    )

    def handle(self, *arguments, **options):
        #Make sure there's entries to migrate in StudentModuleHistoryArchive in this range
        try:
            StudentModuleHistoryArchive.objects.filter(id__lt=min_id_already_migrated, id__gte=min_id)[0]
        except:
            self.stdout.write("No entries found in StudentModuleHistoryArchive in range {}-{}, aborting migration.\n".format(
                min_id_already_migrated, min_id))
            return

        self._migrate(options['window'])


    @transaction.commit_manually
    def _migrate(self, window):
        self.stdout.write("Migrating StudentModuleHistoryArchive\n")
        start_time = time.time()


        archive_entries = (
            StudentModuleHistoryArchive.objects
            .select_related('student_module__student')
            .order_by('-id')
        )

        #REMOVE
        real_max_id = None
        count = 0
        current_max_id = max_id
        #END REMOVE

        old_min_id = None
        old_tick_timestamp = None
        
        while True:
            start_time = time.time()

            try:
                ids = self._acquire_lock(window)
            except:
                self.stderr.write("ERROR: Failed to acquire lock:\n")
                traceback.print_exc()
                continue    #or exit/raise?

            if not ids:
                self.stdout.write("Migration complete\n")
                break

            try:
                #Using __range instead of __in to avoid truncating if `window` is large
                #`_acquire_lock` operates on contiguous ranges, so it shouldn't be a problem
                entries = archive_entries.filter(pk__range=(ids[0], ids[-1]))

                new_entries = [StudentModuleHistory.from_archive(entry) for entry in entries]

                StudentModuleHistory.objects.bulk_create(new_entries)

                duration = time.time() - start_time

                self.stdout.write("Migrated StudentModuleHistoryArchive {}-{} to StudentModuleHistory\n".format(
                    new_entries[0].id, new_entries[-1].id))
                self.stdout.write("Migrated {} entries in {} seconds, {} entries per second\n".format(
                    count, duration, count / duration))
                
                #Fancy math for remaining prediction
                new_tick_timestamp = time.time()
                if old_min_id is not None:
                    num_just_migrated = new_entries[0].id - new_entries[-1].id
                    num_migrated_by_others = old_min_id - new_entries[0].id
                    total_migrated_this_cycle = num_just_migrated + num_migrated_by_others
                    cycles_remaining = new_entries[-1].id / total_migrated_this_cycle

                    time_since_last_tick = new_tick_timestamp - old_tick_timestamp

                    self.stdout.write("{} seconds remaining...\n".format(
                        timedelta(seconds=cycles_remaining / time_since_last_tick)))

                old_min_id = new_entries[0].id
                old_tick_timestamp = new_tick_timestamp

            except:
                transaction.rollback()

                try:
                    self._release_lock(ids)
                except:
                    self.stderr.write(("ERROR: Could not release lock! "
                        "The following IDs have NOT been migrated but are still locked: {}\n").format(
                        ','.join(map(str, ids))))
                    traceback.print_exc()   #or exit/raise?

                raise   #Do we really want it to exit here?

            else:
                transaction.commit()

                try:
                    self._release_lock_and_unqueue(ids)
                except:
                    self.stderr.write(("ERROR: Could not release lock! "
                        "The following IDs have been migrated but are still locked: {}\n").format(
                        ','.join(map(str, ids))))
                    traceback.print_exc()
                    #what now?


    def _acquire_lock(window):
        '''Acquire a lock on `window` newest CSMH entries and return a sorted list of their ids (highest first)'''
        #TODO: Fully instantiate list
        #TODO: put in separate transaction
        
        cursor = connections['student_module_history']
        
        cursor.execute("SELECT id FROM %s WHERE processor IS NULL ORDER BY id DESC LIMIT %d FOR UPDATE;",
            ['csmh_migration', window]) #TODO: take locking table name from option
        ids = cursor.fetchall()

        cursor.execute("UPDATE %s SET processor = %s WHERE id <= %d AND id >= %d",
            ['csmh_migration', socket.gethostname() + '_' + os.getpid(), ids[0], ids[-1]]
        )
        #TODO: collect host info ahead of time


    def _release_lock(ids):
        cursor = connections['student_module_history']

        cursor.execute("SELECT id FROM %s WHERE id <= %d AND id >= %d AND processor = %s",
            ['csmh_migration', ids[0], ids[-1], socket.gethostname() + '_' + os.getpid()]
        )
        found_ids = cursor.fetchall()
        #Make sure this is the same number of rows as I expect
        #Clear processor

    def _release_lock_and_unqueue(ids):
        cursor = connections['student_module_history']

        cursor.execute("SELECT id FROM %s WHERE id <= %d AND id >= %d AND processor = %s",
            ['csmh_migration', ids[0], ids[-1], socket.gethostname() + '_' + os.getpid()]
        )
        found_ids = cursor.fetchall()
        #Make sure this is the same number of rows as I expect

        cursor.execute("DELETE FROM %s WHERE id <= %d AND id >= %d",
            ['csmh_migration', ids[0], ids[-1]]
        )

