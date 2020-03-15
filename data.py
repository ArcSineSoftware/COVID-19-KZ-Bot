from threading import Event
from typing import Optional, List
from os import stat, mkdir
from json import load, dump
from enum import IntEnum
from time import time


class ReportType(IntEnum):
    SHOP_OVERPRICE = 0
    OTHER = 9


class ReportStatus(IntEnum):
    UNSEEN = 0
    SEEN = 1
    REMOVED = 2


class Report:
    def __init__(self, id: int, type: ReportType, status: ReportStatus,
                 date: int, msg: Optional[str]):
        self.id: int = id
        self.type: ReportType = type
        self.status: ReportStatus = status
        self.date: int = date
        self.msg: Optional[str] = msg


class BotDB:
    FILE_SUBSCRIBERS = "subscribers.json"
    FILE_REPORTS_INDEX = "reports_index.json"
    FILE_REPORT = "report_{}.json"

    def __init__(self, db_path):
        try:
            stat(db_path)
        except FileNotFoundError:
            mkdir(db_path)
        self.db_path = db_path

        self._lock_event = Event()
        self._lock_event.set()

    def _lock(self):
        """Lock the database"""
        # Wait until the lock is True
        self._lock_event.wait()
        # Make the lock false
        self._lock_event.clear()

    def _unlock(self):
        """Unlock the database"""
        self._lock_event.set()

    def list_subscribers(self) -> List[int]:
        """Return the list of subscribers"""
        try:
            self._lock()
            fp = open(f"{self.db_path}/{self.FILE_SUBSCRIBERS}", "r")
            subscribers = load(fp)
            fp.close()
            self._unlock()
            return subscribers
        except FileNotFoundError:
            self._unlock()
            return []

    def _overwrite_subscribers(self, subscribers):
        """Overwrite the file with new subscribers"""
        self._lock()
        fp = open(f"{self.db_path}/{self.FILE_SUBSCRIBERS}", "w")
        subscribers.sort()
        dump(subscribers, fp)
        fp.close()
        self._unlock()

    def is_user_subscribed(self, tg_id: int):
        return tg_id in self.list_subscribers()

    def subscribe_user(self, tg_id: int):
        """Subscribe a user to the mailing"""
        subscribers = self.list_subscribers()
        if tg_id not in subscribers:
            subscribers.append(tg_id)
            self._overwrite_subscribers(subscribers)

    def unsubscribe_user(self, tg_id: int):
        """Do vice versa"""
        subscribers = self.list_subscribers()
        try:
            subscribers.remove(tg_id)
        except:
            pass
        self._overwrite_subscribers(subscribers)

    def _get_next_report_id(self) -> int:
        """Returns ID of last report plus 1"""
        return self.max_report_id() + 1

    def max_report_id(self) -> int:
        """Returns the greatest ID among reports"""
        try:
            return max(self.list_reports())
        except ValueError:
            return 0

    def get_report(self, id: int) -> Report:
        """Get Report from id. May raise KeyError if such report doesn't exist"""
        self._lock()
        try:
            fp = open(f"{self.db_path}/report_{id}.json", "r")
        except FileNotFoundError:
            raise KeyError
        report_dict = load(fp)
        fp.close()
        self._unlock()
        return Report(id, report_dict["type"], report_dict["status"],
                      report_dict["date"], report_dict["msg"])

    def add_report(self, type, msg: str) -> int:
        """Add an anonymous report, returns its ID"""
        id = self._get_next_report_id()
        self._lock()
        with open(f"{self.db_path}/report_{id}.json", "w") as fp:
            dump({
                "type": type,
                "status": ReportStatus.UNSEEN,
                "date": time(),
                "msg": msg
            }, fp)
        self._unlock()
        reports = self.list_reports()
        reports.append(id)
        self._overwrite_reports_index(reports)
        return id

    def _overwrite_reports_index(self, reports):
        self._lock()
        with open(f"{self.db_path}/{self.FILE_REPORTS_INDEX}", "w") as fp:
            dump(reports, fp)
        self._unlock()

    def list_reports(self) -> List[int]:
        """List all reports"""
        self._lock()
        try:
            with open(f"{self.db_path}/{self.FILE_REPORTS_INDEX}", "r") as fp:
                reports = load(fp)
        except FileNotFoundError:
            self._unlock()
            return []
        self._unlock()
        return reports

    def list_seen_reports(self) -> List[int]:
        """List seen reports"""
        reports = self.list_reports()
        i = 0
        while True:
            status = self.get_report(reports[i]).status
            if status != ReportStatus.SEEN:
                del reports[i]
            else:
                i += 1
            if i >= len(reports):
                break
        return reports

    def list_unseen_reports(self) -> List[int]:
        """List unseen reports"""
        reports = self.list_reports()
        i = 0
        while True:
            status = self.get_report(reports[i]).status
            if status != ReportStatus.UNSEEN:
                del reports[i]
            else:
                i += 1
            if i >= len(reports):
                break
        return reports

    def _mark_report(self, report_id: int, status):
        report = self.get_report(report_id)
        self._lock()
        with open(f"{self.db_path}/report_{report_id}.json", "w") as fp:
            dump({
                "type": report.type,
                "status": status,
                "date": report.date,
                "msg": report.msg
            }, fp)
        self._unlock()

    def mark_report_seen(self, report_id: int):
        """After an operator reads the report, he/she can mark it as seen"""
        self._mark_report(report_id, ReportStatus.SEEN)

    def mark_report_unseen(self, report_id: int):
        """Do vice versa"""
        self._mark_report(report_id, ReportStatus.UNSEEN)

    def mark_report_removed(self, report_id: int):
        """If the report is indecent, the operator can mark it spam and delete it"""
        self._mark_report(report_id, ReportStatus.REMOVED)
