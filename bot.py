from typing import Dict, Callable, Union, Tuple
from sys import exit
import threading
import logging
import telegram as tg
import telegram.ext as tgext

from data import *
import translation

# Translation function
S: Callable[[Union[str, tg.Update, tg.Message, tg.User], str], str]

# Version string for /info
VERSION = "Anti-COVID-19 Bot for Kazakhstan v1.0"
TRANSLATIONS_DIRECTORY = "languages"
CONFIG = "config.json"

# Logging configuration
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot database
db: BotDB

# Bot config dictionary
config: Dict

# States for several conversations
SELECT_SERVICE, CHECK_SYMPTOMS, SELECT_REPORT_TYPE, WRITE_REPORT, CONFIRM_REPORT = range(5)
AP_SELECT, SUBMIT_NEWS_POST, CONFIRM_SUBMITTING, REPORT_VIEWER, CONFIRM_REMOVING = range(5)


# News Post object
class NewsPost:
    def __init__(self):
        self.texts = []
        self.photos = []
        self.videos = []


# Users can select their reports' types, they're gonna stay here for a while
report_types: Dict[int, int] = {}
report_texts: Dict[int, str] = {}
news_posts: Dict[int, NewsPost] = {}

# Lock for publishing news
publication_lock = threading.Event()
publication_lock.set()
publication_queue: List[NewsPost] = []

# Used when an admin watches reports
viewing_status: Dict[int, int] = {}
# Last report that was shown
viewed_report_id: Dict[int, int] = {}
# Action is about marking reports - giving them new statuses
# First element means with which ReportType do we mark
# Second element is report_id
action_queue: List[Tuple[int, int]]


def main():
    # Manage languages
    global S
    tr = translation.BotTranslation(TRANSLATIONS_DIRECTORY)
    S = tr.get_string

    # Load the config file
    global config
    try:
        with open(CONFIG) as fp:
            config = load(fp)
    except FileNotFoundError:
        logger.error(f"The configuration file {CONFIG} does not exist!")
        exit(1)

    # Initialize database class
    global db
    if "db_path" not in config:
        logger.error(f"Database path is not set!")
        exit(1)
    db_path = config["db_path"]
    db = BotDB(db_path)

    # Initialize the bot
    if "tg_key" not in config:
        logger.error(f"Telegram key is not set!")
        exit(1)
    tg_key = config["tg_key"]
    bot = tgext.Updater(tg_key, use_context=True)

    # Add all handlers
    [bot.dispatcher.add_handler(handler) for handler in [
        tgext.ConversationHandler(
            entry_points=[
                tgext.CommandHandler("admin", cmd_admin)
            ],
            states={
                AP_SELECT: [
                    tgext.MessageHandler(tgext.Filters.text, msg_ap_select)
                ],
                SUBMIT_NEWS_POST: [
                    tgext.CommandHandler("finish", cmd_admin_finish),
                    tgext.CommandHandler("cancel", cmd_admin_cancel),
                    # TODO: Divide MessageHandlers by filters
                    tgext.MessageHandler(
                        tgext.Filters.text,  # | tgext.Filters.photo | tgext.Filters.video,
                        msg_submit_post
                    )
                ],
                CONFIRM_SUBMITTING: [
                    tgext.CommandHandler("confirm", cmd_admin_confirm),
                    tgext.CommandHandler("cancel", cmd_admin_cancel)
                ],
                REPORT_VIEWER: [
                    tgext.MessageHandler(tgext.Filters.text, msg_handler_buttons)
                ],
                # CONFIRM_REMOVING
            },
            fallbacks=[
            ]
        ),
        tgext.ConversationHandler(
            entry_points=[
                tgext.CommandHandler("start", cmd_start),
                tgext.MessageHandler(tgext.Filters.text, msg_select_service)
            ],
            states={
                SELECT_SERVICE: [
                    tgext.MessageHandler(tgext.Filters.text, msg_select_service)
                ],
                CHECK_SYMPTOMS: [
                    tgext.MessageHandler(tgext.Filters.text, msg_check_symptoms)
                ],
                SELECT_REPORT_TYPE: [
                    tgext.MessageHandler(tgext.Filters.text, msg_select_report_type)
                ],
                WRITE_REPORT: [
                    tgext.CommandHandler("cancel", cmd_write_report_cancel),
                    tgext.MessageHandler(tgext.Filters.text, msg_write_report)
                ],
                CONFIRM_REPORT: [
                    tgext.MessageHandler(tgext.Filters.text, msg_confirm_report),
                ]
            },
            fallbacks=[
            ]
        )
    ]]

    # Long poll
    logger.info(f"Launching {VERSION}")
    bot.start_polling()
    bot.idle()


def extract_update(update: tg.Update):
    """Extract user id, text, etc from Update as a tuple"""
    msg = update.message
    return msg.from_user.id, msg.from_user.language_code, msg.text


def start_reply_keyboard(id, lang):
    sub_button_string = S(lang, "BUTTON_SUBSCRIBE_FOR_THE_NEWS") \
        if not db.is_user_subscribed(id) else S(lang, "BUTTON_UNSUBSCRIBE")
    return tg.ReplyKeyboardMarkup(
        [[S(lang, "BUTTON_BASIC_PROTECTION")], [sub_button_string],
         [S(lang, "BUTTON_CHECK_SYMPTOMS")], [S(lang, "BUTTON_WRITE_REPORT")]
         ],
        selective=True, resize_keyboard=True
    )


def cmd_start(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    m.reply_text(
        S(m, "START"),
        reply_markup=start_reply_keyboard(m.from_user.id, m)
    )
    return SELECT_SERVICE


def msg_select_service(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    id, lang, text = extract_update(update)
    if text == S(lang, "BUTTON_BASIC_PROTECTION"):
        m.reply_text(S(lang, "BASIC_PROTECTION_START"))
    elif text == S(lang, "BUTTON_SUBSCRIBE_FOR_THE_NEWS"):
        db.subscribe_user(id)
        logger.info(f"User {id} has subscribed to the news")
        m.reply_text(S(lang, "SUBSCRIBE_SUCCESS"),
                     reply_markup=start_reply_keyboard(id, lang))
    elif text == S(lang, "BUTTON_UNSUBSCRIBE"):
        db.unsubscribe_user(id)
        logger.info(f"User {id} has unsubscribed from the news")
        m.reply_text(S(lang, "UNSUBSCRIBE_SUCCESS"),
                     reply_markup=start_reply_keyboard(id, lang))
    elif text == S(lang, "BUTTON_CHECK_SYMPTOMS"):
        m.reply_text(S(lang, "BASIC_SYMPTOMS"),
                     reply_markup=tg.ReplyKeyboardMarkup(
                         [["✅", "❌"]], resize_keyboard=True, selective=True
                     ))
        return CHECK_SYMPTOMS
    elif text == S(lang, "BUTTON_WRITE_REPORT"):
        m.reply_text(S(lang, "SELECT_REPORT_TYPE"),
                     reply_markup=tg.ReplyKeyboardMarkup(
                         [[S(lang, "TYPE_OVERPRICE")], [S(lang, "TYPE_OTHER")]],
                         resize_keyboard=True, selective=True
                     ))
        return SELECT_REPORT_TYPE
    else:
        # The language of the user could have changed
        # this is why we need to send the keyboard again
        m.reply_text(S(lang, "UNKNOWN_SELECTION"),
                     reply_markup=start_reply_keyboard(id, lang))


def msg_check_symptoms(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    id, lang, text = extract_update(update)
    reply_keyboard = start_reply_keyboard(id, lang)
    m.reply_text(S(lang, "WARNING" if text == "✅" else "NO_WARNING"),
                 reply_markup=reply_keyboard)
    return SELECT_SERVICE


def msg_select_report_type(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    id, lang, text = extract_update(update)
    if text == S(lang, "TYPE_OVERPRICE"):
        type = ReportType.SHOP_OVERPRICE
    else:
        type = ReportType.OTHER
    report_types[id] = type
    m.reply_text(S(lang, "WRITE_YOUR_REPORT"),
                 reply_markup=tg.ReplyKeyboardRemove(selective=True))
    return WRITE_REPORT


def msg_write_report(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    id, lang, text = extract_update(update)
    report_texts[id] = text
    m.reply_text(S(lang, "CONFIRM_SEND").format(text),
                 reply_markup=tg.ReplyKeyboardMarkup(
                     [["✅", "❌"]], resize_keyboard=True, selective=True
                 ))

    return CONFIRM_REPORT


def msg_confirm_report(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    id, lang, text = extract_update(update)
    try:
        type = report_types[id]
        msg = report_texts[id]
    except KeyError:
        m.reply_text(S(lang, "UNKNOWN_ERROR"))
        return cmd_start(update, context)
    if text == "✅":
        report_id = db.add_report(type, msg)
        logger.info(f"A user wrote a report with ID {report_id}")
        m.reply_text(S(lang, "THANK_YOU_FOR_REPORT"),
                     reply_markup=start_reply_keyboard(id, lang))
        del report_types[id]
        del report_texts[id]
    else:
        m.reply_text(S(lang, "REPORTING_CANCELLED"),
                     reply_markup=start_reply_keyboard(id, lang))
    return SELECT_SERVICE


def cmd_write_report_cancel(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    id, lang, text = extract_update(update)
    m.reply_text(S(lang, "REPORTING_CANCELLED"),
                 reply_markup=start_reply_keyboard(id, lang))
    return SELECT_SERVICE


def admin_panel_keyboard(id: int, lang):
    raw_markup = [
        [S(lang, "BUTTON_SEND_NEWS")],
        [S(lang, "BUTTON_UNSEEN")],
        [S(lang, "BUTTON_SEEN")],
    ]
    return tg.ReplyKeyboardMarkup(
        raw_markup,
        selective=True, resize_keyboard=True
    )


def cmd_admin(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    id, lang, text = extract_update(update)
    is_admin = id in config["admins"]
    if not is_admin:
        m.reply_text(S(lang, "ADMIN_MENU_PRIV_ERROR"))
        return tgext.ConversationHandler.END
    else:
        m.reply_text(S(lang, "ADMIN_PANEL_START"),
                     reply_markup=admin_panel_keyboard(id, lang))
    return AP_SELECT


def show_report(context: tgext.CallbackContext, admin_id: int, lang, report_id: int):
    """Send a report to an admin"""
    bot = context.bot
    try:
        report = db.get_report(report_id)
    except KeyError:
        # get_report can report KeyError if the report does not exist
        # that can happen when another admin deletes the selected report already
        bot.send_message(admin_id, S(lang, "REPORT_IS_REMOVED"))
        return
    send_text = S(lang, "REPORT_HEADER_TEMPLATE").format(report_id, report.type) + '\n' + report.msg
    bot.send_message(
        admin_id, send_text,
        reply_markup=tg.ReplyKeyboardMarkup(
            [["⬅️",
              S(lang, "MARK_SEEN") if report.status == ReportStatus.UNSEEN else S(lang, "MARK_UNSEEN"),
              S(lang, "REMOVE_REPORT"),
              S(lang, "QUIT_VIEWING"),
              "➡️"]],
            resize_keyboard=True, selective=True
        )
    )


def msg_ap_select(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    id, lang, text = extract_update(update)
    if text == S(lang, "BUTTON_SEND_NEWS"):
        m.reply_text(S(lang, "SUBMIT_NEWS_1"), reply_markup=tg.ReplyKeyboardRemove())
        return SUBMIT_NEWS_POST
    elif text == S(lang, "BUTTON_UNSEEN"):
        viewing_status[id] = ReportStatus.UNSEEN
        reports = db.list_unseen_reports()
        if len(reports) > 0:
            viewed_report_id[id] = reports[-1]
            show_report(context, id, lang, viewed_report_id[id])
            return REPORT_VIEWER
        else:
            m.reply_text(S(lang, "ERROR_NO_REPORTS_OF_THIS_TYPE"))
            return
    elif text == S(lang, "BUTTON_SEEN"):
        viewing_status[id] = ReportStatus.SEEN
        reports = db.list_seen_reports()
        if len(reports) > 0:
            viewed_report_id[id] = reports[-1]
            show_report(context, id, lang, viewed_report_id[id])
            return REPORT_VIEWER
        else:
            m.reply_text(S(lang, "ERROR_NO_REPORTS_OF_THIS_TYPE"))
            return


def msg_submit_post(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    id, lang = m.from_user.id, m.from_user.language_code
    if id not in news_posts:
        news_posts[id] = NewsPost()
    try:
        if type(m.text) is str and m.text:
            news_posts[id].texts.append(m.text)
    except:
        pass
    try:
        if len(m.photo) > 0:
            news_posts[id].photos.append(m.photo)
    except:
        pass
    try:
        if len(m.video) > 0:
            news_posts[id].videos.append(m.video)
    except:
        pass
    m.reply_text(S(lang, "SUBMIT_NEWS_2"))


def cmd_admin_finish(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    id, lang, text = extract_update(update)
    m.reply_text(S(lang, "SUBMIT_NEWS_3"))
    return CONFIRM_SUBMITTING


def cmd_admin_confirm(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    id, lang, text = extract_update(update)
    publication_queue.append(news_posts[id])
    context.dispatcher.job_queue.run_once(publish_new_post, 1)
    logger.info(f"A new post was published")
    m.reply_text(S(lang, "SUBMIT_SUCCESS"),
                 reply_markup=admin_panel_keyboard(id, lang))
    return SELECT_SERVICE


def cmd_admin_cancel(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    id, lang, text = extract_update(update)
    m.reply_text(S(lang, "REPORTING_CANCELLED"),
                 reply_markup=admin_panel_keyboard(id, lang))
    return SELECT_SERVICE


def publish_new_post(context: tgext.CallbackContext):
    # Wait till lock is free
    publication_lock.wait()
    # Activate the lock
    publication_lock.clear()
    bot = context.bot
    subscriber_ids = db.list_subscribers()
    for post in publication_queue:
        for subscriber_id in subscriber_ids:
            for text in post.texts:
                bot.send_message(subscriber_id, text)
            for photo in post.photos:
                bot.send_photo(subscriber_id, photo)
            for video in post.videos:
                bot.send_video(subscriber_id, video)
        publication_queue.remove(post)
    # Deactivate the lock
    publication_lock.set()


def quit_reports_viewer(admin_id):
    del viewing_status[admin_id]
    del viewed_report_id[admin_id]


def msg_handler_buttons(update: tg.Update, context: tgext.CallbackContext):
    m = update.message
    id, lang, text = extract_update(update)
    report_status = viewing_status[id]
    report_id = viewed_report_id[id]
    list_reports = db.list_unseen_reports if report_status == ReportStatus.UNSEEN else db.list_seen_reports
    if text == "⬅️":  # previous report
        reports = list_reports()
        try:
            index = reports.index(report_id)
        except ValueError:
            m.reply_text(S(lang, "UNKNOWN_ERROR"),
                         reply_markup=admin_panel_keyboard(id, lang))
            quit_reports_viewer(id)
            return AP_SELECT
        if index == 0: # this report is first
            m.reply_text(S(lang, "ALREADY_FIRST"))
            return
        viewed_report_id[id] = reports[index - 1]
    elif text == "➡️":  # next report
        reports = list_reports()
        try:
            index = reports.index(report_id)
        except ValueError:
            m.reply_text(S(lang, "UNKNOWN_ERROR"),
                         reply_markup=admin_panel_keyboard(id, lang))
            quit_reports_viewer(id)
            return AP_SELECT
        if index + 1 == len(reports): # this report is already last
            m.reply_text(S(lang, "ALREADY_LAST"))
            return
        viewed_report_id[id] = reports[index + 1]
    elif text == S(lang, "MARK_SEEN"):
        # ignore if already SEEN
        if report_status == ReportStatus.SEEN:
            return
        db.mark_report_seen(report_id)
    elif text == S(lang, "MARK_UNSEEN"):
        # ignore if already UNSEEN
        if report_status == ReportStatus.UNSEEN:
            return
        db.mark_report_unseen(report_id)
    elif text == S(lang, "REMOVE_REPORT"):
        pass
    elif text == S(lang, "QUIT_VIEWING"):
        m.reply_text(S(lang, "VIEWING_IS_QUIT"),
                     reply_markup=admin_panel_keyboard(id, lang))
        quit_reports_viewer(id)
        return AP_SELECT
    show_report(context, id, lang, viewed_report_id[id])


if __name__ == '__main__':
    main()
