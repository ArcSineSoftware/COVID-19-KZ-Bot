import data
import unittest
import shutil

TEMPDIR = "/tmp/TestDBDirectory"

if __name__ == '__main__':
    unittest.main()


class TestReportHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.db = data.BotDB(TEMPDIR)

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEMPDIR)

    def test_add_report(self):
        id1 = self.db.add_report(data.ReportType.SHOP_OVERPRICE, "I hate this shop")
        self.db.add_report(data.ReportType.OTHER, "I need help!")
        self.assertEqual(len(self.db.list_reports()), 2)
        report = self.db.get_report(id1)
        self.assertEqual(report.id, id1)
        self.assertEqual(report.type, data.ReportType.SHOP_OVERPRICE)
        self.assertEqual(report.status, data.ReportStatus.UNSEEN)
        self.assertGreater(report.date, 0)
        self.assertEqual(report.msg, "I hate this shop")

    def test_mark_seen_and_unseen(self):
        self.db.mark_report_seen(0)
        self.assertEqual(len(self.db.list_seen_reports()), 1)
        self.db.mark_report_unseen(0)
        self.assertEqual(len(self.db.list_seen_reports()), 0)


class TestSubscriptionHandler(unittest.TestCase):
    def setUp(self) -> None:
        self.db = data.BotDB(TEMPDIR)
        self.expected_list = [10 ** i for i in range(10)]

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(TEMPDIR)

    def test_is_subscribed(self):
        db = self.db
        self.assertFalse(db.is_user_subscribed(123))
        db.subscribe_user(123)
        self.assertTrue(db.is_user_subscribed(123))
        db.unsubscribe_user(123)
        self.assertFalse(db.is_user_subscribed(123))

    def test_subscribe_user(self):
        db = self.db
        for i in range(10):
            db.subscribe_user(10 ** i)
        self.assertListEqual(db.list_subscribers(), self.expected_list)

    def test_unsubscribe_user(self):
        db = self.db
        for i in range(len(self.expected_list)):
            db.unsubscribe_user(self.expected_list[i])
            self.assertListEqual(db.list_subscribers(), self.expected_list[i + 1:])
